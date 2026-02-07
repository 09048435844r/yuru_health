import os
import yaml
from typing import Dict, Any


def load_secrets(secrets_path: str = "config/secrets.yaml") -> Dict[str, Any]:
    """
    シークレット情報を読み込む。
    - ローカル環境: YAMLファイルから読み込む
    - クラウド環境 (Streamlit Cloud): st.secrets から読み込む
    """
    if os.path.exists(secrets_path):
        with open(secrets_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    else:
        try:
            import streamlit as st
            return dict(st.secrets)
        except Exception:
            return {}
