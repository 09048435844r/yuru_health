import logging
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
import streamlit as st
from typing import Dict, Any, Optional
from src.utils.secrets_loader import load_secrets
from auth.exceptions import OAuthRefreshError

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
    OAUTH_PENDING_KEY = "google_oauth_pending"
    OAUTH_PENDING_PROVIDER = "google_pkce_pending"
    OAUTH_PENDING_TTL_MINUTES = 15
    
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
    
    def ensure_credentials(self, strict: bool = False):
        """毎回のページロードで呼び出し、session_state にトークンがなければ DB から復元し、期限切れならリフレッシュする"""
        if not GOOGLE_AUTH_AVAILABLE:
            if strict:
                raise OAuthRefreshError("Google OAuth dependencies are not installed")
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
                if strict:
                    raise OAuthRefreshError(f"Google token hydration failed: {e}") from e
                return
        
        if creds is None:
            if strict:
                raise OAuthRefreshError("Google token not found in oauth_tokens")
            return
        
        # 期限切れ → リフレッシュ
        if not isinstance(creds, Credentials):
            if strict:
                raise OAuthRefreshError("Google credentials payload is invalid")
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
                if strict:
                    raise OAuthRefreshError(f"Google token refresh failed: {e}") from e
                return
    
    def _save_credentials(self, creds: "Credentials"):
        """Credentials を Supabase と session_state に保存"""
        st.session_state["google_credentials"] = creds
        try:
            self.db_manager.save_token(self.user_id, self.PROVIDER, self._credentials_to_dict(creds))
        except Exception:
            pass

    def _normalize_redirect_uri(self, uri: str) -> str:
        """redirect URI を正規化する。localhost は末尾スラッシュを付与する。"""
        normalized = str(uri or "").strip()
        if not normalized:
            return ""
        if "localhost" in normalized and not normalized.endswith("/"):
            return normalized + "/"
        return normalized

    def _generate_pkce_pair(self) -> tuple[str, str]:
        """PKCE 用の code_verifier / code_challenge(S256) を生成する。"""
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("utf-8")).digest()
        ).decode("utf-8").rstrip("=")
        return verifier, challenge

    def _save_pending_oauth(self, pending: Dict[str, Any]) -> None:
        try:
            self.db_manager.save_token(self.user_id, self.OAUTH_PENDING_PROVIDER, pending)
        except Exception as e:
            logger.warning(f"Google pending oauth save failed: {e}")

    def _load_pending_oauth(self) -> Optional[Dict[str, Any]]:
        try:
            pending = self.db_manager.get_token(self.user_id, self.OAUTH_PENDING_PROVIDER)
        except Exception as e:
            logger.warning(f"Google pending oauth load failed: {e}")
            return None

        if not isinstance(pending, dict):
            return None

        required = {"state", "code_verifier", "redirect_uri", "auth_url"}
        if not required.issubset(pending.keys()):
            return None

        expires_at = pending.get("expires_at")
        if expires_at:
            try:
                expires_dt = datetime.fromisoformat(str(expires_at))
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= expires_dt.astimezone(timezone.utc):
                    self.clear_pending_oauth()
                    return None
            except ValueError:
                self.clear_pending_oauth()
                return None

        return pending

    def _get_pending_oauth(self) -> Optional[Dict[str, Any]]:
        return self._load_pending_oauth()

    def clear_pending_oauth(self):
        try:
            self.db_manager.delete_token(self.user_id, self.OAUTH_PENDING_PROVIDER)
        except Exception as e:
            logger.warning(f"Google pending oauth delete failed: {e}")
        st.session_state.pop(self.OAUTH_PENDING_KEY, None)
        st.session_state.pop("google_oauth_state", None)
        st.session_state.pop("google_oauth_redirect_uri", None)

    def is_expected_state(self, state: Optional[str]) -> bool:
        pending = self._get_pending_oauth()
        return bool(pending and state and state == pending.get("state"))
    
    def _get_redirect_uri(self) -> str:
        """現在の環境に合ったリダイレクトURIを返す"""
        try:
            # Streamlit Cloud の場合、実際のURLを使用
            if hasattr(st, "context") and hasattr(st.context, "headers"):
                host = st.context.headers.get("Host", "")
                if host and "localhost" not in host:
                    for uri in self.redirect_uris:
                        if "localhost" not in uri:
                            return self._normalize_redirect_uri(uri)
        except Exception:
            pass
        # ローカル環境
        localhost_uris = [self._normalize_redirect_uri(uri) for uri in self.redirect_uris if "localhost" in uri]
        localhost_uris = [uri for uri in localhost_uris if uri]
        if localhost_uris:
            slash_uris = [uri for uri in localhost_uris if uri.endswith("/")]
            return slash_uris[0] if slash_uris else localhost_uris[0]

        for uri in self.redirect_uris:
            if "localhost" in uri:
                return self._normalize_redirect_uri(uri)
        return self._normalize_redirect_uri(self.redirect_uris[0] if self.redirect_uris else "")
    
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
    
    def get_credentials(self, strict: bool = False) -> Optional["Credentials"]:
        """session_state から Credentials を取得し、必要なら refresh"""
        if not GOOGLE_AUTH_AVAILABLE:
            if strict:
                raise OAuthRefreshError("Google OAuth dependencies are not installed")
            return None
        creds = st.session_state.get("google_credentials")
        if creds is None:
            if strict:
                raise OAuthRefreshError("Google credentials not found in session_state")
            return None
        if isinstance(creds, Credentials):
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self._save_credentials(creds)
                except Exception as e:
                    st.session_state.pop("google_credentials", None)
                    if strict:
                        raise OAuthRefreshError(f"Google token refresh failed: {e}") from e
                    return None
            if creds.valid:
                return creds
            if strict:
                raise OAuthRefreshError("Google credentials are invalid")
            return None
        if strict:
            raise OAuthRefreshError("Google credentials object type is invalid")
        return None
    
    def get_authorization_url(self) -> str:
        """認証URLを生成"""
        if not self.is_available():
            return ""

        pending = self._get_pending_oauth()
        if pending:
            return str(pending.get("auth_url", ""))

        redirect_uri = self._get_redirect_uri()
        state = secrets.token_urlsafe(24)
        code_verifier, code_challenge = self._generate_pkce_pair()
        flow = Flow.from_client_config(
            self._build_client_config(),
            scopes=self.SCOPES,
            redirect_uri=redirect_uri,
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )
        now_utc = datetime.now(timezone.utc)
        pending_payload = {
            "state": state,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "auth_url": auth_url,
            "created_at": now_utc.isoformat(),
            "expires_at": (now_utc + timedelta(minutes=self.OAUTH_PENDING_TTL_MINUTES)).isoformat(),
        }
        self._save_pending_oauth(pending_payload)
        return auth_url
    
    def exchange_code_for_token(self, code: str, state: Optional[str] = None) -> bool:
        """認証コードをトークンに交換"""
        if not GOOGLE_AUTH_AVAILABLE:
            return False
        try:
            pending = self._get_pending_oauth()
            if not pending:
                raise RuntimeError("認証セッションが見つかりません。Google Fit ログインをやり直してください。")

            expected_state = str(pending.get("state", ""))
            if not state or state != expected_state:
                raise RuntimeError("state 検証に失敗しました。Google Fit ログインをやり直してください。")

            redirect_uri = str(pending.get("redirect_uri") or self._get_redirect_uri())
            flow = Flow.from_client_config(
                self._build_client_config(),
                scopes=self.SCOPES,
                redirect_uri=redirect_uri,
            )
            flow.code_verifier = str(pending.get("code_verifier", ""))
            flow.fetch_token(code=code)
            self._save_credentials(flow.credentials)
            self.clear_pending_oauth()
            return True
        except Exception as e:
            st.error(f"Google認証エラー: {e}")
            return False
    
    def logout(self):
        """認証情報をクリア"""
        st.session_state.pop("google_credentials", None)
        self.clear_pending_oauth()
        try:
            self.db_manager.delete_token(self.user_id, self.PROVIDER)
        except Exception:
            pass
