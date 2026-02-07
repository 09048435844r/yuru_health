import streamlit as st
from typing import Dict, Any, Optional, List
from src.utils.secrets_loader import load_secrets

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False


class GoogleOAuth:
    SCOPES = [
        "https://www.googleapis.com/auth/fitness.activity.read",
        "https://www.googleapis.com/auth/fitness.body.read",
        "https://www.googleapis.com/auth/fitness.sleep.read",
    ]
    
    def __init__(self, secrets_path: str = "config/secrets.yaml"):
        self.secrets = load_secrets(secrets_path)
        self.google_config = self.secrets.get("google", {})
        self.client_id = self.google_config.get("client_id", "")
        self.client_secret = self.google_config.get("client_secret", "")
        self.redirect_uris = self.google_config.get("redirect_uris", ["http://localhost:8501/"])
    
    def _get_redirect_uri(self) -> str:
        """現在の環境に合ったリダイレクトURIを返す"""
        try:
            # Streamlit Cloud の場合、実際のURLを使用
            if hasattr(st, "context") and hasattr(st.context, "headers"):
                host = st.context.headers.get("Host", "")
                if host and "localhost" not in host:
                    for uri in self.redirect_uris:
                        if "localhost" not in uri:
                            return uri
        except Exception:
            pass
        # ローカル環境
        for uri in self.redirect_uris:
            if "localhost" in uri:
                return uri
        return self.redirect_uris[0] if self.redirect_uris else "http://localhost:8501/"
    
    def _build_client_config(self) -> Dict[str, Any]:
        """Google OAuth用のクライアント設定を構築"""
        return {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": self.redirect_uris,
            }
        }
    
    def is_available(self) -> bool:
        """Google OAuth が利用可能か確認"""
        return (
            GOOGLE_AUTH_AVAILABLE
            and bool(self.client_id)
            and self.client_id != "your_google_client_id"
        )
    
    def is_authenticated(self) -> bool:
        """認証済みか確認"""
        creds = st.session_state.get("google_credentials")
        if creds is None:
            return False
        if isinstance(creds, Credentials):
            return creds.valid or creds.expired
        return False
    
    def get_credentials(self) -> Optional["Credentials"]:
        """session_state から Credentials を取得"""
        if not GOOGLE_AUTH_AVAILABLE:
            return None
        creds = st.session_state.get("google_credentials")
        if isinstance(creds, Credentials):
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                try:
                    creds.refresh(Request())
                    st.session_state["google_credentials"] = creds
                except Exception:
                    st.session_state.pop("google_credentials", None)
                    return None
            return creds if creds.valid else None
        return None
    
    def get_authorization_url(self) -> str:
        """認証URLを生成"""
        redirect_uri = self._get_redirect_uri()
        flow = Flow.from_client_config(
            self._build_client_config(),
            scopes=self.SCOPES,
            redirect_uri=redirect_uri,
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        st.session_state["google_oauth_state"] = state
        st.session_state["google_oauth_redirect_uri"] = redirect_uri
        return auth_url
    
    def exchange_code_for_token(self, code: str) -> bool:
        """認証コードをトークンに交換"""
        if not GOOGLE_AUTH_AVAILABLE:
            return False
        try:
            redirect_uri = st.session_state.get("google_oauth_redirect_uri", self._get_redirect_uri())
            flow = Flow.from_client_config(
                self._build_client_config(),
                scopes=self.SCOPES,
                redirect_uri=redirect_uri,
            )
            flow.fetch_token(code=code)
            st.session_state["google_credentials"] = flow.credentials
            return True
        except Exception as e:
            st.error(f"Google認証エラー: {e}")
            return False
    
    def logout(self):
        """認証情報をクリア"""
        st.session_state.pop("google_credentials", None)
        st.session_state.pop("google_oauth_state", None)
        st.session_state.pop("google_oauth_redirect_uri", None)
