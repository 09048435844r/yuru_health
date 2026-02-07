import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode
from src.utils.secrets_loader import load_secrets


class WithingsOAuth:
    AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
    TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
    REDIRECT_URI = "http://localhost:8501"
    
    def __init__(self, secrets_path: str = "config/secrets.yaml", token_path: str = "config/token_withings.json"):
        self.token_path = Path(token_path)
        self.secrets = load_secrets(secrets_path)
        self.client_id = self.secrets["withings"]["client_id"]
        self.consumer_secret = self.secrets["withings"]["consumer_secret"]
        self.tokens = self._load_tokens()
    
    def _load_tokens(self) -> Dict[str, Any]:
        if self.token_path.exists():
            with open(self.token_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def _save_tokens(self, tokens: Dict[str, Any]):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2, ensure_ascii=False)
        self.tokens = tokens
    
    def get_authorization_url(self, state: str = "random_state") -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.REDIRECT_URI,
            "scope": "user.metrics",
            "state": state
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"
    
    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        data = {
            "action": "requesttoken",
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.consumer_secret,
            "code": code,
            "redirect_uri": self.REDIRECT_URI
        }
        
        response = requests.post(self.TOKEN_URL, data=data)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("status") == 0:
            body = result.get("body", {})
            tokens = {
                "access_token": body.get("access_token"),
                "refresh_token": body.get("refresh_token"),
                "expires_in": body.get("expires_in"),
                "token_type": body.get("token_type"),
                "scope": body.get("scope"),
                "user_id": body.get("userid"),
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(seconds=body.get("expires_in", 10800))).isoformat()
            }
            self._save_tokens(tokens)
            return tokens
        else:
            raise Exception(f"Token exchange failed: {result}")
    
    def refresh_access_token(self) -> Dict[str, Any]:
        if not self.tokens.get("refresh_token"):
            raise Exception("No refresh token available")
        
        data = {
            "action": "requesttoken",
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.consumer_secret,
            "refresh_token": self.tokens["refresh_token"]
        }
        
        response = requests.post(self.TOKEN_URL, data=data)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("status") == 0:
            body = result.get("body", {})
            tokens = {
                "access_token": body.get("access_token"),
                "refresh_token": body.get("refresh_token"),
                "expires_in": body.get("expires_in"),
                "token_type": body.get("token_type"),
                "scope": body.get("scope"),
                "user_id": body.get("userid"),
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(seconds=body.get("expires_in", 10800))).isoformat()
            }
            self._save_tokens(tokens)
            return tokens
        else:
            raise Exception(f"Token refresh failed: {result}")
    
    def get_valid_access_token(self) -> Optional[str]:
        if not self.tokens:
            return None
        
        expires_at = self.tokens.get("expires_at")
        if expires_at:
            expires_datetime = datetime.fromisoformat(expires_at)
            if datetime.now() >= expires_datetime - timedelta(minutes=5):
                try:
                    self.refresh_access_token()
                except Exception as e:
                    print(f"Failed to refresh token: {e}")
                    return None
        
        return self.tokens.get("access_token")
    
    def is_authenticated(self) -> bool:
        return self.get_valid_access_token() is not None
    
    def get_user_id(self) -> Optional[str]:
        return self.tokens.get("user_id")
    
    def clear_tokens(self):
        if self.token_path.exists():
            self.token_path.unlink()
        self.tokens = {}
