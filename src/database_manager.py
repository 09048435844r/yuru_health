import json
import logging
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from src.utils.secrets_loader import load_secrets

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, secrets_path: str = "config/secrets.yaml"):
        self.secrets = load_secrets(secrets_path)
        self.supabase: Client = self._create_client()
        self.env = "cloud"
        self.db_config = {"type": "supabase"}
    
    def _create_client(self) -> Client:
        supabase_config = self.secrets.get("supabase", {})
        url = supabase_config.get("url", "")
        key = supabase_config.get("key", "")
        if not url or not key:
            raise ValueError("Supabase URL and Key must be set in config/secrets.yaml")
        return create_client(url, key)
    
    def connect(self):
        pass
    
    def close(self):
        pass
    
    def init_tables(self):
        pass
    
    def insert_weight_data(self, user_id: str, measured_at: str, weight_kg: float, raw_data: str):
        data = {
            "user_id": user_id,
            "measured_at": measured_at,
            "weight_kg": weight_kg,
            "raw_data": self._parse_raw_data(raw_data),
        }
        self.supabase.table("weight_data").insert(data).execute()
    
    def get_weight_data(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = self.supabase.table("weight_data").select("*").order("measured_at", desc=True).limit(limit)
        if user_id:
            query = query.eq("user_id", user_id)
        response = query.execute()
        return response.data
    
    def insert_oura_data(self, user_id: str, measured_at: str, activity_score: Optional[int], 
                        sleep_score: Optional[int], readiness_score: Optional[int], 
                        steps: Optional[int], total_sleep_duration: Optional[int], raw_data: str):
        data = {
            "user_id": user_id,
            "measured_at": measured_at,
            "activity_score": activity_score,
            "sleep_score": sleep_score,
            "readiness_score": readiness_score,
            "steps": steps,
            "total_sleep_duration": total_sleep_duration,
            "raw_data": self._parse_raw_data(raw_data),
        }
        self.supabase.table("oura_data").insert(data).execute()
    
    def get_oura_data(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = self.supabase.table("oura_data").select("*").order("measured_at", desc=True).limit(limit)
        if user_id:
            query = query.eq("user_id", user_id)
        response = query.execute()
        return response.data
    
    def insert_environmental_log(self, timestamp: str, source: str, 
                                  latitude: Optional[float], longitude: Optional[float],
                                  weather_summary: Optional[str], temp: Optional[float],
                                  humidity: Optional[int], pressure: Optional[int],
                                  raw_data: Optional[str]):
        data = {
            "timestamp": timestamp,
            "source": source,
            "latitude": latitude,
            "longitude": longitude,
            "weather_summary": weather_summary,
            "temp": temp,
            "humidity": humidity,
            "pressure": pressure,
            "raw_data": self._parse_raw_data(raw_data),
        }
        self.supabase.table("environmental_logs").insert(data).execute()
    
    def get_latest_environmental_log(self) -> Optional[Dict[str, Any]]:
        response = (
            self.supabase.table("environmental_logs")
            .select("*")
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    
    def insert_google_fit_data(self, user_id: str, date: str, data_type: str,
                               value: Any, raw_data: Any):
        data = {
            "user_id": user_id,
            "date": date,
            "data_type": data_type,
            "value": value,
            "raw_data": self._parse_raw_data(raw_data),
        }
        self.supabase.table("google_fit_data").insert(data).execute()
    
    def get_google_fit_data(self, user_id: Optional[str] = None, data_type: Optional[str] = None,
                            limit: int = 100) -> List[Dict[str, Any]]:
        query = self.supabase.table("google_fit_data").select("*").order("date", desc=True).limit(limit)
        if user_id:
            query = query.eq("user_id", user_id)
        if data_type:
            query = query.eq("data_type", data_type)
        response = query.execute()
        return response.data
    
    def get_data_arrival_history(self, days: int = 14) -> List[Dict[str, Any]]:
        """過去N日間の (source, recorded_at) リストを raw_data_lake から取得"""
        from datetime import datetime, timedelta
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        response = (
            self.supabase.table("raw_data_lake")
            .select("source, recorded_at")
            .gte("recorded_at", start_date)
            .execute()
        )
        return response.data
    
    def get_raw_data_by_date(self, target_date: str, user_id: str = "user_001") -> Dict[str, List[Dict[str, Any]]]:
        """指定日の生データを source ごとに整理して返す"""
        response = (
            self.supabase.table("raw_data_lake")
            .select("*")
            .eq("user_id", user_id)
            .eq("recorded_at", target_date)
            .execute()
        )
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in response.data:
            source = row.get("source", "unknown")
            result.setdefault(source, []).append(row)
        return result
    
    def save_raw_data(self, user_id: str, recorded_at: str, source: str,
                      category: str, payload: Any):
        """raw_data_lake に生データを保存する"""
        try:
            data = {
                "user_id": user_id,
                "recorded_at": recorded_at,
                "source": source,
                "category": category,
                "payload": payload if isinstance(payload, dict) else self._parse_raw_data(payload),
            }
            self.supabase.table("raw_data_lake").insert(data).execute()
        except Exception as e:
            logger.warning(f"save_raw_data failed: source={source}, category={category}, error={e}")
    
    def save_token(self, user_id: str, provider: str, token_data: Dict[str, Any]):
        """OAuth トークンを upsert (insert or update) する"""
        data = {
            "user_id": user_id,
            "provider": provider,
            "token_data": token_data if isinstance(token_data, dict) else json.loads(token_data),
            "updated_at": "now()",
        }
        self.supabase.table("oauth_tokens").upsert(data).execute()
    
    def get_token(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
        """OAuth トークンを取得する"""
        response = (
            self.supabase.table("oauth_tokens")
            .select("token_data")
            .eq("user_id", user_id)
            .eq("provider", provider)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0].get("token_data")
        return None
    
    def delete_token(self, user_id: str, provider: str):
        """OAuth トークンを削除する"""
        self.supabase.table("oauth_tokens").delete().eq("user_id", user_id).eq("provider", provider).execute()
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError("Direct SQL queries are not supported with Supabase. Use table methods instead.")
    
    def _parse_raw_data(self, raw_data: Any) -> Any:
        if raw_data is None:
            return None
        if isinstance(raw_data, dict):
            return raw_data
        if isinstance(raw_data, str):
            try:
                return json.loads(raw_data)
            except (json.JSONDecodeError, TypeError):
                return raw_data
        return raw_data
