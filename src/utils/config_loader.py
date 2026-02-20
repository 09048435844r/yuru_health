"""設定ファイル (settings.yaml) と st.secrets を統合して返すユーティリティ。

優先順位:
  1. config/settings.yaml  — ベース設定（Git 管理対象）
  2. st.secrets             — 機密情報の上書き・追加（Streamlit Cloud TOML）

両者を再帰的にディープマージし、st.secrets 側の値が優先される。
"""
import logging
import yaml
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path("config/settings.yaml")


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """base に override を再帰的にマージしたコピーを返す。override 側が優先。"""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml_settings(path: Path = _SETTINGS_PATH) -> Dict[str, Any]:
    """settings.yaml を読み込む。ファイルが無ければ空辞書。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("config/settings.yaml not found — using defaults")
        return {}
    except Exception as e:
        logger.warning(f"Failed to load settings.yaml: {e}")
        return {}


def _load_st_secrets() -> Dict[str, Any]:
    """st.secrets を通常の dict に変換して返す。利用不可なら空辞書。"""
    try:
        import streamlit as st
        # st.secrets は AttrDict 風オブジェクトなので再帰的に dict 化
        converted = _to_dict(st.secrets)
        if isinstance(converted, dict):
            return converted
        logger.info("st.secrets is not available as dict; fallback to settings.yaml only")
        return {}
    except Exception as e:
        logger.info(f"st.secrets unavailable; fallback to settings.yaml only: {e}")
        return {}


def _to_dict(obj: Any) -> Any:
    """st.secrets の AttrDict を通常の dict に再帰変換する。"""
    try:
        # Mapping 型なら dict 化
        items = obj.items() if hasattr(obj, "items") else None
        if items is not None:
            return {k: _to_dict(v) for k, v in items}
    except Exception:
        pass
    return obj


def load_settings(settings_path: Path = _SETTINGS_PATH) -> Dict[str, Any]:
    """settings.yaml と st.secrets をディープマージした統合設定を返す。"""
    base = _load_yaml_settings(settings_path)
    secrets = _load_st_secrets()
    merged = _deep_merge(base, secrets)
    return merged
