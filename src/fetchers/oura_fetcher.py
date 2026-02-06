import yaml
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from src.base_fetcher import BaseFetcher


class OuraFetcher(BaseFetcher):
    API_BASE_URL = "https://api.ouraring.com/v2/usercollection"
    
    def __init__(self, config: Dict[str, Any], secrets_path: str = "config/secrets.yaml"):
        super().__init__(config)
        self.secrets_path = Path(secrets_path)
        self.secrets = self._load_secrets()
        self.personal_token = self.secrets["oura"]["personal_token"]
    
    def _load_secrets(self) -> Dict[str, Any]:
        with open(self.secrets_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def authenticate(self) -> bool:
        return self.personal_token is not None and self.personal_token != "your_oura_personal_token"
    
    def fetch_data(self, user_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.authenticate():
            raise Exception("Oura personal token is not configured. Please set it in config/secrets.yaml")
        
        if not end_date:
            end = datetime.now()
        else:
            end = datetime.fromisoformat(end_date)
        
        if not start_date:
            start = end - timedelta(days=30)
        else:
            start = datetime.fromisoformat(start_date)
        
        daily_activity = self._fetch_daily_activity(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        daily_sleep = self._fetch_daily_sleep(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        daily_readiness = self._fetch_daily_readiness(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        
        parsed_data = self._parse_oura_data(daily_activity, daily_sleep, daily_readiness, user_id)
        
        self.update_fetch_time()
        
        return parsed_data
    
    def _fetch_daily_activity(self, start_date: str, end_date: str) -> Dict[str, Any]:
        url = f"{self.API_BASE_URL}/daily_activity"
        
        params = {
            "start_date": start_date,
            "end_date": end_date
        }
        
        headers = {
            "Authorization": f"Bearer {self.personal_token}"
        }
        
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching daily activity: {e}")
            return {"data": []}
    
    def _fetch_daily_sleep(self, start_date: str, end_date: str) -> Dict[str, Any]:
        url = f"{self.API_BASE_URL}/daily_sleep"
        
        params = {
            "start_date": start_date,
            "end_date": end_date
        }
        
        headers = {
            "Authorization": f"Bearer {self.personal_token}"
        }
        
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching daily sleep: {e}")
            return {"data": []}
    
    def _fetch_daily_readiness(self, start_date: str, end_date: str) -> Dict[str, Any]:
        url = f"{self.API_BASE_URL}/daily_readiness"
        
        params = {
            "start_date": start_date,
            "end_date": end_date
        }
        
        headers = {
            "Authorization": f"Bearer {self.personal_token}"
        }
        
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching daily readiness: {e}")
            return {"data": []}
    
    def _parse_oura_data(self, activity: Dict[str, Any], sleep: Dict[str, Any], 
                        readiness: Dict[str, Any], user_id: str) -> List[Dict[str, Any]]:
        data = []
        
        activity_dict = {item["day"]: item for item in activity.get("data", [])}
        sleep_dict = {item["day"]: item for item in sleep.get("data", [])}
        readiness_dict = {item["day"]: item for item in readiness.get("data", [])}
        
        all_dates = set(activity_dict.keys()) | set(sleep_dict.keys()) | set(readiness_dict.keys())
        
        for date in sorted(all_dates):
            activity_data = activity_dict.get(date, {})
            sleep_data = sleep_dict.get(date, {})
            readiness_data = readiness_dict.get(date, {})
            
            combined_data = {
                "activity": activity_data,
                "sleep": sleep_data,
                "readiness": readiness_data
            }
            
            data.append({
                "user_id": user_id,
                "measured_at": f"{date} 00:00:00",
                "activity_score": activity_data.get("score"),
                "sleep_score": sleep_data.get("score"),
                "readiness_score": readiness_data.get("score"),
                "steps": activity_data.get("steps"),
                "total_sleep_duration": sleep_data.get("contributors", {}).get("total_sleep_duration"),
                "raw_data": self.save_raw_data(combined_data)
            })
        
        return data
    
    def parse_response(self, raw_response: Any) -> List[Dict[str, Any]]:
        return []
