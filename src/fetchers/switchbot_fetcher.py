import hashlib
import hmac
import base64
import logging
import time
import uuid
import requests
from typing import Dict, Any, Optional
from datetime import datetime
from src.utils.secrets_loader import load_secrets

logger = logging.getLogger(__name__)


class SwitchBotFetcher:
    """
    SwitchBot API v1.1 を使用した環境データ取得クラス
    CO2濃度、気温、湿度などを取得する
    """
    
    BASE_URL = "https://api.switch-bot.com/v1.1"
    
    def __init__(self, secrets_path: str = "config/secrets.yaml", db_manager=None):
        self.secrets = load_secrets(secrets_path)
        self.db_manager = db_manager
        switchbot_config = self.secrets.get("switchbot", {})
        self.token = switchbot_config.get("token", "")
        self.secret = switchbot_config.get("secret", "")
        self.device_id = switchbot_config.get("device_id", "")
    
    def is_available(self) -> bool:
        """API利用可能か確認"""
        return bool(self.token and self.secret and self.device_id)
    
    def _make_headers(self) -> Dict[str, str]:
        """SwitchBot API v1.1 認証ヘッダーを生成"""
        t = str(int(round(time.time() * 1000)))
        nonce = str(uuid.uuid4())
        string_to_sign = f"{self.token}{t}{nonce}"
        sign = base64.b64encode(
            hmac.new(
                self.secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return {
            "Authorization": self.token,
            "sign": sign,
            "t": t,
            "nonce": nonce,
            "Content-Type": "application/json",
        }
    
    def fetch_device_status(self) -> Optional[Dict[str, Any]]:
        """
        デバイスのステータスを取得し、Data Lake に保存する
        
        Returns:
            dict: デバイスステータス（成功時）、None（失敗時）
        """
        if not self.is_available():
            logger.info("SwitchBotFetcher: credentials not configured, skipping")
            return None
        
        try:
            url = f"{self.BASE_URL}/devices/{self.device_id}/status"
            response = requests.get(url, headers=self._make_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("statusCode") != 100:
                logger.info(f"SwitchBot API error: statusCode={data.get('statusCode')}, message={data.get('message')}")
                return None
            
            body = data.get("body", {})
            
            # Data Lake に生データを保存
            if self.db_manager:
                self.db_manager.save_raw_data(
                    user_id="system",
                    source="switchbot",
                    category="environment",
                    payload=body,
                )
                logger.info("SwitchBot: environment data saved to Data Lake")
            else:
                logger.info("SwitchBotFetcher: db_manager is None, skipping save")
            
            return body
        
        except requests.exceptions.Timeout:
            logger.info("SwitchBot API request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.info(f"SwitchBot API request failed: {e}")
            return None
        except Exception as e:
            logger.info(f"SwitchBot unexpected error: {e}")
            return None
