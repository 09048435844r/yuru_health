import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

_JST = timezone(timedelta(hours=9))

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    GOOGLE_FIT_AVAILABLE = True
except ImportError:
    GOOGLE_FIT_AVAILABLE = False


class GoogleFitFetcher:
    """
    Google Fit API を使用した健康データ取得クラス
    Samsung Health -> Health Connect -> Google Fit 経由のデータを取得
    """
    
    def __init__(self, credentials: "Credentials", db_manager=None):
        if not GOOGLE_FIT_AVAILABLE:
            raise ImportError("google-api-python-client is required")
        self.credentials = credentials
        self.db_manager = db_manager
        self.fitness_service = build("fitness", "v1", credentials=credentials)
    
    def _time_millis(self, dt: datetime) -> int:
        """datetime を ミリ秒エポックに変換"""
        return int(dt.timestamp() * 1000)
    
    def _nano_to_datetime(self, nanos: str) -> str:
        """ナノ秒エポック文字列を ISO形式に変換"""
        return datetime.fromtimestamp(int(nanos) / 1e9).isoformat()
    
    def fetch_steps(self, user_id: str, start_date: Optional[str] = None, 
                    end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        歩数データを取得 (com.google.step_count.delta)
        JST基準で各日の00:00:00〜23:59:59を明示的に指定して取得
        dataset APIを使用して生データを取得し、日別に集計
        """
        start_dt, end_dt = self._parse_date_range(start_date, end_date)
        
        results = []
        current_date = start_dt.date()
        end_date_obj = end_dt.date()
        
        # Iterate through each day in the range
        while current_date <= end_date_obj:
            # Define JST-based day boundaries: 00:00:00 to 23:59:59
            day_start = datetime.combine(current_date, datetime.min.time(), tzinfo=_JST)
            day_end = datetime.combine(current_date, datetime.max.time(), tzinfo=_JST)
            
            # Use dataset API instead of aggregate API to get raw data points
            data_source = "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
            dataset_id = f"{self._time_millis(day_start) * 1000000}-{self._time_millis(day_end) * 1000000}"
            
            try:
                response = self.fitness_service.users().dataSources().datasets().get(
                    userId="me",
                    dataSourceId=data_source,
                    datasetId=dataset_id,
                ).execute()
                
                # Data Lake: Save raw response for this day
                self._save_to_data_lake(user_id, response, "steps")
                
                # Extract and sum all step counts from data points
                steps = 0
                for point in response.get("point", []):
                    for val in point.get("value", []):
                        steps += val.get("intVal", 0)
                
                # Store result with explicit date
                results.append({
                    "user_id": user_id,
                    "date": current_date.strftime("%Y-%m-%d"),
                    "data_type": "steps",
                    "value": steps,
                    "raw_data": json.dumps({"point": response.get("point", [])[:10]}),  # Store first 10 points as sample
                })
                
                logger.info(f"Google Fit steps for {current_date}: {steps} steps ({len(response.get('point', []))} data points)")
                
            except Exception as e:
                logger.warning(f"Google Fit steps fetch failed for {current_date}: {e}")
                # Continue to next day even if one day fails
            
            # Move to next day
            current_date += timedelta(days=1)
        
        return results
    
    def fetch_weight(self, user_id: str, start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        体重データを取得 (com.google.weight)
        """
        start_dt, end_dt = self._parse_date_range(start_date, end_date)
        
        data_source = "derived:com.google.weight:com.google.android.gms:merge_weight"
        dataset_id = f"{self._time_millis(start_dt) * 1000000}-{self._time_millis(end_dt) * 1000000}"
        
        try:
            response = self.fitness_service.users().dataSources().datasets().get(
                userId="me",
                dataSourceId=data_source,
                datasetId=dataset_id,
            ).execute()
            
            # Data Lake: 生データを解析前に保存
            self._save_to_data_lake(user_id, response, "weight")
            
            results = []
            for point in response.get("point", []):
                measured_at = self._nano_to_datetime(point.get("startTimeNanos", "0"))
                weight_kg = None
                for val in point.get("value", []):
                    if "fpVal" in val:
                        weight_kg = round(val["fpVal"], 2)
                
                if weight_kg is not None:
                    results.append({
                        "user_id": user_id,
                        "date": measured_at,
                        "data_type": "weight",
                        "value": weight_kg,
                        "raw_data": json.dumps(point),
                    })
            
            return results
        except Exception as e:
            raise Exception(f"Google Fit 体重取得エラー: {e}")
    
    def fetch_sleep(self, user_id: str, start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        睡眠データを取得 (セッションタイプ 72)
        """
        start_dt, end_dt = self._parse_date_range(start_date, end_date)
        
        try:
            response = self.fitness_service.users().sessions().list(
                userId="me",
                startTime=start_dt.isoformat() + "Z",
                endTime=end_dt.isoformat() + "Z",
                activityType=72,  # Sleep
            ).execute()
            
            # Data Lake: 生データを解析前に保存
            self._save_to_data_lake(user_id, response, "sleep")
            
            results = []
            for session in response.get("session", []):
                start_nanos = session.get("startTimeMillis", "0")
                end_nanos = session.get("endTimeMillis", "0")
                
                start_time = datetime.fromtimestamp(int(start_nanos) / 1000)
                end_time = datetime.fromtimestamp(int(end_nanos) / 1000)
                duration_minutes = int((end_time - start_time).total_seconds() / 60)
                
                results.append({
                    "user_id": user_id,
                    "date": start_time.strftime("%Y-%m-%d"),
                    "data_type": "sleep",
                    "value": duration_minutes,
                    "raw_data": json.dumps(session),
                })
            
            return results
        except Exception as e:
            raise Exception(f"Google Fit 睡眠取得エラー: {e}")
    
    def fetch_steps_finalized(self, user_id: str, target_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        前日の確定歩数データを取得（深夜0:30以降の確定値取得用）
        
        Args:
            user_id: ユーザーID
            target_date: 取得対象日（YYYY-MM-DD形式）。Noneの場合は前日
        
        Returns:
            確定歩数データ、または取得失敗時はNone
        """
        if target_date:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            # Default to previous day
            target_dt = (datetime.now(_JST) - timedelta(days=1)).date()
        
        # Fetch only the target day
        results = self.fetch_steps(user_id, target_dt.strftime("%Y-%m-%d"), target_dt.strftime("%Y-%m-%d"))
        
        if results:
            logger.info(f"Google Fit finalized steps for {target_dt}: {results[0].get('value')} steps")
            return results[0]
        else:
            logger.warning(f"Google Fit finalized steps fetch failed for {target_dt}")
            return None
    
    def fetch_all(self, user_id: str, start_date: Optional[str] = None,
                  end_date: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        全データ（歩数・体重・睡眠）をまとめて取得
        """
        results = {
            "steps": self.fetch_steps(user_id, start_date, end_date),
            "weight": self.fetch_weight(user_id, start_date, end_date),
            "sleep": self.fetch_sleep(user_id, start_date, end_date),
        }

        total = sum(len(v) for v in results.values())
        if total == 0:
            logger.info("Google Fit: no new data returned from API")

        return results
    
    def _save_to_data_lake(self, user_id: str, raw_response: Dict[str, Any], category: str):
        """APIレスポンス全体を raw_data_lake に保存"""
        if not self.db_manager:
            logger.info("GoogleFitFetcher: db_manager is None, skipping save")
            return
        self.db_manager.save_raw_data(
            user_id=user_id,
            source="google_fit",
            category=category,
            payload=raw_response,
        )
    
    def _parse_date_range(self, start_date: Optional[str], end_date: Optional[str]):
        """日付範囲をパース"""
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        else:
            end_dt = datetime.now(_JST)
        
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = end_dt - timedelta(days=7)
        
        return start_dt, end_dt
