"""
Data fetching utilities for YuruHealth
データ取得ロジック
"""
from typing import Dict, Any
from src.database_manager import DatabaseManager


def fetch_latest_data(db_manager: DatabaseManager, user_id: str = "user_001") -> Dict[str, Any]:
    """最新の健康データを取得"""
    weight_data = db_manager.get_weight_data(user_id=user_id, limit=30)
    oura_data = db_manager.get_oura_data(user_id=user_id, limit=30)
    
    latest_weight = weight_data[0] if weight_data else None
    latest_oura = oura_data[0] if oura_data else None
    
    return {
        "weight_data": weight_data,
        "oura_data": oura_data,
        "latest_weight": latest_weight,
        "latest_oura": latest_oura
    }


def get_google_fit_sleep_policy() -> str:
    """Google Fit 睡眠データの source_policy を取得"""
    try:
        from src.utils.config_loader import load_settings
        settings = load_settings()
        parser_cfg = ((settings.get("google_fit") or {}).get("sleep_parser") or {}) if isinstance(settings, dict) else {}
        return parser_cfg.get("source_policy", "min")
    except Exception:
        return "min"
