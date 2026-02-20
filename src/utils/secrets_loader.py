import os
import re
import yaml
from typing import Dict, Any


def load_secrets(secrets_path: str = "config/secrets.yaml") -> Dict[str, Any]:
    """
    シークレット情報を読み込む（優先順位）:
    1. 環境変数 (os.getenv) — パブリックリポジトリ / CI / Streamlit Cloud 向け
    2. YAML ファイル (config/secrets.yaml) — ローカル開発向け
    3. st.secrets — Streamlit Cloud TOML フォールバック
    """
    # 1) YAML（ローカル）
    yaml_secrets: Dict[str, Any] = {}
    if os.path.exists(secrets_path):
        with open(secrets_path, "r", encoding="utf-8") as f:
            yaml_secrets = yaml.safe_load(f) or {}

    # 2) 環境変数（CI/Cloud）で上書き
    env_secrets = _load_from_env()
    merged = _deep_merge(yaml_secrets, env_secrets)

    # 3) 最後のフォールバック: st.secrets
    if not merged:
        try:
            import streamlit as st
            merged = dict(st.secrets)
        except Exception:
            merged = {}

    return _normalize_and_validate(merged)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """辞書を再帰的に merge する（override 優先）。"""
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _normalize_supabase_url(url: str) -> str:
    """SUPABASE_URL を正規化する。壊れた .sup...abase.co も救済する。"""
    u = (url or "").strip().strip("\"'")
    if not u:
        return ""

    # 正常系
    if re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co", u, flags=re.IGNORECASE):
        return u

    # 破損系救済: https://<ref>.sup<garbage>abase.co -> https://<ref>.supabase.co
    m = re.fullmatch(r"https://([a-z0-9-]+)\.sup.*abase\.co", u, flags=re.IGNORECASE)
    if m:
        return f"https://{m.group(1)}.supabase.co"

    return u


def _extract_supabase_injected_fragment(url: str) -> str:
    """壊れた URL (sup<fragment>abase.co) から fragment を抽出する。"""
    u = (url or "").strip().strip("\"'")
    m = re.fullmatch(r"https://[a-z0-9-]+\.sup([A-Za-z0-9_-]+)abase\.co", u)
    return m.group(1) if m else ""


def _normalize_and_validate(secrets: Dict[str, Any]) -> Dict[str, Any]:
    supabase = secrets.get("supabase") if isinstance(secrets, dict) else None
    if isinstance(supabase, dict):
        raw_url = str(supabase.get("url", ""))
        normalized_url = _normalize_supabase_url(raw_url)
        supabase["url"] = normalized_url

        raw_key = str(supabase.get("key", "")).strip().strip("\"'")
        injected = _extract_supabase_injected_fragment(raw_url)

        # 破損例:
        # - URL: https://<ref>.sup<JWT-HEADER>abase.co
        # - KEY: .<JWT-PAYLOAD>.<SIGNATURE>
        # この場合、HEADER を URL から回収して復元する。
        if injected and raw_key.startswith(".") and raw_key.count(".") == 2:
            raw_key = f"{injected}{raw_key}"

        supabase["key"] = raw_key
    return secrets


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
