import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from src.utils.secrets_loader import load_secrets

# JST (UTC+9) タイムゾーン
JST = timezone(timedelta(hours=9))

logger = logging.getLogger(__name__)


def _now_jst() -> datetime:
    """現在の日本時間 (aware datetime) を返す"""
    return datetime.now(JST)


def _to_jst(iso_str: str) -> datetime:
    """ISO 文字列 (UTC / aware) を JST の aware datetime に変換する"""
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST)


def _to_jst_date(iso_str: str) -> str:
    """ISO 文字列から JST の日付文字列 (YYYY-MM-DD) を返す"""
    return _to_jst(iso_str).strftime("%Y-%m-%d")


def _to_jst_hour(iso_str: str) -> int:
    """ISO 文字列から JST の時 (0-23) を返す"""
    return _to_jst(iso_str).hour


class DatabaseManager:
    def __init__(self, secrets_path: str = "config/secrets.yaml"):
        self.secrets = load_secrets(secrets_path)
        self.supabase: Client = self._create_client()
        self.env = "cloud"
        self.db_config = {"type": "supabase"}
    
    def _create_client(self) -> Client:
        supabase_config = self.secrets.get("supabase", {})
        url = supabase_config.get("url", "")
        key = supabase_config.get("key", "")
        if not url or not key:
            raise ValueError("Supabase URL and Key must be set in config/secrets.yaml")
        return create_client(url, key)
    
    def connect(self):
        pass
    
    def close(self):
        pass
    
    def init_tables(self):
        pass
    
    def insert_weight_data(self, user_id: str, measured_at: str, weight_kg: float, raw_data: str):
        data = {
            "user_id": user_id,
            "measured_at": measured_at,
            "weight_kg": weight_kg,
            "raw_data": self._parse_raw_data(raw_data),
        }
        self.supabase.table("weight_data").insert(data).execute()
    
    def get_weight_data(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = self.supabase.table("weight_data").select("*").order("measured_at", desc=True).limit(limit)
        if user_id:
            query = query.eq("user_id", user_id)
        response = query.execute()
        return response.data
    
    def insert_oura_data(self, user_id: str, measured_at: str, activity_score: Optional[int], 
                        sleep_score: Optional[int], readiness_score: Optional[int], 
                        steps: Optional[int], total_sleep_duration: Optional[int], raw_data: str):
        data = {
            "user_id": user_id,
            "measured_at": measured_at,
            "activity_score": activity_score,
            "sleep_score": sleep_score,
            "readiness_score": readiness_score,
            "steps": steps,
            "total_sleep_duration": total_sleep_duration,
            "raw_data": self._parse_raw_data(raw_data),
        }
        self.supabase.table("oura_data").insert(data).execute()
    
    def get_oura_data(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = self.supabase.table("oura_data").select("*").order("measured_at", desc=True).limit(limit)
        if user_id:
            query = query.eq("user_id", user_id)
        response = query.execute()
        return response.data
    
    def insert_environmental_log(self, timestamp: str, source: str, 
                                  latitude: Optional[float], longitude: Optional[float],
                                  weather_summary: Optional[str], temp: Optional[float],
                                  humidity: Optional[int], pressure: Optional[int],
                                  raw_data: Optional[str]):
        data = {
            "timestamp": timestamp,
            "source": source,
            "latitude": latitude,
            "longitude": longitude,
            "weather_summary": weather_summary,
            "temp": temp,
            "humidity": humidity,
            "pressure": pressure,
            "raw_data": self._parse_raw_data(raw_data),
        }
        self.supabase.table("environmental_logs").insert(data).execute()
    
    def get_latest_environmental_log(self) -> Optional[Dict[str, Any]]:
        response = (
            self.supabase.table("environmental_logs")
            .select("*")
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    
    def insert_google_fit_data(self, user_id: str, date: str, data_type: str,
                               value: Any, raw_data: Any):
        data = {
            "user_id": user_id,
            "date": date,
            "data_type": data_type,
            "value": value,
            "raw_data": self._parse_raw_data(raw_data),
        }
        self.supabase.table("google_fit_data").insert(data).execute()
    
    def get_google_fit_data(self, user_id: Optional[str] = None, data_type: Optional[str] = None,
                            limit: int = 100) -> List[Dict[str, Any]]:
        query = self.supabase.table("google_fit_data").select("*").order("date", desc=True).limit(limit)
        if user_id:
            query = query.eq("user_id", user_id)
        if data_type:
            query = query.eq("data_type", data_type)
        response = query.execute()
        return response.data
    
    def get_data_arrival_history(self, days: int = 14) -> List[Dict[str, Any]]:
        """過去N日間の (source, fetched_date) リストを raw_data_lake から取得"""
        start_date = (_now_jst() - timedelta(days=days)).isoformat()
        response = (
            self.supabase.table("raw_data_lake")
            .select("source, fetched_at")
            .gte("fetched_at", start_date)
            .order("fetched_at", desc=True)
            .limit(10000)
            .execute()
        )
        # fetched_at (TIMESTAMPTZ / UTC) を JST 日付に変換して返す
        results = []
        seen = set()
        for row in response.data:
            fetched_date = _to_jst_date(row["fetched_at"])
            key = (row["source"], fetched_date)
            if key not in seen:
                seen.add(key)
                results.append({"source": row["source"], "fetched_date": fetched_date})
        return results

    def get_data_arrival_rich(self, days: int = 14) -> Dict[str, Dict[str, Any]]:
        """過去N日間の source×date ごとにサマリー統計と時系列サンプルを返す。

        Returns:
            {
              ("switchbot", "2026-02-11"): {
                "has_data": True,
                "timeseries": [{"hour": 0, "temp": 22.1, "humidity": 45}, ...],
                "summary": {"temp_avg": 22.5, "humidity_avg": 48, ...},
              },
              ("oura", "2026-02-11"): {
                "has_data": True,
                "badge": {"sleep_score": 82, "activity_score": 75, "readiness_score": 88},
              },
              ...
            }
        """
        start_date = (_now_jst() - timedelta(days=days)).isoformat()
        response = (
            self.supabase.table("raw_data_lake")
            .select("source, category, fetched_at, payload")
            .gte("fetched_at", start_date)
            .order("fetched_at", desc=True)
            .limit(10000)
            .execute()
        )

        # source×date ごとにレコードを集約 (fetched_at を JST 日付に変換)
        buckets: Dict[tuple, list] = {}
        for row in response.data:
            fetched_date = _to_jst_date(row["fetched_at"])
            key = (row["source"], fetched_date)
            buckets.setdefault(key, []).append(row)

        result: Dict[tuple, Dict[str, Any]] = {}
        for key, rows in buckets.items():
            source = key[0]
            entry: Dict[str, Any] = {"has_data": True}

            if source in ("switchbot", "weather"):
                entry.update(self._build_timeseries(source, rows))
            elif source == "oura":
                entry["badge"] = self._build_oura_badge(rows)
            elif source == "withings":
                entry["badge"] = self._build_withings_badge(rows)
            elif source == "google_fit":
                entry["badge"] = self._build_google_fit_badge(rows)

            result[key] = entry
        return result

    @staticmethod
    def _build_timeseries(source: str, rows: list) -> Dict[str, Any]:
        """SwitchBot / Weather の時系列データを構築"""
        timeseries = []
        for row in rows:
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            hour = _to_jst_hour(row.get("fetched_at", "1970-01-01T00:00:00+00:00"))

            if source == "switchbot":
                timeseries.append({
                    "hour": hour,
                    "temp": payload.get("temperature"),
                    "humidity": payload.get("humidity"),
                    "co2": payload.get("CO2"),
                })
            elif source == "weather":
                main = payload.get("main", {})
                timeseries.append({
                    "hour": hour,
                    "temp": main.get("temp"),
                    "humidity": main.get("humidity"),
                    "pressure": main.get("pressure"),
                })

        # サマリー統計
        summary = {}
        for field in ("temp", "humidity", "co2", "pressure"):
            vals = [p[field] for p in timeseries if p.get(field) is not None]
            if vals:
                summary[f"{field}_avg"] = round(sum(vals) / len(vals), 1)
                summary[f"{field}_min"] = round(min(vals), 1)
                summary[f"{field}_max"] = round(max(vals), 1)

        return {"timeseries": timeseries, "summary": summary}

    @staticmethod
    def _build_oura_badge(rows: list) -> Dict[str, Any]:
        """Oura の代表スコアを抽出"""
        badge: Dict[str, Any] = {}
        for row in rows:
            payload = row.get("payload", {})
            cat = row.get("category", "")
            if not isinstance(payload, dict):
                continue
            if cat == "sleep" and "score" in payload:
                badge["sleep_score"] = payload["score"]
            elif cat == "activity" and "score" in payload:
                badge["activity_score"] = payload["score"]
            elif cat == "readiness" and "score" in payload:
                badge["readiness_score"] = payload["score"]
            if "contributors" in payload and "steps" in payload.get("contributors", {}):
                pass
            if "steps" in payload:
                badge["steps"] = payload["steps"]
        return badge

    @staticmethod
    def _build_withings_badge(rows: list) -> Dict[str, Any]:
        """Withings の体重を抽出"""
        weights = []
        for row in rows:
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            w = payload.get("weight")
            if w is not None:
                weights.append(float(w))
            # measures 配列内の体重
            for m in payload.get("measures", []):
                if m.get("type") == 1:
                    val = m.get("value", 0) * (10 ** m.get("unit", 0))
                    if val > 0:
                        weights.append(round(val, 1))
        if weights:
            return {"weight_kg": round(weights[-1], 1)}
        return {}

    @staticmethod
    def _build_google_fit_badge(rows: list) -> Dict[str, Any]:
        """Google Fit の歩数・体重を抽出"""
        badge: Dict[str, Any] = {}
        for row in rows:
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            dt = payload.get("data_type", row.get("category", ""))
            val = payload.get("value")
            if "step" in dt.lower() and val is not None:
                badge["steps"] = int(val)
            elif "weight" in dt.lower() and val is not None:
                badge["weight_kg"] = round(float(val), 1)
            elif "sleep" in dt.lower() and val is not None:
                badge["sleep_min"] = int(val)
        return badge
    
    def get_raw_data_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """raw_data_lake の最新 N 件を返す"""
        response = (
            self.supabase.table("raw_data_lake")
            .select("id, user_id, fetched_at, source, category, payload")
            .order("fetched_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data

    def get_raw_data_by_date(self, target_date: str, user_id: str = "user_001") -> Dict[str, List[Dict[str, Any]]]:
        """指定日の最新 fetched_at のデータを source ごとに整理して返す"""
        start = f"{target_date}T00:00:00"
        end = f"{target_date}T23:59:59"
        response = (
            self.supabase.table("raw_data_lake")
            .select("*")
            .eq("user_id", user_id)
            .gte("fetched_at", start)
            .lte("fetched_at", end)
            .order("fetched_at", desc=True)
            .execute()
        )
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in response.data:
            source = row.get("source", "unknown")
            result.setdefault(source, []).append(row)
        return result
    
    # ── Phase 2: 相関分析用データ取得 ──

    def get_correlation_data(self, days: int = 14):
        """睡眠スコア (Oura) と 室内環境 (SwitchBot) を結合した DataFrame を返す。

        集計ロジック:
          - Oura: source='oura', category='sleep' の payload から score を抽出。
            日付は payload.day (YYYY-MM-DD) → recorded_at[:10] の順でフォールバック。
          - SwitchBot: source='switchbot', category='environment' の payload から
            temperature, humidity, CO2 を抽出し、日付ごとに平均値を算出。
          ※ 理想的には SwitchBot を「前日22:00〜当日08:00」で集計して睡眠時間帯の
            環境と対応付けるべきだが、Phase 2 初版では「同日の全時間帯平均」で結合する。
            将来的に時間帯フィルタを追加予定。

        Returns:
            columns: date, sleep_score, co2_avg, temp_avg, humidity_avg
        """
        import pandas as pd

        start_date = (_now_jst() - timedelta(days=days)).isoformat()

        # ── Oura sleep データ ──
        oura_resp = (
            self.supabase.table("raw_data_lake")
            .select("payload, recorded_at")
            .eq("source", "oura")
            .eq("category", "sleep")
            .gte("fetched_at", start_date)
            .order("fetched_at")
            .execute()
        )
        sleep_rows: List[Dict[str, Any]] = []
        for row in oura_resp.data:
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            score = payload.get("score")
            if score is None:
                continue
            # 日付: payload.day → recorded_at[:10]
            date_str = payload.get("day") or row.get("recorded_at", "")[:10]
            if len(date_str) < 10:
                continue
            sleep_rows.append({"date": date_str[:10], "sleep_score": int(score)})

        if not sleep_rows:
            return pd.DataFrame(columns=["date", "sleep_score", "co2_avg", "temp_avg", "humidity_avg"])

        df_sleep = pd.DataFrame(sleep_rows)
        # 同日に複数レコードがある場合は最新 (最後) を採用
        df_sleep = df_sleep.drop_duplicates(subset="date", keep="last")

        # ── SwitchBot environment データ ──
        sb_resp = (
            self.supabase.table("raw_data_lake")
            .select("payload, fetched_at")
            .eq("source", "switchbot")
            .eq("category", "environment")
            .gte("fetched_at", start_date)
            .order("fetched_at")
            .execute()
        )
        env_rows: List[Dict[str, Any]] = []
        for row in sb_resp.data:
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            date_str = _to_jst_date(row.get("fetched_at", "1970-01-01T00:00:00+00:00"))
            if len(date_str) < 10:
                continue
            env_rows.append({
                "date": date_str,
                "co2": payload.get("CO2"),
                "temp": payload.get("temperature"),
                "humidity": payload.get("humidity"),
            })

        if not env_rows:
            # SwitchBot データなし → sleep のみ返す
            df_sleep = df_sleep.rename(columns={"sleep_score": "sleep_score"})
            df_sleep["co2_avg"] = None
            df_sleep["temp_avg"] = None
            df_sleep["humidity_avg"] = None
            df_sleep = df_sleep.sort_values("date").reset_index(drop=True)
            return df_sleep

        df_env = pd.DataFrame(env_rows)
        # 日付ごとに平均を算出
        df_env_agg = df_env.groupby("date").agg(
            co2_avg=("co2", "mean"),
            temp_avg=("temp", "mean"),
            humidity_avg=("humidity", "mean"),
        ).reset_index()
        df_env_agg = df_env_agg.round(1)

        # ── マージ (inner join: 両方にデータがある日のみ) ──
        df = pd.merge(df_sleep, df_env_agg, on="date", how="left")
        df = df.sort_values("date").reset_index(drop=True)
        return df

    # ハッシュ計算時に除外する変動キー（API レスポンスに含まれる現在時刻等）
    _VOLATILE_KEYS = frozenset({
        "dt", "t", "time", "timestamp", "ts", "server_time",
        "fetched_at", "recorded_at", "updated_at", "created_at",
        "cod",  # OpenWeatherMap の内部コード
    })

    @classmethod
    def _strip_volatile(cls, obj: Any) -> Any:
        """payload から変動するメタデータキーを再帰的に除外したコピーを返す"""
        if isinstance(obj, dict):
            return {
                k: cls._strip_volatile(v)
                for k, v in obj.items()
                if k not in cls._VOLATILE_KEYS
            }
        if isinstance(obj, list):
            return [cls._strip_volatile(item) for item in obj]
        return obj

    @classmethod
    def _payload_hash(cls, payload: Any) -> str:
        """payload の SHA-256 ハッシュを返す（重複検知用）。
        変動するタイムスタンプ系キーを除外してから計算する。"""
        stable = cls._strip_volatile(payload)
        canonical = json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_recorded_at(payload: Any, fallback: datetime) -> str:
        """payload 内のタイムスタンプ候補から recorded_at を導出する。
        見つからなければ fallback (JST now) の ISO 文字列を返す。"""
        if not isinstance(payload, dict):
            return fallback.isoformat()

        # Unix epoch 系キー (dt, timestamp, ts, t, time)
        for key in ("dt", "timestamp", "ts", "t", "time"):
            val = payload.get(key)
            if isinstance(val, (int, float)) and val > 1_000_000_000:
                try:
                    return datetime.fromtimestamp(val, tz=JST).isoformat()
                except (OSError, ValueError):
                    continue

        # ISO 文字列系キー (recorded_at, date, day)
        for key in ("recorded_at", "date", "day"):
            val = payload.get(key)
            if isinstance(val, str) and len(val) >= 10:
                try:
                    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    return dt.astimezone(JST).isoformat()
                except ValueError:
                    # "2026-02-11" のような日付のみの場合
                    try:
                        dt = datetime.strptime(val[:10], "%Y-%m-%d").replace(tzinfo=JST)
                        return dt.isoformat()
                    except ValueError:
                        continue

        return fallback.isoformat()

    def save_raw_data(self, user_id: str, source: str,
                      category: str, payload: Any, **_kwargs):
        """raw_data_lake にハッシュガード付きで INSERT する。
        
        制約: unique_raw_data_v2 (user_id, fetched_at, source, category)
        ロジック:
          1. 同一 source/category の最新レコードの payload ハッシュと比較
          2. 中身が同じ → スキップ（重複防止）
          3. 中身が異なる → 新規 INSERT（fetched_at = now）
        """
        try:
            new_payload = payload if isinstance(payload, dict) else self._parse_raw_data(payload)
            new_hash = self._payload_hash(new_payload)
            
            # 同一 source/category の最新レコードを取得
            existing = (
                self.supabase.table("raw_data_lake")
                .select("id, payload")
                .eq("user_id", user_id)
                .eq("source", source)
                .eq("category", category)
                .order("fetched_at", desc=True)
                .limit(1)
                .execute()
            )
            
            if existing.data:
                old_hash = self._payload_hash(existing.data[0].get("payload", {}))
                if new_hash == old_hash:
                    logger.info(f"Skipped duplicate for {source}/{category}")
                    return
            
            now = _now_jst()
            recorded_at = self._extract_recorded_at(new_payload, now)
            data = {
                "user_id": user_id,
                "fetched_at": now.isoformat(),
                "recorded_at": recorded_at,
                "source": source,
                "category": category,
                "payload": new_payload,
            }
            self.supabase.table("raw_data_lake").insert(data).execute()
            logger.info(f"save_raw_data INSERT: {source}/{category}")
        except Exception as e:
            logger.warning(f"save_raw_data failed: source={source}, category={category}, error={e}")
    
    def save_token(self, user_id: str, provider: str, token_data: Dict[str, Any]):
        """OAuth トークンを upsert (insert or update) する"""
        data = {
            "user_id": user_id,
            "provider": provider,
            "token_data": token_data if isinstance(token_data, dict) else json.loads(token_data),
            "updated_at": "now()",
        }
        self.supabase.table("oauth_tokens").upsert(data).execute()
    
    def get_token(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
        """OAuth トークンを取得する"""
        response = (
            self.supabase.table("oauth_tokens")
            .select("token_data")
            .eq("user_id", user_id)
            .eq("provider", provider)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0].get("token_data")
        return None
    
    def delete_token(self, user_id: str, provider: str):
        """OAuth トークンを削除する"""
        self.supabase.table("oauth_tokens").delete().eq("user_id", user_id).eq("provider", provider).execute()
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError("Direct SQL queries are not supported with Supabase. Use table methods instead.")
    
    def _parse_raw_data(self, raw_data: Any) -> Any:
        if raw_data is None:
            return None
        if isinstance(raw_data, dict):
            return raw_data
        if isinstance(raw_data, str):
            try:
                return json.loads(raw_data)
            except (json.JSONDecodeError, TypeError):
                return raw_data
        return raw_data
