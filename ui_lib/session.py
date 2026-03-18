"""
Session management utilities for YuruHealth
セッション状態の管理とキャッシュ
"""
import streamlit as st
from datetime import timezone, timedelta
from src.database_manager import DatabaseManager
from auth.withings_oauth import WithingsOAuth
from auth.google_oauth import GoogleOAuth
from src.evaluators.gemini_evaluator import GeminiEvaluator
from src.utils.config_loader import load_settings

JST = timezone(timedelta(hours=9))


def get_database_manager() -> DatabaseManager:
    """DatabaseManager のシングルトンインスタンスを取得"""
    obj = st.session_state.get("_db_manager")
    required_attrs = (
        "_payload_hash",
        "get_daily_insight_history",
        "save_daily_insight",
        "get_latest_daily_insight",
        "insert_intake_log",
        "get_intake_logs",
        "get_intake_summary_by_date",
        "delete_intake_log",
    )
    if obj is None or any(not hasattr(obj, attr) for attr in required_attrs):
        st.session_state["_db_manager"] = DatabaseManager("config/secrets.yaml")
    return st.session_state["_db_manager"]


def get_withings_oauth(db_manager: DatabaseManager) -> WithingsOAuth:
    """WithingsOAuth のシングルトンインスタンスを取得"""
    if "_withings_oauth" not in st.session_state:
        st.session_state["_withings_oauth"] = WithingsOAuth(db_manager)
    return st.session_state["_withings_oauth"]


def get_google_oauth(db_manager: DatabaseManager) -> GoogleOAuth:
    """GoogleOAuth のシングルトンインスタンスを取得"""
    obj = st.session_state.get("_google_oauth")
    if obj is None or not hasattr(obj, "ensure_credentials"):
        st.session_state["_google_oauth"] = GoogleOAuth(db_manager)
    return st.session_state["_google_oauth"]


@st.cache_resource
def load_gemini_settings() -> dict:
    """Gemini設定をキャッシュして取得"""
    settings = load_settings()
    gemini = settings.get("gemini", {})
    if "available_models" not in gemini:
        gemini["available_models"] = [gemini.get("model_name", "gemini-2.0-flash")]
    return gemini


@st.cache_resource
def get_gemini_evaluator(model_name: str) -> GeminiEvaluator:
    """GeminiEvaluator のキャッシュインスタンスを取得"""
    return GeminiEvaluator({}, model_name=model_name)


def has_oauth_token(db_manager: DatabaseManager, provider: str, user_id: str = "user_001") -> bool:
    """oauth_tokens テーブルに provider のトークンが存在するかを返す"""
    try:
        return bool(db_manager.get_token(user_id, provider))
    except Exception:
        return False
