import requests
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from src.utils.secrets_loader import load_secrets

JST = timezone(timedelta(hours=9))


class WithingsOAuth:
    AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
    TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
    PROVIDER = "withings"
    
    def __init__(self, db_manager, secrets_path: str = "config/secrets.yaml", user_id: str = "user_001"):
        self.db_manager = db_manager
        self.user_id = user_id
        self.secrets = load_secrets(secrets_path)
        withings_config = self.secrets.get("withings", {})
        self.client_id = withings_config.get("client_id", "")
        self.client_secret = withings_config.get("client_secret", "")
        self.redirect_uri = withings_config.get("redirect_uri", "")
        self.tokens = self._load_tokens()
    
    def _load_tokens(self) -> Dict[str, Any]:
        """Supabase からトークンを読み込む"""
        try:
            token_data = self.db_manager.get_token(self.user_id, self.PROVIDER)
            return token_data if token_data else {}
        except Exception:
            return {}
    
    def _save_tokens(self, tokens: Dict[str, Any]):
        """Supabase にトークンを保存する"""
        try:
            self.db_manager.save_token(self.user_id, self.PROVIDER, tokens)
        except Exception:
            pass
        self.tokens = tokens
    
    def get_authorization_url(self, state: str = "random_state") -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "user.metrics",
            "state": state
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"
    
    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        data = {
            "action": "requesttoken",
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri
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
                "created_at": datetime.now(JST).isoformat(),
                "expires_at": (datetime.now(JST) + timedelta(seconds=body.get("expires_in", 10800))).isoformat()
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
            "client_secret": self.client_secret,
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
                "created_at": datetime.now(JST).isoformat(),
                "expires_at": (datetime.now(JST) + timedelta(seconds=body.get("expires_in", 10800))).isoformat()
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
            if datetime.now(JST) >= expires_datetime - timedelta(minutes=5):
                try:
                    self.refresh_access_token()
                except Exception:
                    return None
        
        return self.tokens.get("access_token")
    
    def is_authenticated(self) -> bool:
        return self.get_valid_access_token() is not None
    
    def get_user_id(self) -> Optional[str]:
        return self.tokens.get("user_id")
    
    def clear_tokens(self):
        try:
            self.db_manager.delete_token(self.user_id, self.PROVIDER)
        except Exception:
            pass
        self.tokens = {}
