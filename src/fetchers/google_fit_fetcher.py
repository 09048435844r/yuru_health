import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

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
        """
        start_dt, end_dt = self._parse_date_range(start_date, end_date)
        
        dataset_id = f"{self._time_millis(start_dt) * 1000000}-{self._time_millis(end_dt) * 1000000}"
        
        body = {
            "aggregateBy": [{
                "dataTypeName": "com.google.step_count.delta",
                "dataSourceId": "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
            }],
            "bucketByTime": {"durationMillis": 86400000},  # 1日ごと
            "startTimeMillis": self._time_millis(start_dt),
            "endTimeMillis": self._time_millis(end_dt),
        }
        
        try:
            response = self.fitness_service.users().dataset().aggregate(
                userId="me", body=body
            ).execute()
            
            # Data Lake: 生データを解析前に保存
            self._save_to_data_lake(user_id, response, "steps")
            
            results = []
            for bucket in response.get("bucket", []):
                bucket_start = datetime.fromtimestamp(
                    int(bucket["startTimeMillis"]) / 1000
                ).strftime("%Y-%m-%d")
                
                steps = 0
                for dataset in bucket.get("dataset", []):
                    for point in dataset.get("point", []):
                        for val in point.get("value", []):
                            steps += val.get("intVal", 0)
                
                results.append({
                    "user_id": user_id,
                    "date": bucket_start,
                    "data_type": "steps",
                    "value": steps,
                    "raw_data": json.dumps(bucket),
                })
            
            return results
        except Exception as e:
            raise Exception(f"Google Fit 歩数取得エラー: {e}")
    
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
    
    def fetch_all(self, user_id: str, start_date: Optional[str] = None,
                  end_date: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        全データ（歩数・体重・睡眠）をまとめて取得
        """
        results = {"steps": [], "weight": [], "sleep": []}
        
        try:
            results["steps"] = self.fetch_steps(user_id, start_date, end_date)
        except Exception:
            pass
        
        try:
            results["weight"] = self.fetch_weight(user_id, start_date, end_date)
        except Exception:
            pass
        
        try:
            results["sleep"] = self.fetch_sleep(user_id, start_date, end_date)
        except Exception:
            pass
        
        return results
    
    def _save_to_data_lake(self, user_id: str, raw_response: Dict[str, Any], category: str):
        """APIレスポンス全体を raw_data_lake に保存"""
        if not self.db_manager:
            logger.info("GoogleFitFetcher: db_manager is None, skipping save")
            return
        recorded_at = datetime.now().strftime("%Y-%m-%d")
        self.db_manager.save_raw_data(
            user_id=user_id,
            recorded_at=recorded_at,
            source="google_fit",
            category=category,
            payload=raw_response,
        )
    
    def _parse_date_range(self, start_date: Optional[str], end_date: Optional[str]):
        """日付範囲をパース"""
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        else:
            end_dt = datetime.now()
        
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = end_dt - timedelta(days=7)
        
        return start_dt, end_dt
