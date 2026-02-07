import json
import requests
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from src.utils.secrets_loader import load_secrets


class WeatherFetcher:
    """
    OpenWeatherMap APIを使用した天気データ取得クラス
    """
    
    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
    
    def __init__(self, secrets_path: str = "config/secrets.yaml"):
        self.secrets = load_secrets(secrets_path)
        self.api_key = self.secrets.get("openweathermap", {}).get("api_key")
        self.default_lat = self.secrets.get("openweathermap", {}).get("default_lat")
        self.default_lon = self.secrets.get("openweathermap", {}).get("default_lon")
    
    def is_available(self) -> bool:
        """API利用可能か確認"""
        return self.api_key is not None
    
    @property
    def last_error(self):
        return getattr(self, '_last_error', None)
    
    def fetch_weather(self, lat: Optional[float] = None, lon: Optional[float] = None) -> Dict[str, Any]:
        """
        天気データを取得する
        
        Args:
            lat: 緯度（Noneの場合はデフォルト値を使用）
            lon: 経度（Noneの場合はデフォルト値を使用）
            
        Returns:
            dict: 天気データ（source, lat, lon, weather_summary, temp, humidity, pressure, raw_data）
        """
        if not self.is_available():
            return {}
        
        # 座標の決定とソースの判定
        if lat is not None and lon is not None:
            source = "browser_gps"
        elif self.default_lat is not None and self.default_lon is not None:
            lat = self.default_lat
            lon = self.default_lon
            source = "config_fallback"
        else:
            return {}
        
        self._last_error = None
        try:
            params = {
                "lat": lat,
                "lon": lon,
                "appid": self.api_key,
                "units": "metric",
                "lang": "ja"
            }
            
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            
            if response.status_code != 200:
                self._last_error = f"API error {response.status_code}: {response.text}"
            
            response.raise_for_status()
            data = response.json()
            
            # レスポンスをパース
            weather_desc = data.get("weather", [{}])[0].get("description", "不明")
            weather_icon = self._get_weather_emoji(data.get("weather", [{}])[0].get("icon", ""))
            temp = data.get("main", {}).get("temp")
            humidity = data.get("main", {}).get("humidity")
            pressure = data.get("main", {}).get("pressure")
            city_name = data.get("name", "")
            
            return {
                "source": source,
                "latitude": lat,
                "longitude": lon,
                "weather_summary": f"{weather_icon} {weather_desc}",
                "temp": temp,
                "humidity": humidity,
                "pressure": pressure,
                "city_name": city_name,
                "raw_data": json.dumps(data, ensure_ascii=False),
                "timestamp": datetime.now().isoformat()
            }
        
        except requests.exceptions.Timeout:
            self._last_error = "API request timed out"
            return {}
        except requests.exceptions.RequestException as e:
            self._last_error = f"API request failed: {e}"
            return {}
        except Exception as e:
            self._last_error = f"Unexpected error: {e}"
            return {}
    
    def _get_weather_emoji(self, icon_code: str) -> str:
        """OpenWeatherMapのアイコンコードから絵文字を返す"""
        emoji_map = {
            "01d": "☀️", "01n": "🌙",
            "02d": "⛅", "02n": "☁️",
            "03d": "☁️", "03n": "☁️",
            "04d": "☁️", "04n": "☁️",
            "09d": "🌧️", "09n": "🌧️",
            "10d": "🌦️", "10n": "🌧️",
            "11d": "⛈️", "11n": "⛈️",
            "13d": "🌨️", "13n": "🌨️",
            "50d": "🌫️", "50n": "🌫️",
        }
        return emoji_map.get(icon_code, "🌤️")
