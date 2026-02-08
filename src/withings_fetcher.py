from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import requests
from src.base_fetcher import BaseFetcher
from auth.withings_oauth import WithingsOAuth


class WithingsFetcher(BaseFetcher):
    API_BASE_URL = "https://wbsapi.withings.net"
    
    def __init__(self, config: Dict[str, Any], oauth_client: Optional[WithingsOAuth] = None):
        super().__init__(config)
        if oauth_client is None:
            raise ValueError("oauth_client (WithingsOAuth) is required")
        self.oauth_client = oauth_client
        self.access_token: Optional[str] = None
    
    def authenticate(self) -> bool:
        self.access_token = self.oauth_client.get_valid_access_token()
        return self.access_token is not None
    
    def fetch_data(self, user_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.authenticate():
            raise Exception("Not authenticated. Please complete OAuth flow first.")
        
        if not end_date:
            end = datetime.now()
        else:
            end = datetime.fromisoformat(end_date)
        
        if not start_date:
            start = end - timedelta(days=30)
        else:
            start = datetime.fromisoformat(start_date)
        
        raw_response = self._fetch_measurements(int(start.timestamp()), int(end.timestamp()))
        
        parsed_data = self._parse_measurements(raw_response, user_id)
        
        self.update_fetch_time()
        
        return parsed_data
    
    def _fetch_measurements(self, startdate: int, enddate: int) -> Dict[str, Any]:
        url = f"{self.API_BASE_URL}/measure"
        
        params = {
            "action": "getmeas",
            "meastype": 1,
            "category": 1,
            "startdate": startdate,
            "enddate": enddate
        }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    def _parse_measurements(self, raw_response: Dict[str, Any], user_id: str) -> List[Dict[str, Any]]:
        data = []
        
        if raw_response.get("status") == 0:
            measuregrps = raw_response.get("body", {}).get("measuregrps", [])
            
            for grp in measuregrps:
                measured_at = datetime.fromtimestamp(grp["date"])
                
                for measure in grp.get("measures", []):
                    if measure["type"] == 1:
                        weight_kg = measure["value"] * (10 ** measure["unit"])
                        
                        data.append({
                            "user_id": user_id,
                            "measured_at": measured_at.strftime("%Y-%m-%d %H:%M:%S"),
                            "weight_kg": round(weight_kg, 2),
                            "raw_data": self.save_raw_data(raw_response)
                        })
        
        return data
    
    def parse_response(self, raw_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        parsed_data = []
        
        if raw_response.get("status") == 0:
            measuregrps = raw_response.get("body", {}).get("measuregrps", [])
            
            for grp in measuregrps:
                measured_at = datetime.fromtimestamp(grp["date"])
                
                for measure in grp.get("measures", []):
                    if measure["type"] == 1:
                        weight_kg = measure["value"] * (10 ** measure["unit"])
                        
                        parsed_data.append({
                            "measured_at": measured_at.strftime("%Y-%m-%d %H:%M:%S"),
                            "weight_kg": round(weight_kg, 2)
                        })
        
        return parsed_data
