"""
Data formatting utilities for YuruHealth
データフォーマット関数
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

JST = timezone(timedelta(hours=9))


def to_jst_date_text(value: Any) -> str:
    """DB時刻(UTC/naive/aware)をJSTに変換して YYYY-MM-DD を返す"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10] if len(text) >= 10 else ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).strftime("%Y-%m-%d")


def to_jst_hour(value: Any) -> int:
    """DB時刻をJSTの時(0-23)に変換"""
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).hour


def minutes_to_hhmm(value: Any) -> str:
    """分数を h:mm 形式に変換"""
    try:
        total = int(value)
    except (TypeError, ValueError):
        return "0:00"
    if total < 0:
        total = 0
    hours = total // 60
    mins = total % 60
    return f"{hours}:{mins:02d}"


def extract_sleep_chosen_app(raw_data: Any) -> str:
    """Google Fit 睡眠データから採用アプリを抽出"""
    payload: Dict[str, Any] = {}
    if isinstance(raw_data, dict):
        payload = raw_data
    elif isinstance(raw_data, str):
        try:
            import json
            payload = json.loads(raw_data)
        except Exception:
            pass
    
    app = payload.get("chosen_app")
    return str(app) if app else "-"
