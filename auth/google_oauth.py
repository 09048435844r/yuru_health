import logging
import streamlit as st
from typing import Dict, Any, Optional
from src.utils.secrets_loader import load_secrets

logger = logging.getLogger(__name__)

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False


class GoogleOAuth:
    SCOPES = [
        "https://www.googleapis.com/auth/fitness.activity.read",
        "https://www.googleapis.com/auth/fitness.body.read",
        "https://www.googleapis.com/auth/fitness.sleep.read",
    ]
    PROVIDER = "google"
    
    def __init__(self, db_manager, secrets_path: str = "config/secrets.yaml", user_id: str = "user_001"):
        self.db_manager = db_manager
        self.user_id = user_id
        self.secrets = load_secrets(secrets_path)
        self.google_config = self.secrets.get("google", {})
        self.client_id = self.google_config.get("client_id", "")
        self.client_secret = self.google_config.get("client_secret", "")
        self.redirect_uris = self.google_config.get("redirect_uris", [])
        self._restore_credentials()
    
    def _credentials_to_dict(self, creds: "Credentials") -> Dict[str, Any]:
        """Credentials オブジェクトを dict に変換"""
        return {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else self.SCOPES,
        }
    
    def _dict_to_credentials(self, data: Dict[str, Any]) -> Optional["Credentials"]:
        """dict から Credentials オブジェクトを復元"""
        if not GOOGLE_AUTH_AVAILABLE or not data:
            return None
        try:
            return Credentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=data.get("client_id", self.client_id),
                client_secret=data.get("client_secret", self.client_secret),
                scopes=data.get("scopes", self.SCOPES),
            )
        except Exception:
            return None
    
    def _restore_credentials(self):
        """Supabase からトークンを復元して session_state にセット"""
        if st.session_state.get("google_credentials"):
            return
        try:
            token_data = self.db_manager.get_token(self.user_id, self.PROVIDER)
            if token_data:
                creds = self._dict_to_credentials(token_data)
                if creds:
                    st.session_state["google_credentials"] = creds
                    logger.info("Google credentials restored from Supabase")
        except Exception:
            pass
    
    def ensure_credentials(self):
        """毎回のページロードで呼び出し、session_state にトークンがなければ DB から復元し、期限切れならリフレッシュする"""
        if not GOOGLE_AUTH_AVAILABLE:
            return
        
        creds = st.session_state.get("google_credentials")
        
        # session_state にない → DB から復元
        if creds is None:
            try:
                token_data = self.db_manager.get_token(self.user_id, self.PROVIDER)
                if token_data:
                    creds = self._dict_to_credentials(token_data)
                    if creds:
                        st.session_state["google_credentials"] = creds
                        logger.info("Google credentials hydrated from Supabase")
            except Exception as e:
                logger.info(f"Google token hydration failed: {e}")
                return
        
        if creds is None:
            return
        
        # 期限切れ → リフレッシュ
        if not isinstance(creds, Credentials):
            return
        
        if creds.valid:
            return
        
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_credentials(creds)
                logger.info("Google credentials refreshed and saved")
            except Exception as e:
                logger.info(f"Google token refresh failed: {e}")
                st.session_state.pop("google_credentials", None)
                return
    
    def _save_credentials(self, creds: "Credentials"):
        """Credentials を Supabase と session_state に保存"""
        st.session_state["google_credentials"] = creds
        try:
            self.db_manager.save_token(self.user_id, self.PROVIDER, self._credentials_to_dict(creds))
        except Exception:
            pass
    
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
        return self.redirect_uris[0] if self.redirect_uris else ""
    
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
        """認証済みか確認（有効またはリフレッシュ可能なトークンがある場合 True）"""
        if not GOOGLE_AUTH_AVAILABLE:
            return False
        creds = st.session_state.get("google_credentials")
        if creds is None:
            return False
        if isinstance(creds, Credentials):
            if creds.valid:
                return True
            if creds.expired and creds.refresh_token:
                return True
        return False
    
    def get_credentials(self) -> Optional["Credentials"]:
        """session_state から Credentials を取得し、必要なら refresh"""
        if not GOOGLE_AUTH_AVAILABLE:
            return None
        creds = st.session_state.get("google_credentials")
        if isinstance(creds, Credentials):
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self._save_credentials(creds)
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
            self._save_credentials(flow.credentials)
            return True
        except Exception as e:
            st.error(f"Google認証エラー: {e}")
            return False
    
    def logout(self):
        """認証情報をクリア"""
        st.session_state.pop("google_credentials", None)
        st.session_state.pop("google_oauth_state", None)
        st.session_state.pop("google_oauth_redirect_uri", None)
        try:
            self.db_manager.delete_token(self.user_id, self.PROVIDER)
        except Exception:
            pass
