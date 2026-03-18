"""YuruHealth - メインダッシュボード
今日のコンディションを瞬時に把握
"""
import logging
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone

# UI Library & Components
from ui_lib.session import (
    get_database_manager,
    get_google_oauth,
    load_gemini_settings,
    get_gemini_evaluator,
)
from ui_lib.data_fetcher import fetch_latest_data
from ui_lib.formatters import minutes_to_hhmm
from components.responsive import inject_responsive_css, responsive_columns
from components.metrics import display_health_metrics, display_weight_metric
from components.charts import create_sleep_score_chart, create_weight_chart

# Fetchers
from src.fetchers.weather_fetcher import WeatherFetcher
from src.fetchers.google_fit_fetcher import GoogleFitFetcher

JST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)


st.set_page_config(
    page_title="YuruHealth - Dashboard",
    page_icon="💚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Galaxy Z Fold 7対応のレスポンシブCSS注入
inject_responsive_css()


def get_database_manager():
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


def get_withings_oauth(db_manager):
    if "_withings_oauth" not in st.session_state:
        st.session_state["_withings_oauth"] = WithingsOAuth(db_manager)
    return st.session_state["_withings_oauth"]


@st.cache_resource
def load_gemini_settings():
    settings = load_settings()
    gemini = settings.get("gemini", {})
    if "available_models" not in gemini:
        gemini["available_models"] = [gemini.get("model_name", "gemini-2.0-flash")]
    return gemini


@st.cache_resource
def get_gemini_evaluator(model_name: str):
    return GeminiEvaluator({}, model_name=model_name)


def get_weather_fetcher(db_manager=None):
    return WeatherFetcher(db_manager=db_manager)


def get_google_oauth(db_manager):
    obj = st.session_state.get("_google_oauth")
    if obj is None or not hasattr(obj, "ensure_credentials"):
        st.session_state["_google_oauth"] = GoogleOAuth(db_manager)
    return st.session_state["_google_oauth"]


def has_oauth_token(db_manager: DatabaseManager, provider: str, user_id: str = "user_001") -> bool:
    """oauth_tokens テーブルに provider のトークンが存在するかを返す。"""
    try:
        return bool(db_manager.get_token(user_id, provider))
    except Exception:
        return False


def fetch_latest_data(db_manager: DatabaseManager, user_id: str = "user_001"):
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


def _to_jst_date_text(value: Any) -> str:
    """DB時刻(UTC/naive/aware)をJSTに変換して YYYY-MM-DD を返す。"""
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


def _to_jst_hour(value: Any) -> int:
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


def _minutes_to_hhmm(value: Any) -> str:
    try:
        total = int(value)
    except (TypeError, ValueError):
        return "0:00"
    if total < 0:
        total = 0
    hours = total // 60
    mins = total % 60
    return f"{hours}:{mins:02d}"


def _extract_sleep_chosen_app(raw_data: Any) -> str:
    payload: Dict[str, Any] = {}
    if isinstance(raw_data, dict):
        payload = raw_data
    elif isinstance(raw_data, str):
        try:
            obj = json.loads(raw_data)
            if isinstance(obj, dict):
                payload = obj
        except Exception:
            return "-"
    app = payload.get("chosen_app")
    return str(app) if app else "-"


def _get_google_fit_sleep_policy() -> str:
    try:
        settings = load_settings()
        parser_cfg = ((settings.get("google_fit") or {}).get("sleep_parser") or {}) if isinstance(settings, dict) else {}
        policy = str(parser_cfg.get("source_policy") or "min").strip()
        return policy or "min"
    except Exception:
        return "min"


SYSTEM_HEALTH_SAMPLE_INTERVAL_SECONDS = 300
SYSTEM_HEALTH_RETENTION_DAYS = 30


@st.cache_data(ttl=SYSTEM_HEALTH_SAMPLE_INTERVAL_SECONDS, show_spinner=False)
def collect_system_health_sample() -> Dict[str, Any]:
    """5分間隔でシステムメトリクスを SQLite に保存する。"""
    return ensure_system_health_sample(
        sample_interval_seconds=SYSTEM_HEALTH_SAMPLE_INTERVAL_SECONDS,
        retention_days=SYSTEM_HEALTH_RETENTION_DAYS,
        disk_path="/app",
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_system_health_history(hours: int) -> List[Dict[str, Any]]:
    since_utc = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))
    return fetch_system_health_history(since_utc=since_utc)


def _system_health_records_to_df(records: List[Dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["measured_at", "cpu_temp_c", "cpu_percent", "memory_percent", "disk_percent"])
    df = pd.DataFrame(records)
    df["measured_at"] = pd.to_datetime(df["measured_at"], utc=True, errors="coerce").dt.tz_convert(JST)
    for col in ["cpu_temp_c", "cpu_percent", "memory_percent", "disk_percent"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["measured_at"]).sort_values("measured_at")


def _downsample_df(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    step = max(1, (len(df) + max_points - 1) // max_points)
    return df.iloc[::step].copy()


def _get_system_health_ui_config() -> Dict[str, float]:
    defaults: Dict[str, float] = {
        "temp_warn_c": 60.0,
        "temp_critical_c": 70.0,
        "usage_warn_percent": 85.0,
        "usage_critical_percent": 95.0,
    }
    try:
        settings = load_settings()
        cfg = (settings.get("system_health") or {}) if isinstance(settings, dict) else {}
        ui_cfg = (cfg.get("ui") or {}) if isinstance(cfg, dict) else {}
        for key, default_value in defaults.items():
            raw = ui_cfg.get(key)
            if raw is None:
                continue
            defaults[key] = float(raw)
    except Exception:
        pass
    return defaults


def _temp_color(temp_c: Any, cfg: Dict[str, float]) -> str:
    try:
        value = float(temp_c)
    except (TypeError, ValueError):
        return "#9ca3af"
    if value > cfg["temp_critical_c"]:
        return "#dc2626"
    if value > cfg["temp_warn_c"]:
        return "#d97706"
    return "#16a34a"


def _usage_color(percent: Any, cfg: Dict[str, float]) -> str:
    try:
        value = float(percent)
    except (TypeError, ValueError):
        return "#9ca3af"
    if value >= cfg["usage_critical_percent"]:
        return "#dc2626"
    if value >= cfg["usage_warn_percent"]:
        return "#d97706"
    return "#16a34a"


def _render_system_health_widget() -> None:
    snapshot = collect_system_health_sample()
    metrics = snapshot.get("latest") if isinstance(snapshot, dict) else None
    if not isinstance(metrics, dict):
        st.caption("システムヘルスの取得に失敗しました。")
        return
    cfg = _get_system_health_ui_config()
    cpu_temp = metrics.get("cpu_temp_c")
    temp_text = f"{cpu_temp:.1f}°C" if isinstance(cpu_temp, (int, float)) else "N/A"
    cpu_percent = float(metrics.get("cpu_percent") or 0.0)
    memory_percent = float(metrics.get("memory_percent") or 0.0)
    disk_percent = float(metrics.get("disk_percent") or 0.0)

    st.markdown(
        f"""
        <div style="border:1px solid #e5e7eb; border-radius:10px; padding:10px 12px; margin-top:6px; background:#ffffff;">
            <div style="display:flex; justify-content:space-between; margin:2px 0; font-size:0.92rem;">
                <span>CPU温度</span>
                <span style="font-weight:700; color:{_temp_color(cpu_temp, cfg)};">{temp_text}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin:2px 0; font-size:0.92rem;">
                <span>CPU使用率</span>
                <span style="font-weight:700; color:{_usage_color(cpu_percent, cfg)};">{cpu_percent:.1f}%</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin:2px 0; font-size:0.92rem;">
                <span>メモリ使用率</span>
                <span style="font-weight:700; color:{_usage_color(memory_percent, cfg)};">{memory_percent:.1f}%</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin:2px 0; font-size:0.92rem;">
                <span>ディスク使用率</span>
                <span style="font-weight:700; color:{_usage_color(disk_percent, cfg)};">{disk_percent:.1f}%</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("保存: data/system_health.db / 間隔: 5分 / 保持: 30日")
    if not isinstance(cpu_temp, (int, float)):
        st.caption("CPU温度が取得できません。/sys/class/thermal のマウントと権限をご確認ください。")


def get_weather_info(db_manager) -> dict:
    """サイドバー足跡用に、parsedテーブルの最新DB値を直接読み込んで source×date 辞書を構築する。"""
    start_jst = (datetime.now(JST) - timedelta(days=max(0, 7))).strftime("%Y-%m-%d")

    rich_history: Dict[tuple, Dict[str, Any]] = {}

    # Oura (oura_data)
    oura_rows = (
        _db_manager.supabase.table("oura_data")
        .select("measured_at, sleep_score, activity_score, readiness_score")
        .eq("user_id", user_id)
        .gte("measured_at", f"{start_jst}T00:00:00")
        .order("measured_at")
        .limit(50000)
        .execute()
        .data
        or []
    )
    oura_latest_by_date: Dict[str, Dict[str, Any]] = {}
    for row in oura_rows:
        date_text = _to_jst_date_text(row.get("measured_at"))
        if not date_text:
            continue
        oura_latest_by_date[date_text] = row
    for date_text, row in oura_latest_by_date.items():
        rich_history[("oura", date_text)] = {
            "has_data": True,
            "badge": {
                "sleep_score": row.get("sleep_score"),
                "activity_score": row.get("activity_score"),
                "readiness_score": row.get("readiness_score"),
            },
        }

    # Withings (weight_data)
    withings_rows = (
        _db_manager.supabase.table("weight_data")
        .select("measured_at, weight_kg")
        .eq("user_id", user_id)
        .gte("measured_at", f"{start_jst}T00:00:00")
        .order("measured_at")
        .limit(50000)
        .execute()
        .data
        or []
    )
    withings_latest_by_date: Dict[str, Dict[str, Any]] = {}
    for row in withings_rows:
        date_text = _to_jst_date_text(row.get("measured_at"))
        if not date_text:
            continue
        withings_latest_by_date[date_text] = row
    for date_text, row in withings_latest_by_date.items():
        rich_history[("withings", date_text)] = {
            "has_data": True,
            "badge": {"weight_kg": row.get("weight_kg")},
        }

    # Google Fit (google_fit_data)
    gfit_rows = (
        _db_manager.supabase.table("google_fit_data")
        .select("date, data_type, value")
        .eq("user_id", user_id)
        .gte("date", start_jst)
        .order("date")
        .limit(50000)
        .execute()
        .data
        or []
    )
    gfit_badge_by_date: Dict[str, Dict[str, Any]] = {}
    for row in gfit_rows:
        date_text = _to_jst_date_text(row.get("date"))
        if not date_text:
            continue
        badge = gfit_badge_by_date.setdefault(date_text, {})
        data_type = str(row.get("data_type") or "")
        value = row.get("value")
        if data_type == "steps" and value is not None:
            badge["steps"] = int(badge.get("steps", 0)) + int(value)
        elif data_type == "weight" and value is not None:
            badge["weight_kg"] = round(float(value), 1)
        elif data_type == "sleep" and value is not None:
            badge["sleep_min"] = int(badge.get("sleep_min", 0)) + int(value)
    for date_text, badge in gfit_badge_by_date.items():
        rich_history[("google_fit", date_text)] = {
            "has_data": True,
            "badge": badge,
        }

    # Environment (environmental_logs): source に応じて Weather / SwitchBot を分離
    env_rows = (
        _db_manager.supabase.table("environmental_logs")
        .select("timestamp, source, temp, humidity, pressure, raw_data")
        .gte("timestamp", f"{start_jst}T00:00:00")
        .order("timestamp")
        .limit(50000)
        .execute()
        .data
        or []
    )
    env_by_source_date: Dict[tuple, Dict[str, Any]] = {}
    for row in env_rows:
        date_text = _to_jst_date_text(row.get("timestamp"))
        if not date_text:
            continue
        source_value = str(row.get("source") or "").strip().lower()
        footprint_source = "switchbot" if source_value == "switchbot" else "weather"
        key = (footprint_source, date_text)
        bucket = env_by_source_date.setdefault(key, {"timeseries": []})
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        bucket["timeseries"].append(
            {
                "hour": _to_jst_hour(row.get("timestamp")),
                "temp": row.get("temp"),
                "humidity": row.get("humidity"),
                "pressure": row.get("pressure"),
                "co2": raw_data.get("CO2"),
            }
        )

    for (footprint_source, date_text), bucket in env_by_source_date.items():
        ts = bucket.get("timeseries", [])
        summary: Dict[str, Any] = {}
        for field in ("temp", "humidity", "pressure", "co2"):
            values = [p[field] for p in ts if p.get(field) is not None]
            if values:
                summary[f"{field}_avg"] = round(sum(values) / len(values), 1)
        rich_history[(footprint_source, date_text)] = {
            "has_data": True,
            "timeseries": ts,
            "summary": summary,
        }

    return rich_history


def refresh_data(db_manager: DatabaseManager, user_id: str = "user_001"):
    """データを更新"""
    try:
        with st.spinner("データを更新中..."):
            logger.info("=== refresh_data started ===")
            end_dt = datetime.now(JST)
            start_dt = end_dt - timedelta(days=7)
            start_str = start_dt.strftime("%Y-%m-%d")
            end_str = end_dt.strftime("%Y-%m-%d")
            
            # Withingsデータ取得
            withings_oauth = get_withings_oauth(db_manager)
            if withings_oauth.is_authenticated():
                logger.info("Withings: authenticated, fetching data...")
                try:
                    config = load_settings()
                    fetcher = WithingsFetcher(config, withings_oauth, db_manager=db_manager)
                    data = fetcher.fetch_data(user_id, start_str, end_str)
                    
                    if data:
                        for record in data:
                            db_manager.insert_weight_data(
                                user_id=record["user_id"],
                                measured_at=record["measured_at"],
                                weight_kg=record["weight_kg"],
                                raw_data=record.get("raw_data", "")
                            )
                except Exception as e:
                    logger.info(f"Withings fetch error: {e}")
                    st.warning(f"Withings: {str(e)}")
            else:
                logger.info("Withings: not authenticated, skipping")
            
            # Ouraデータ取得
            try:
                config = load_settings()
                fetcher = OuraFetcher(config, db_manager=db_manager)
                logger.info(f"Oura: db_manager passed = {db_manager is not None}")
                if fetcher.authenticate():
                    logger.info("Oura: authenticated, fetching data...")
                    data = fetcher.fetch_data(user_id, start_str, end_str)
                    
                    if data:
                        for record in data:
                            db_manager.insert_oura_data(
                                user_id=record["user_id"],
                                measured_at=record["measured_at"],
                                activity_score=record.get("activity_score"),
                                sleep_score=record.get("sleep_score"),
                                readiness_score=record.get("readiness_score"),
                                steps=record.get("steps"),
                                total_sleep_duration=record.get("total_sleep_duration"),
                                raw_data=record.get("raw_data", "")
                            )
            except Exception as e:
                logger.info(f"Oura fetch error: {e}")
                st.warning(f"Oura: {str(e)}")
            
            # 天気データ取得
            logger.info("Weather: starting fetch...")
            try:
                weather_fetcher = get_weather_fetcher(db_manager=db_manager)
                if weather_fetcher.is_available():
                    lat = st.session_state.get("gps_lat")
                    lon = st.session_state.get("gps_lon")
                    weather = weather_fetcher.fetch_weather(lat=lat, lon=lon)
                    
                    if weather:
                        db_manager.insert_environmental_log(
                            timestamp=weather["timestamp"],
                            source=weather["source"],
                            latitude=weather["latitude"],
                            longitude=weather["longitude"],
                            weather_summary=weather["weather_summary"],
                            temp=weather["temp"],
                            humidity=weather["humidity"],
                            pressure=weather["pressure"],
                            raw_data=weather["raw_data"]
                        )
                        st.session_state["latest_weather"] = weather
                    elif weather_fetcher.last_error:
                        st.error(f"🌤️ 天気取得エラー: {weather_fetcher.last_error}")
            except Exception as e:
                st.error(f"🌤️ 天気取得エラー: {str(e)}")
            
            # Google Fit データ取得 (7日バックフィル)
            try:
                google_oauth = get_google_oauth(db_manager)
                if google_oauth.is_available() and hasattr(google_oauth, "ensure_credentials"):
                    google_oauth.ensure_credentials()
                if google_oauth.is_available() and google_oauth.is_authenticated():
                    creds = google_oauth.get_credentials()
                    if creds:
                        logger.info("Google Fit: authenticated, fetching 7-day data...")
                        gfit_fetcher = GoogleFitFetcher(creds, db_manager=db_manager)
                        fit_data = gfit_fetcher.fetch_all(user_id, start_str, end_str)
                        saved_count = 0
                        for data_type, records in fit_data.items():
                            for record in records:
                                try:
                                    db_manager.insert_google_fit_data(
                                        user_id=record["user_id"],
                                        date=record["date"],
                                        data_type=record["data_type"],
                                        value=record["value"],
                                        raw_data=record["raw_data"],
                                    )
                                    saved_count += 1
                                except Exception:
                                    pass
                        logger.info(f"Google Fit: {saved_count} records saved")
            except Exception as e:
                logger.info(f"Google Fit fetch error: {e}")
            
            # SwitchBot 環境データ取得
            logger.info("SwitchBot: starting fetch...")
            try:
                switchbot_fetcher = SwitchBotFetcher(db_manager=db_manager)
                if switchbot_fetcher.is_available():
                    result = switchbot_fetcher.fetch_device_status()
                    if result:
                        logger.info("SwitchBot: environment data fetched successfully")
                    else:
                        logger.info("SwitchBot: no data returned")
                else:
                    logger.info("SwitchBot: not configured, skipping")
            except Exception as e:
                logger.info(f"SwitchBot fetch error: {e}")
        
        logger.info("=== refresh_data completed ===")
        collect_system_health_sample.clear()
        load_system_health_history.clear()
        load_footprint_from_parsed_tables.clear()
        st.success("✅ データを更新しました")
        st.rerun()
    except Exception as e:
        logger.error(f"refresh_data top-level error: {e}")
        st.error(f"❌ エラー: {str(e)}")


def main():
    st.title("💚 YuruHealth")
    
    db_manager = get_database_manager()
    db_manager.init_tables()


    gemini_settings = load_gemini_settings()
    
    # OAuth インスタンス
    withings_oauth = get_withings_oauth(db_manager)
    google_oauth = get_google_oauth(db_manager)

    # Withings OAuth コールバック処理
    query_params = st.query_params
    withings_code = query_params.get("code")
    withings_state = query_params.get("state", "")
    if withings_code and withings_state.startswith("withings_") and not withings_oauth.is_authenticated():
        try:
            withings_oauth.exchange_code_for_token(withings_code)
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Withings認証エラー: {e}")
    
    # GPS位置情報の取得（session_stateで再リロードループを防止）
    if GEOLOCATION_AVAILABLE and "gps_requested" not in st.session_state:
        st.session_state["gps_requested"] = True
        try:
            loc = get_geolocation()
            if loc and isinstance(loc, dict):
                coords = loc.get("coords", {})
                if coords.get("latitude") and coords.get("longitude"):
                    st.session_state["gps_lat"] = coords["latitude"]
                    st.session_state["gps_lon"] = coords["longitude"]
        except Exception:
            pass
    
    # 最新データ取得
    data = fetch_latest_data(db_manager)
    latest_oura = data["latest_oura"]
    
    # Sidebar Controls (スマホ向けに設定類を集約)
    default_model = gemini_settings.get("model_name", "gemini-2.0-flash")
    available_models = gemini_settings.get("available_models") or [default_model]

    with st.sidebar:
        st.header("⚙️ 設定")

        analytics_days = st.select_slider(
            "分析期間",
            options=[7, 14, 30],
            value=14,
            format_func=lambda d: f"{d}日間",
        )
        insight_date = st.date_input(
            "Deep Insight 対象日",
            value=(datetime.now(JST) - timedelta(days=1)).date(),
        )
        selected_model = st.radio("Gemini モデル", options=available_models, horizontal=True)

        with st.expander("🔐 API連携", expanded=False):
            withings_connected = has_oauth_token(db_manager, "withings")
            google_connected = has_oauth_token(db_manager, "google")
            oura_connected = latest_oura is not None

            if oura_connected:
                st.success("✅ Oura: 連携済み")
            else:
                st.warning("⚠️ Oura: データ未取得（トークン設定または取得処理を確認）")

            withings_oauth.sync_tokens_from_db()
            if withings_connected:
                st.success("✅ Withings: 認証済み")
                if st.button("� Withings認証解除"):
                    withings_oauth.clear_tokens()
                    st.rerun()
            else:
                st.warning("⚠️ Withings: 未認証")
                if withings_oauth.client_id:
                    auth_url = withings_oauth.get_authorization_url(state="withings_auth")
                    st.link_button("🔗 Withings にログイン", auth_url)
                else:
                    st.caption("Withings の client_id が設定されていません")

            if google_oauth.is_available():
                google_oauth.ensure_credentials()
                if google_connected:
                    st.success("✅ Google Fit: 認証済み")
                    if st.button("🚪 Google Fit ログアウト", key="sidebar_google_logout"):
                        google_oauth.logout()
                        st.rerun()
                else:
                    st.warning("⚠️ Google Fit: 未認証")
                    st.caption("初回は『Google Fit にログイン』を押して、ブラウザで認証を完了してください。")
                    auth_url = google_oauth.get_authorization_url()
                    st.link_button("🔗 Google Fit にログイン", auth_url)
            else:
                st.caption("Google Fit の client_id / client_secret が未設定です")

        with st.expander("ℹ️ システム情報", expanded=False):
            st.info(f"**環境:** {db_manager.env}")
            st.info(f"**DB:** {db_manager.db_config['type']}")
            st.caption(f"Model: {default_model} (選択可能: {', '.join(available_models)})")

        if st.checkbox("�️ Raw Data View", value=False):
            raw_rows = db_manager.get_raw_data_recent(limit=100)
            if raw_rows:
                df_raw = pd.DataFrame(raw_rows)
                st.dataframe(df_raw, use_container_width=True)
            else:
                st.caption("raw_data_lake にデータがありません")

        st.markdown("---")
        st.markdown("### 🧰 Pi ヘルスチェック")
        _render_system_health_widget()

    # 環境情報
    env_log = db_manager.get_latest_environmental_log()
    weather_info = st.session_state.get("latest_weather") or env_log

    # ── Top KPI (3列) ──
    sleep_scores = [r.get("sleep_score") for r in data["oura_data"] if r.get("sleep_score") is not None]
    latest_sleep = sleep_scores[0] if sleep_scores else None
    prev_sleep = sleep_scores[1] if len(sleep_scores) > 1 else None

    weight_values = [r.get("weight_kg") for r in data["weight_data"] if r.get("weight_kg") is not None]
    latest_weight_value = weight_values[0] if weight_values else None
    prev_weight_value = weight_values[1] if len(weight_values) > 1 else None

    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1:
        if latest_sleep is not None:
            sleep_delta = f"{latest_sleep - prev_sleep:+.0f}" if prev_sleep is not None else None
            st.metric("� 睡眠スコア", f"{latest_sleep}点", delta=sleep_delta)
        else:
            st.metric("� 睡眠スコア", "No Data")
    with kpi2:
        if latest_weight_value is not None:
            weight_delta = f"{latest_weight_value - prev_weight_value:+.1f}kg" if prev_weight_value is not None else None
            st.metric("⚖️ 体重", f"{latest_weight_value}kg", delta=weight_delta)
        else:
            st.metric("⚖️ 体重", "No Data")
    with kpi3:
        if weather_info and weather_info.get("temp") is not None:
            st.metric("🌡️ 環境", f"{weather_info['temp']}℃")
        else:
            st.metric("🌡️ 環境", "No Data")

    col_spacer, col_btn = st.columns([3, 1])
    with col_btn:
        if st.button("🔄 更新", use_container_width=True):
            refresh_data(db_manager)

    st.markdown("### 👣 記録の足跡（直近7日）")
    rich_history = load_footprint_from_parsed_tables(db_manager, days=7, user_id="user_001")
    if rich_history:
        recent_dates = sorted({fetched_date for (_, fetched_date) in rich_history.keys()})[-7:]
        rich_history_recent = {
            k: v for k, v in rich_history.items()
            if k[1] in recent_dates
        }
    else:
        rich_history_recent = {}

    footprint_html, total_cells, filled_cells = build_footprint_html(rich_history_recent, days=7)
    st.markdown(footprint_html, unsafe_allow_html=True)

    if filled_cells > 0:
        rate = filled_cells / total_cells * 100
        st.success(f"🎉 直近7日で **{filled_cells}件** のデータが届いています（到達率 {rate:.0f}%）。")
    else:
        st.info("まだデータがありません。🔄 ボタンでデータを取得してみましょう。")

    # Google OAuth コールバック処理
    if google_oauth.is_available():
        google_oauth.ensure_credentials()
        query_params = st.query_params
        auth_error = query_params.get("error")
        auth_code = query_params.get("code")
        auth_state = query_params.get("state")

        if auth_error:
            google_oauth.clear_pending_oauth()
            st.error(f"Google認証エラー: {auth_error}")
            st.query_params.clear()
        elif auth_code:
            if not google_oauth.is_expected_state(auth_state):
                google_oauth.clear_pending_oauth()
                st.error("Google認証エラー: state が一致しません。Google Fit ログインをやり直してください。")
                st.query_params.clear()
            elif not google_oauth.is_authenticated():
                if google_oauth.exchange_code_for_token(auth_code, state=auth_state):
                    st.query_params.clear()
                    st.rerun()
            else:
                # 既に認証済みの場合は callback パラメータだけ掃除する
                st.query_params.clear()

    # ── タブ化 UI ──
    tab_summary, tab_intake, tab_sleep, tab_weight, tab_env, tab_server = st.tabs([
        "📊 サマリー",
        "🥤 摂取ログ",
        "💤 睡眠詳細",
        "⚖️ 体重推移",
        "🌡️ 環境ログ",
        "🖥️ サーバー・ヘルス",
    ])

    with tab_summary:
        if "deep_insight" not in st.session_state:
            st.session_state.deep_insight = ""
        if "deep_insight_date" not in st.session_state:
            st.session_state.deep_insight_date = ""
        if "deep_insight_model" not in st.session_state:
            st.session_state.deep_insight_model = ""
        if "deep_insight_created_at" not in st.session_state:
            st.session_state.deep_insight_created_at = ""

        evaluator = get_gemini_evaluator(default_model)
        insight_container = st.container()
        target_date = insight_date.strftime("%Y-%m-%d")
        user_id = "user_001"

        insight_history = db_manager.get_daily_insight_history(target_date=target_date, user_id=user_id, limit=20)
        latest_db_insight = insight_history[0] if insight_history else None

        # 日付変更時は DB の最新結果を基準に表示を同期
        if st.session_state.deep_insight_date != target_date:
            if latest_db_insight:
                st.session_state.deep_insight = latest_db_insight.get("content", "")
                st.session_state.deep_insight_model = latest_db_insight.get("model_name", "")
                st.session_state.deep_insight_created_at = latest_db_insight.get("created_at", "")
            else:
                st.session_state.deep_insight = ""
                st.session_state.deep_insight_model = ""
                st.session_state.deep_insight_created_at = ""
            st.session_state.deep_insight_date = target_date

        def _run_deep_insight_analysis():
            with st.spinner("Geminiが昨日のデータを読み解いています..."):
                raw_data = db_manager.get_raw_data_by_date(target_date)
                if not raw_data:
                    st.warning(f"⚠️ {target_date} の生データがありません。🔄ボタンでデータを更新してください。")
                    return

                insight = evaluator.deep_analyze(
                    raw_data,
                    target_model=selected_model,
                    target_date=target_date,
                    user_id=user_id,
                    db_manager=db_manager,
                )
                db_manager.save_daily_insight(
                    target_date=target_date,
                    content=insight,
                    model_name=selected_model,
                    user_id=user_id,
                )
                st.session_state.deep_insight = insight
                st.session_state.deep_insight_model = selected_model
                st.session_state.deep_insight_created_at = datetime.now(JST).isoformat()
                st.session_state.deep_insight_date = target_date
                st.rerun()

        if evaluator.is_available():
            if latest_db_insight:
                label = f"既存の分析が{len(insight_history)}件あります。{selected_model} でやり直しますか？"
                with st.popover(label, use_container_width=True):
                    st.caption(f"対象日: {target_date}")
                    st.warning("再分析を実行すると、新しい結果が履歴に追加されます。")
                    if st.button("✅ はい、再分析する", key=f"reanalyze_{target_date}", use_container_width=True):
                        _run_deep_insight_analysis()
            else:
                if st.button("🔍 Gemini 分析（Deep Insight）", use_container_width=True):
                    _run_deep_insight_analysis()

        with insight_container:
            if st.session_state.deep_insight:
                st.success(st.session_state.deep_insight.split("\n")[0])
                with st.expander("📋 詳細分析を見る", expanded=False):
                    st.markdown(st.session_state.deep_insight)

                if st.session_state.deep_insight_model or st.session_state.deep_insight_created_at:
                    meta_parts = []
                    if st.session_state.deep_insight_model:
                        meta_parts.append(f"model: {st.session_state.deep_insight_model}")
                    if st.session_state.deep_insight_created_at:
                        meta_parts.append(f"created: {st.session_state.deep_insight_created_at[:16].replace('T', ' ')}")
                    st.caption(" / ".join(meta_parts))

                if insight_history:
                    with st.expander("🕘 過去の生成履歴", expanded=False):
                        for row in insight_history:
                            created_at = row.get("created_at", "")
                            created_label = created_at[11:16] if len(created_at) >= 16 else "--:--"
                            model_label = row.get("model_name", "model不明")
                            with st.expander(f"{created_label} {model_label}版", expanded=False):
                                st.markdown(row.get("content", ""))
            else:
                st.info("まだ分析結果がありません。上のボタンから Deep Insight を実行してください。")

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if latest_oura and latest_oura.get("readiness_score") is not None:
                st.metric("💪 レディネス", f"{latest_oura.get('readiness_score')}点")
            else:
                st.metric("💪 レディネス", "ー")
        with col_b:
            if latest_oura and latest_oura.get("activity_score") is not None:
                st.metric("🏃 活動", f"{latest_oura.get('activity_score')}点")
            else:
                st.metric("🏃 活動", "ー")
        with col_c:
            if latest_oura and latest_oura.get("steps") is not None:
                st.metric("🚶 歩数", f"{latest_oura.get('steps'):,}歩")
            else:
                st.metric("🚶 歩数", "ー")

        with st.expander("🏃 Google Fit データ", expanded=False):
            if google_oauth.is_authenticated():
                st.success("✅ Google Fit: 認証済み")

                if st.button("📥 Google Fit データ取得"):
                    try:
                        creds = google_oauth.get_credentials()
                        if creds:
                            fetcher = GoogleFitFetcher(creds, db_manager=db_manager)
                            end_dt = datetime.now(JST)
                            start_dt = end_dt - timedelta(days=7)
                            start_str = start_dt.strftime("%Y-%m-%d")
                            end_str = end_dt.strftime("%Y-%m-%d")

                            with st.spinner("Google Fit からデータ取得中..."):
                                fit_data = fetcher.fetch_all("user_001", start_str, end_str)

                            saved_count = 0
                            for data_type, records in fit_data.items():
                                for record in records:
                                    try:
                                        db_manager.insert_google_fit_data(
                                            user_id=record["user_id"],
                                            date=record["date"],
                                            data_type=record["data_type"],
                                            value=record["value"],
                                            raw_data=record["raw_data"],
                                        )
                                        saved_count += 1
                                    except Exception:
                                        pass

                            st.success(f"✅ {saved_count}件のデータを保存しました")
                        else:
                            st.error("認証情報の取得に失敗しました。再ログインしてください。")
                    except Exception as e:
                        st.error(f"❌ Google Fit エラー: {e}")

                gfit_steps = db_manager.get_google_fit_data(user_id="user_001", data_type="steps", limit=7)
                gfit_sleep = db_manager.get_google_fit_data(user_id="user_001", data_type="sleep", limit=7)

                if gfit_steps:
                    st.markdown("**📊 歩数 (直近7日)**")
                    df_steps = pd.DataFrame(gfit_steps)
                    df_steps["date"] = pd.to_datetime(df_steps["date"])
                    df_steps = df_steps.sort_values("date")
                    st.bar_chart(df_steps.set_index("date")["value"], use_container_width=True)

                if gfit_sleep:
                    st.markdown("**😴 睡眠時間 (直近7日, h:mm)**")
                    st.caption(f"source policy: {_get_google_fit_sleep_policy()}")
                    df_sleep = pd.DataFrame(gfit_sleep)
                    df_sleep["date"] = pd.to_datetime(df_sleep["date"])
                    df_sleep = df_sleep.sort_values("date")
                    df_sleep["sleep_hhmm"] = df_sleep["value"].apply(_minutes_to_hhmm)
                    df_sleep["source"] = df_sleep.get("raw_data", pd.Series([None] * len(df_sleep))).apply(_extract_sleep_chosen_app)
                    st.dataframe(
                        df_sleep[["date", "sleep_hhmm", "source"]].rename(columns={"date": "日付", "sleep_hhmm": "睡眠", "source": "採用ソース"}),
                        use_container_width=True,
                        hide_index=True,
                    )

                if st.button("🚪 Google Fit ログアウト"):
                    google_oauth.logout()
                    st.rerun()
            else:
                if google_oauth.is_available():
                    st.info("Google Fit に接続して、Samsung Health のデータを取得できます。")
                    st.caption("初回のみブラウザ認証が必要です（API連携からも実行できます）。")
                    auth_url = google_oauth.get_authorization_url()
                    st.link_button("🔗 Google Fit にログイン", auth_url)
                else:
                    st.warning("Google Fit 連携が未設定です。config/secrets.yaml を確認してください。")

    with tab_intake:
        st.subheader("🥤 摂取ログ・トラッキング")
        user_id = "user_001"

        supplements = load_supplements()
        items_master = supplements.get("items", {})
        presets = supplements.get("presets", {})

        if not items_master:
            st.warning("config/supplements.yaml に items が未定義です。")
        else:
            scene_options = list(presets.keys()) or ["Morning", "Noon", "Night", "Workout", "Anytime"]
            selected_scene = st.selectbox("シーン", options=scene_options, index=0)
            scene_preset = get_scene_preset(selected_scene, supplements)
            default_items = set(scene_preset.get("default_items", []))

            now_jst = datetime.now(JST)
            scene_time_presets = {
                "Morning": (7, 0),
                "Noon": (12, 0),
                "Night": (21, 0),
                "Workout": (18, 0),
            }

            if "intake_log_date" not in st.session_state:
                st.session_state["intake_log_date"] = now_jst.date()
            if "intake_log_time" not in st.session_state:
                hh_mm = scene_time_presets.get(selected_scene)
                if hh_mm:
                    st.session_state["intake_log_time"] = now_jst.replace(
                        hour=hh_mm[0], minute=hh_mm[1], second=0, microsecond=0
                    ).time()
                else:
                    st.session_state["intake_log_time"] = now_jst.time().replace(second=0, microsecond=0)

            prev_scene_key = "_intake_prev_scene"
            if st.session_state.get(prev_scene_key) != selected_scene:
                hh_mm = scene_time_presets.get(selected_scene)
                if hh_mm:
                    st.session_state["intake_log_time"] = now_jst.replace(
                        hour=hh_mm[0], minute=hh_mm[1], second=0, microsecond=0
                    ).time()
                st.session_state[prev_scene_key] = selected_scene

            st.caption("後から入力しやすいように、日付ショートカットとシーン時刻プリセットを使えます。")
            quick_today, quick_yesterday, quick_two_days, quick_scene_time = st.columns(4)
            if quick_today.button("今日", key="intake_date_today"):
                st.session_state["intake_log_date"] = now_jst.date()
                st.rerun()
            if quick_yesterday.button("昨日", key="intake_date_yesterday"):
                st.session_state["intake_log_date"] = (now_jst - timedelta(days=1)).date()
                st.rerun()
            if quick_two_days.button("一昨日", key="intake_date_two_days"):
                st.session_state["intake_log_date"] = (now_jst - timedelta(days=2)).date()
                st.rerun()
            if quick_scene_time.button("シーン時刻", key="intake_apply_scene_time"):
                hh_mm = scene_time_presets.get(selected_scene)
                if hh_mm:
                    st.session_state["intake_log_time"] = now_jst.replace(
                        hour=hh_mm[0], minute=hh_mm[1], second=0, microsecond=0
                    ).time()
                else:
                    st.session_state["intake_log_time"] = now_jst.time().replace(second=0, microsecond=0)
                st.rerun()

            col_date, col_time = st.columns(2)
            intake_date = col_date.date_input("摂取日", key="intake_log_date")
            intake_time = col_time.time_input("摂取時刻", step=600, key="intake_log_time")
            intake_timestamp = datetime.combine(intake_date, intake_time).replace(tzinfo=JST)

            recent_logs = db_manager.get_intake_logs(user_id=user_id, hours=12, limit=20)
            recent_same_scene = []
            for row in recent_logs:
                if row.get("scene") != selected_scene:
                    continue
                ts = row.get("timestamp")
                try:
                    row_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if row_dt.tzinfo is None:
                        row_dt = row_dt.replace(tzinfo=JST)
                    row_dt = row_dt.astimezone(JST)
                except Exception:
                    continue
                if abs((intake_timestamp - row_dt).total_seconds()) <= 30 * 60:
                    recent_same_scene.append(row_dt)

            if recent_same_scene:
                latest = max(recent_same_scene)
                st.warning(
                    f"⚠️ 直近30分に同じシーン（{selected_scene}）の記録があります: {latest.strftime('%m/%d %H:%M')}"
                )

            grouped_items = {"base": [], "optional": []}
            for item_id, item in items_master.items():
                item_type = item.get("type", "optional")
                if item_type not in grouped_items:
                    item_type = "optional"
                grouped_items[item_type].append((item_id, item))

            selected_item_quantities = {}

            for item_type, label in (("base", "🧱 ベース"), ("optional", "✨ オプション")):
                items = grouped_items.get(item_type, [])
                if not items:
                    continue
                st.markdown(f"**{label}**")
                for item_id, item in items:
                    item_name = item.get("name", item_id)
                    unit_type = str(item.get("unit_type", "回") or "回")
                    default_quantity = item.get("default_quantity", 1.0)
                    try:
                        default_quantity = max(0.0, float(default_quantity))
                    except (TypeError, ValueError):
                        default_quantity = 1.0
                    checked = st.checkbox(
                        item_name,
                        value=item_id in default_items,
                        key=f"intake_chk_{selected_scene}_{item_id}",
                    )
                    if checked:
                        if unit_type in {"錠", "粒", "カプセル", "ソフトジェル"}:
                            quantity = st.number_input(
                                f"{item_name} の数量（{unit_type}）",
                                min_value=0,
                                max_value=20,
                                value=int(round(default_quantity)),
                                step=1,
                                key=f"intake_qty_{selected_scene}_{item_id}",
                            )
                        else:
                            quantity = st.number_input(
                                f"{item_name} の数量（{unit_type}）",
                                min_value=0.0,
                                max_value=20.0,
                                value=float(default_quantity),
                                step=0.5,
                                key=f"intake_qty_{selected_scene}_{item_id}",
                            )
                        selected_item_quantities[item_id] = float(quantity)

            snapshot_payload = build_intake_snapshot(items_master, selected_item_quantities)
            if selected_item_quantities:
                with st.expander("🧪 スナップショット確認", expanded=False):
                    total_nutrients = snapshot_payload.get("total_nutrients", {})
                    nutrient_rows = [
                        {"成分": format_nutrient_label(k), "摂取量": v}
                        for k, v in total_nutrients.items()
                    ]
                    if nutrient_rows:
                        st.dataframe(pd.DataFrame(nutrient_rows), use_container_width=True, hide_index=True)
                    st.json(snapshot_payload)
            else:
                st.info("記録するアイテムを1つ以上選択してください。")

            st.markdown(
                """
                <style>
                div[data-testid="stButton"] button[kind="primary"] {
                    min-height: 56px;
                    font-size: 1.05rem;
                    font-weight: 700;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            if st.button("✅ 記録する", type="primary", use_container_width=True, key="save_intake_log"):
                if not selected_item_quantities:
                    st.error("保存するには最低1アイテムを選択してください。")
                else:
                    db_manager.insert_intake_log(
                        user_id=user_id,
                        timestamp=intake_timestamp.isoformat(),
                        scene=selected_scene,
                        snapshot_payload=snapshot_payload,
                    )
                    st.success(
                        f"保存しました: {selected_scene} / {intake_timestamp.strftime('%Y-%m-%d %H:%M')}"
                    )
                    st.rerun()

            st.markdown("#### 🕘 直近12時間タイムライン")
            if recent_logs:
                for row in recent_logs:
                    payload = row.get("snapshot_payload") or {}
                    items = payload.get("items", []) if isinstance(payload, dict) else []
                    total_nutrients = payload.get("total_nutrients", {}) if isinstance(payload, dict) else {}
                    intake_log_id = row.get("id")
                    ts = row.get("timestamp")
                    ts_label = str(ts)
                    try:
                        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=JST)
                        ts_label = dt.astimezone(JST).strftime("%m/%d %H:%M")
                    except Exception:
                        pass

                    row_col, action_col = st.columns([6, 2])
                    with row_col:
                        st.caption(
                            f"{ts_label} / {row.get('scene', '-')} / アイテム{len(items)}件 / 成分{len(total_nutrients)}件"
                        )
                    with action_col:
                        if intake_log_id and st.button("🗑️ 取消", key=f"intake_delete_{intake_log_id}"):
                            st.session_state["pending_intake_delete_id"] = intake_log_id

                    if intake_log_id and st.session_state.get("pending_intake_delete_id") == intake_log_id:
                        confirm_col, cancel_col = st.columns([3, 2])
                        with confirm_col:
                            if st.button("この記録を削除", key=f"intake_confirm_delete_{intake_log_id}", type="primary"):
                                db_manager.delete_intake_log(intake_log_id=intake_log_id, user_id=user_id)
                                st.session_state.pop("pending_intake_delete_id", None)
                                st.success("記録を削除しました。")
                                st.rerun()
                        with cancel_col:
                            if st.button("キャンセル", key=f"intake_cancel_delete_{intake_log_id}"):
                                st.session_state.pop("pending_intake_delete_id", None)
                                st.rerun()
            else:
                st.caption("直近12時間の摂取ログはまだありません。")

    with tab_sleep:
        st.subheader("💤 睡眠詳細")
        oura_data = data["oura_data"]

        if oura_data:
            df = pd.DataFrame(oura_data)
            df["measured_at"] = pd.to_datetime(df["measured_at"])
            df = df.sort_values("measured_at", ascending=False)
            df_chart = df.sort_values("measured_at")

            score_cols = ["sleep_score", "activity_score", "readiness_score"]
            if all(col in df.columns for col in score_cols):
                latest_sleep_score = df.iloc[0]["sleep_score"]
                st.markdown(f"### 睡眠スコア推移（現在: {latest_sleep_score}点）")

                fig_sleep = go.Figure()
                fig_sleep.add_trace(go.Scatter(
                    x=df_chart["measured_at"],
                    y=df_chart["sleep_score"],
                    name="睡眠スコア",
                    mode="lines+markers",
                    line=dict(color="#2E7D9A", width=3),
                    marker=dict(size=9, color="#2E7D9A"),
                    hovertemplate="%{x|%m/%d}<br>睡眠スコア: %{y:.0f}点<extra></extra>",
                ))
                fig_sleep.add_trace(go.Scatter(
                    x=df_chart["measured_at"],
                    y=df_chart["activity_score"],
                    name="活動スコア",
                    mode="lines+markers",
                    line=dict(color="#4DB6AC", width=2.5),
                    marker=dict(size=8, color="#4DB6AC"),
                    hovertemplate="%{x|%m/%d}<br>活動スコア: %{y:.0f}点<extra></extra>",
                ))
                fig_sleep.add_trace(go.Scatter(
                    x=df_chart["measured_at"],
                    y=df_chart["readiness_score"],
                    name="レディネス",
                    mode="lines+markers",
                    line=dict(color="#80CBC4", width=2.5),
                    marker=dict(size=8, color="#80CBC4"),
                    hovertemplate="%{x|%m/%d}<br>レディネス: %{y:.0f}点<extra></extra>",
                ))
                fig_sleep.add_hline(
                    y=80,
                    line_width=1.5,
                    line_dash="dash",
                    line_color="#26A69A",
                    annotation_text="目標ライン: 80点",
                    annotation_position="top left",
                )
                fig_sleep.update_layout(
                    height=340,
                    margin=dict(l=0, r=0, t=10, b=0),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                    yaxis=dict(title="スコア", range=[50, 100]),
                    xaxis=dict(title=""),
                    hovermode="x unified",
                    hoverlabel=dict(font_size=14),
                )
                st.plotly_chart(fig_sleep, use_container_width=True)

            st.dataframe(
                df[["measured_at", "sleep_score", "activity_score", "readiness_score", "steps"]].head(10),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("睡眠データがありません")

    with tab_weight:
        st.subheader("⚖️ 体重推移")
        weight_data = data["weight_data"]

        if weight_data:
            df = pd.DataFrame(weight_data)
            df["measured_at"] = pd.to_datetime(df["measured_at"])
            df = df.sort_values("measured_at", ascending=False)
            df_chart = df.sort_values("measured_at")
            latest_weight_kg = df.iloc[0]["weight_kg"]
            target_weight_kg = 60.0

            st.markdown(f"### 体重推移（現在: {latest_weight_kg:.1f}kg）")

            fig_weight = go.Figure()
            fig_weight.add_trace(go.Scatter(
                x=df_chart["measured_at"],
                y=df_chart["weight_kg"],
                name="体重",
                mode="lines+markers",
                line=dict(color="#5DADE2", width=3),
                marker=dict(size=9, color="#90CAF9"),
                hovertemplate="%{x|%m/%d}<br>体重: %{y:.1f}kg<extra></extra>",
            ))
            fig_weight.add_hline(
                y=target_weight_kg,
                line_width=1.5,
                line_dash="dash",
                line_color="#90A4AE",
                annotation_text=f"目標体重: {target_weight_kg:.1f}kg",
                annotation_position="top left",
            )
            fig_weight.update_layout(
                height=320,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                yaxis=dict(title="体重 (kg)"),
                xaxis=dict(title=""),
                hovermode="x unified",
                hoverlabel=dict(font_size=14),
            )
            st.plotly_chart(fig_weight, use_container_width=True)

            st.dataframe(
                df[["measured_at", "weight_kg"]].head(10),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("体重データがありません")

    with tab_env:
        st.subheader("🌡️ 環境ログ")
        if weather_info and weather_info.get("weather_summary"):
            st.caption(f"最新: {weather_info.get('weather_summary', '')} / {weather_info.get('temp', 'ー')}℃")

        try:
            df_corr = db_manager.get_correlation_data(days=analytics_days)
            if df_corr.empty or df_corr["sleep_score"].isna().all():
                st.info("分析に必要なデータがまだありません。Oura の睡眠データが蓄積されると表示されます。")
            else:
                latest_co2 = df_corr["co2_avg"].dropna().iloc[-1] if df_corr["co2_avg"].notna().any() else None
                co2_title = f"CO₂ と睡眠スコア（現在CO₂: {latest_co2:.0f}ppm）" if latest_co2 is not None else "CO₂ と睡眠スコア"
                st.markdown(f"### {co2_title}")

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=df_corr["date"],
                    y=df_corr["sleep_score"],
                    name="睡眠スコア",
                    marker_color="rgba(79,195,247,0.72)",
                    yaxis="y",
                    hovertemplate="%{x}<br>睡眠スコア: %{y:.0f}点<extra></extra>",
                ))

                if df_corr["co2_avg"].notna().any():
                    fig.add_trace(go.Scatter(
                        x=df_corr["date"],
                        y=df_corr["co2_avg"],
                        name="CO₂ (ppm)",
                        mode="lines+markers",
                        line=dict(color="#E64A19", width=3),
                        marker=dict(size=9, color="#F4511E"),
                        yaxis="y2",
                        hovertemplate="%{x}<br>CO₂: %{y:.0f}ppm<extra></extra>",
                    ))
                    fig.add_hline(
                        y=1000,
                        yref="y2",
                        line_width=1.5,
                        line_dash="dash",
                        line_color="#D32F2F",
                        annotation_text="CO₂ 警告ライン: 1000ppm",
                        annotation_position="top left",
                    )

                fig.update_layout(
                    height=360,
                    margin=dict(l=0, r=0, t=30, b=0),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                    yaxis=dict(title="睡眠スコア", range=[0, 100], side="left"),
                    yaxis2=dict(title="CO₂ (ppm)", overlaying="y", side="right", showgrid=False),
                    xaxis=dict(title=""),
                    bargap=0.3,
                    hovermode="x unified",
                    hoverlabel=dict(font_size=14),
                )
                st.plotly_chart(fig, use_container_width=True)

                has_temp = df_corr["temp_avg"].notna().any()
                has_hum = df_corr["humidity_avg"].notna().any()
                if has_temp or has_hum:
                    latest_temp = df_corr["temp_avg"].dropna().iloc[-1] if has_temp else None
                    temp_title = f"室温・湿度の推移（現在室温: {latest_temp:.1f}℃）" if latest_temp is not None else "室温・湿度の推移"
                    st.markdown(f"### {temp_title}")

                    fig2 = go.Figure()
                    if has_temp:
                        fig2.add_trace(go.Scatter(
                            x=df_corr["date"],
                            y=df_corr["temp_avg"],
                            name="室温 (℃)",
                            mode="lines+markers",
                            line=dict(color="#F57C00", width=3),
                            marker=dict(size=9, color="#FB8C00"),
                            hovertemplate="%{x}<br>室温: %{y:.1f}℃<extra></extra>",
                        ))
                        fig2.add_hline(
                            y=28,
                            line_width=1.5,
                            line_dash="dash",
                            line_color="#E53935",
                            annotation_text="高温注意ライン: 28℃",
                            annotation_position="top left",
                        )
                    if has_hum:
                        fig2.add_trace(go.Scatter(
                            x=df_corr["date"],
                            y=df_corr["humidity_avg"],
                            name="湿度 (%)",
                            mode="lines+markers",
                            line=dict(color="#90A4AE", width=2.5),
                            marker=dict(size=8, color="#B0BEC5"),
                            yaxis="y2",
                            hovertemplate="%{x}<br>湿度: %{y:.1f}%<extra></extra>",
                        ))
                    fig2.update_layout(
                        height=300,
                        margin=dict(l=0, r=0, t=10, b=0),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                        yaxis=dict(title="室温 (℃)", side="left"),
                        yaxis2=dict(title="湿度 (%)", overlaying="y", side="right", showgrid=False),
                        hovermode="x unified",
                        hoverlabel=dict(font_size=14),
                    )
                    st.plotly_chart(fig2, use_container_width=True)

                with st.expander("📋 データテーブル", expanded=False):
                    st.dataframe(df_corr, use_container_width=True, hide_index=True)
        except Exception as e:
            logger.warning(f"Deep Analytics error: {e}")
            st.caption("📊 分析データの取得中にエラーが発生しました。")

    with tab_server:
        st.subheader("🖥️ サーバー・ヘルス")
        st.caption("保存先: data/system_health.db（SQLite, Supabaseとは完全分離）")

        period_map = {
            "24時間": 24,
            "1週間": 24 * 7,
            "1ヶ月": 24 * 30,
        }
        selected_period = st.radio(
            "表示期間",
            options=list(period_map.keys()),
            horizontal=True,
            index=0,
            key="server_health_period",
        )

        # 表示時にも5分周期で最新サンプルを確保
        collect_system_health_sample()

        records = load_system_health_history(period_map[selected_period])
        df_health = _system_health_records_to_df(records)

        if df_health.empty:
            st.info("システムヘルスデータがまだありません。数分後に再表示してください。")
        else:
            max_points = 720 if selected_period == "1ヶ月" else 2000
            df_plot = _downsample_df(df_health, max_points=max_points)
            cfg = _get_system_health_ui_config()

            peak_temp = df_health["cpu_temp_c"].max(skipna=True)
            avg_cpu = df_health["cpu_percent"].mean(skipna=True)
            avg_memory = df_health["memory_percent"].mean(skipna=True)
            avg_disk = df_health["disk_percent"].mean(skipna=True)

            k1, k2, k3, k4 = st.columns(4)
            with k1:
                if pd.notna(peak_temp):
                    st.metric("最高温度", f"{float(peak_temp):.1f}°C")
                else:
                    st.metric("最高温度", "N/A")
            with k2:
                st.metric("平均CPU負荷", f"{float(avg_cpu):.1f}%")
            with k3:
                st.metric("平均メモリ", f"{float(avg_memory):.1f}%")
            with k4:
                st.metric("平均ディスク", f"{float(avg_disk):.1f}%")

            fig_temp = go.Figure()
            fig_temp.add_trace(go.Scatter(
                x=df_plot["measured_at"],
                y=df_plot["cpu_temp_c"],
                name="CPU温度",
                mode="lines",
                line=dict(color="#ef4444", width=2.5),
                hovertemplate="%{x|%m/%d %H:%M}<br>CPU温度: %{y:.1f}°C<extra></extra>",
            ))
            fig_temp.add_hline(
                y=cfg["temp_warn_c"],
                line_width=1,
                line_dash="dash",
                line_color="#d97706",
                annotation_text=f"警告 {cfg['temp_warn_c']:.0f}°C",
                annotation_position="top left",
            )
            fig_temp.add_hline(
                y=cfg["temp_critical_c"],
                line_width=1,
                line_dash="dash",
                line_color="#dc2626",
                annotation_text=f"危険 {cfg['temp_critical_c']:.0f}°C",
                annotation_position="top left",
            )
            fig_temp.update_layout(
                height=280,
                margin=dict(l=0, r=0, t=20, b=0),
                xaxis=dict(title=""),
                yaxis=dict(title="温度 (°C)"),
                hovermode="x unified",
            )
            st.plotly_chart(fig_temp, use_container_width=True)

            fig_usage = go.Figure()
            fig_usage.add_trace(go.Scatter(
                x=df_plot["measured_at"],
                y=df_plot["cpu_percent"],
                name="CPU",
                mode="lines",
                line=dict(color="#2563eb", width=2.2),
            ))
            fig_usage.add_trace(go.Scatter(
                x=df_plot["measured_at"],
                y=df_plot["memory_percent"],
                name="Memory",
                mode="lines",
                line=dict(color="#0891b2", width=2.2),
            ))
            fig_usage.add_trace(go.Scatter(
                x=df_plot["measured_at"],
                y=df_plot["disk_percent"],
                name="Disk",
                mode="lines",
                line=dict(color="#4f46e5", width=2.2),
            ))
            fig_usage.update_layout(
                height=300,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(title=""),
                yaxis=dict(title="使用率 (%)", range=[0, 100]),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            )
            st.plotly_chart(fig_usage, use_container_width=True)

            if len(df_plot) < len(df_health):
                st.caption(f"1ヶ月表示の見やすさのため、{len(df_health)}点 → {len(df_plot)}点に間引いて表示しています。")
            else:
                st.caption(f"表示ポイント数: {len(df_plot)}")


if __name__ == "__main__":
    main()
