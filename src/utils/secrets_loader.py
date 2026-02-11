import os
import yaml
from typing import Dict, Any


def load_secrets(secrets_path: str = "config/secrets.yaml") -> Dict[str, Any]:
    """
    シークレット情報を読み込む（優先順位）:
    1. 環境変数 (os.getenv) — パブリックリポジトリ / CI / Streamlit Cloud 向け
    2. YAML ファイル (config/secrets.yaml) — ローカル開発向け
    3. st.secrets — Streamlit Cloud TOML フォールバック
    """
    secrets = _load_from_env()
    if secrets:
        return secrets

    if os.path.exists(secrets_path):
        with open(secrets_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    try:
        import streamlit as st
        return dict(st.secrets)
    except Exception:
        return {}


def _load_from_env() -> Dict[str, Any]:
    """環境変数から secrets 辞書を構築する。1つでもセットされていれば有効とみなす。"""
    env_map = {
        "SUPABASE_URL": ("supabase", "url"),
        "SUPABASE_KEY": ("supabase", "key"),
        "OURA_PERSONAL_TOKEN": ("oura", "personal_token"),
        "GEMINI_API_KEY": ("gemini", "api_key"),
        "OPENWEATHERMAP_API_KEY": ("openweathermap", "api_key"),
        "OPENWEATHERMAP_DEFAULT_LAT": ("openweathermap", "default_lat"),
        "OPENWEATHERMAP_DEFAULT_LON": ("openweathermap", "default_lon"),
        "WITHINGS_CLIENT_ID": ("withings", "client_id"),
        "WITHINGS_CLIENT_SECRET": ("withings", "client_secret"),
        "WITHINGS_REDIRECT_URI": ("withings", "redirect_uri"),
        "GOOGLE_CLIENT_ID": ("google", "client_id"),
        "GOOGLE_CLIENT_SECRET": ("google", "client_secret"),
        "GOOGLE_REDIRECT_URI_CLOUD": ("google", "redirect_uris_cloud"),
        "GOOGLE_REDIRECT_URI_LOCAL": ("google", "redirect_uris_local"),
        "SWITCHBOT_TOKEN": ("switchbot", "token"),
        "SWITCHBOT_SECRET": ("switchbot", "secret"),
        "SWITCHBOT_DEVICE_ID": ("switchbot", "device_id"),
        "GEMINI_MODEL_NAME": ("gemini", "model_name"),
    }

    result: Dict[str, Any] = {}
    found_any = False

    for env_key, (section, key) in env_map.items():
        value = os.getenv(env_key)
        if value is not None:
            found_any = True
            result.setdefault(section, {})[key] = value

    if not found_any:
        return {}

    # 特殊処理: float 変換
    for float_key in ("default_lat", "default_lon"):
        owm = result.get("openweathermap", {})
        if float_key in owm:
            try:
                owm[float_key] = float(owm[float_key])
            except (ValueError, TypeError):
                pass

    # 特殊処理: Google redirect_uris をリストに組み立て
    google = result.get("google", {})
    uris = []
    if google.pop("redirect_uris_cloud", None):
        uris.append(os.getenv("GOOGLE_REDIRECT_URI_CLOUD", ""))
    if google.pop("redirect_uris_local", None):
        uris.append(os.getenv("GOOGLE_REDIRECT_URI_LOCAL", ""))
    if uris:
        google["redirect_uris"] = uris

    return result
