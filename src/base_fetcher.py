from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
import json


class BaseFetcher(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.last_fetch_time: Optional[datetime] = None
    
    @abstractmethod
    def fetch_data(self, user_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def authenticate(self) -> bool:
        pass
    
    def parse_response(self, raw_response: Any) -> List[Dict[str, Any]]:
        return []
    
    def save_raw_data(self, data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)
    
    def get_last_fetch_time(self) -> Optional[datetime]:
        return self.last_fetch_time
    
    def update_fetch_time(self):
        self.last_fetch_time = datetime.now()
