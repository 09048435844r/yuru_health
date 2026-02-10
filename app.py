import logging
import streamlit as st
import pandas as pd
import yaml
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
from src.database_manager import DatabaseManager
from src.withings_fetcher import WithingsFetcher
from src.fetchers.oura_fetcher import OuraFetcher
from src.fetchers.weather_fetcher import WeatherFetcher
from src.fetchers.switchbot_fetcher import SwitchBotFetcher
from auth.withings_oauth import WithingsOAuth
from src.evaluators.gemini_evaluator import GeminiEvaluator
from auth.google_oauth import GoogleOAuth
from src.fetchers.google_fit_fetcher import GoogleFitFetcher, GOOGLE_FIT_AVAILABLE

try:
    from streamlit_js_eval import get_geolocation
    GEOLOCATION_AVAILABLE = True
except ImportError:
    GEOLOCATION_AVAILABLE = False


st.set_page_config(
    page_title="YuruHealth",
    page_icon="💚",
    layout="centered",
    initial_sidebar_state="collapsed"
)


def get_database_manager():
    obj = st.session_state.get("_db_manager")
    if obj is None or not hasattr(obj, "_payload_key_count"):
        st.session_state["_db_manager"] = DatabaseManager("config/secrets.yaml")
    return st.session_state["_db_manager"]


def get_withings_oauth(db_manager):
    if "_withings_oauth" not in st.session_state:
        st.session_state["_withings_oauth"] = WithingsOAuth(db_manager)
    return st.session_state["_withings_oauth"]


@st.cache_resource
def load_gemini_settings():
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)
        return settings.get("gemini", {})


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


def refresh_data(db_manager: DatabaseManager, user_id: str = "user_001"):
    """データを更新"""
    try:
        with st.spinner("データを更新中..."):
            logger.info("=== refresh_data started ===")
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=7)
            start_str = start_dt.strftime("%Y-%m-%d")
            end_str = end_dt.strftime("%Y-%m-%d")
            
            # Withingsデータ取得
            withings_oauth = get_withings_oauth(db_manager)
            if withings_oauth.is_authenticated():
                logger.info("Withings: authenticated, fetching data...")
                try:
                    with open("config/settings.yaml", "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f)
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
                with open("config/settings.yaml", "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
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
    
    # Withings OAuth コールバック処理
    withings_oauth = get_withings_oauth(db_manager)
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
    latest_weight = data["latest_weight"]
    latest_oura = data["latest_oura"]
    
    # 環境情報表示（さりげなく）
    env_log = db_manager.get_latest_environmental_log()
    weather_info = st.session_state.get("latest_weather") or env_log
    
    # ── 最上部: メトリクス (天気・レディネス・体重) ──
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if weather_info and weather_info.get("temp") is not None:
            summary = weather_info.get("weather_summary", "")
            st.metric(label=f"🌤 {summary}", value=f"{weather_info['temp']}℃")
        else:
            st.metric(label="🌤 天気", value="--")
    
    with col2:
        if latest_oura and latest_oura.get('readiness_score'):
            st.metric(
                label="💪 レディネス",
                value=f"{latest_oura.get('readiness_score')}点"
            )
        else:
            st.metric(label="� レディネス", value="--")
    
    with col3:
        if latest_weight and latest_weight.get('weight_kg'):
            weight = latest_weight.get('weight_kg')
            st.metric(label="⚖️ 体重", value=f"{weight}kg")
        else:
            st.metric(label="⚖️ 体重", value="--")
    
    # データ更新ボタン
    col_spacer, col_btn = st.columns([3, 1])
    with col_btn:
        if st.button("🔄 更新", use_container_width=True):
            refresh_data(db_manager)
    
    st.markdown("---")
    
    # ── 記録の足跡 (Data Footprints) ──
    st.subheader("👣 記録の足跡")
    
    arrival_history = db_manager.get_data_arrival_history(days=14)
    
    source_labels = {
        "oura": "Oura Ring",
        "withings": "Withings",
        "google_fit": "Google Fit",
        "weather": "Weather",
        "switchbot": "SwitchBot",
    }
    
    today = datetime.now().date()
    date_range = [(today - timedelta(days=i)) for i in range(13, -1, -1)]
    
    arrival_set = set()
    for row in arrival_history:
        arrival_set.add((row["source"], row["recorded_at"]))
    
    total_dots = 0
    green_dots = 0
    
    for source_key, source_label in source_labels.items():
        cols = st.columns([2] + [1] * 14)
        cols[0].caption(source_label)
        for i, d in enumerate(date_range):
            date_str = d.strftime("%Y-%m-%d")
            total_dots += 1
            if (source_key, date_str) in arrival_set:
                cols[i + 1].markdown("🟢")
                green_dots += 1
            else:
                cols[i + 1].markdown("⚪")
    
    date_header_cols = st.columns([2] + [1] * 14)
    date_header_cols[0].caption("")
    for i, d in enumerate(date_range):
        date_header_cols[i + 1].caption(d.strftime("%d"))
    
    if green_dots > 0:
        rate = green_dots / total_dots * 100
        st.success(f"🎉 過去14日間で **{green_dots}件** のデータが届いています（到達率 {rate:.0f}%）。記録を続けていること自体が素晴らしい！")
    else:
        st.info("まだデータがありません。� ボタンでデータを取得してみましょう。")
    
    st.markdown("---")
    
    # ── サブメトリクス ──
    col4, col5, col6 = st.columns(3)
    
    with col4:
        if latest_oura and latest_oura.get('sleep_score'):
            st.metric(label="😴 睡眠", value=f"{latest_oura.get('sleep_score')}点")
        else:
            st.metric(label="😴 睡眠", value="--")
    
    with col5:
        if latest_oura and latest_oura.get('activity_score'):
            st.metric(label="🏃 活動", value=f"{latest_oura.get('activity_score')}点")
        else:
            st.metric(label="🏃 活動", value="--")
    
    with col6:
        if latest_oura and latest_oura.get('steps'):
            st.metric(label="🚶 歩数", value=f"{latest_oura.get('steps'):,}歩")
        else:
            st.metric(label="🚶 歩数", value="--")
    
    st.markdown("---")
    
    # ── AI Deep Insight (生データ分析) ──
    model_name = gemini_settings.get("model_name", "gemini-1.5-flash")
    evaluator = get_gemini_evaluator(model_name)
    
    if evaluator.is_available():
        if st.button("🔍 AI Deep Insight (生データ分析)", use_container_width=True):
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            with st.spinner("生データを取得中..."):
                raw_data = db_manager.get_raw_data_by_date(yesterday)
            if not raw_data:
                st.warning(f"⚠️ {yesterday} の生データがありません。🔄ボタンでデータを更新してください。")
            else:
                with st.spinner("🔍 Deep Insight 分析中..."):
                    insight = evaluator.deep_analyze(raw_data)
                st.success(insight.split("\n")[0] if insight else "分析結果なし")
                with st.expander("� 詳細分析を見る", expanded=False):
                    st.markdown(insight)
    
    st.markdown("---")
    
    # ── 詳細データ（エキスパンダー） ──
    with st.expander("📈 詳細データ", expanded=False):
        tab1, tab2 = st.tabs(["体重", "Oura"])
        
        with tab1:
            st.subheader("体重データ")
            weight_data = data["weight_data"]
            
            if weight_data:
                df = pd.DataFrame(weight_data)
                df['measured_at'] = pd.to_datetime(df['measured_at'])
                df = df.sort_values('measured_at', ascending=False)
                
                st.line_chart(
                    df.set_index('measured_at')['weight_kg'],
                    use_container_width=True
                )
                
                st.dataframe(
                    df[['measured_at', 'weight_kg']].head(10),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("データがありません")
        
        with tab2:
            st.subheader("Oura Ringデータ")
            oura_data = data["oura_data"]
            
            if oura_data:
                df = pd.DataFrame(oura_data)
                df['measured_at'] = pd.to_datetime(df['measured_at'])
                df = df.sort_values('measured_at', ascending=False)
                
                score_cols = ['sleep_score', 'activity_score', 'readiness_score']
                if all(col in df.columns for col in score_cols):
                    st.line_chart(
                        df.set_index('measured_at')[score_cols],
                        use_container_width=True
                    )
                
                st.dataframe(
                    df[['measured_at', 'sleep_score', 'activity_score', 'readiness_score', 'steps']].head(10),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("データがありません")
    
    # Google Fit データ表示
    google_oauth = get_google_oauth(db_manager)
    if google_oauth.is_available():
        google_oauth.ensure_credentials()
        
        # OAuth コールバック処理
        query_params = st.query_params
        auth_code = query_params.get("code")
        if auth_code and not google_oauth.is_authenticated():
            if google_oauth.exchange_code_for_token(auth_code):
                st.query_params.clear()
                st.rerun()
        
        with st.expander("🏃 Google Fit データ", expanded=False):
            if google_oauth.is_authenticated():
                st.success("✅ Google Fit: 認証済み")
                
                if st.button("📥 Google Fit データ取得"):
                    try:
                        creds = google_oauth.get_credentials()
                        if creds:
                            fetcher = GoogleFitFetcher(creds, db_manager=db_manager)
                            end_dt = datetime.now()
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
                
                # 保存済みデータ表示
                gfit_steps = db_manager.get_google_fit_data(user_id="user_001", data_type="steps", limit=7)
                gfit_sleep = db_manager.get_google_fit_data(user_id="user_001", data_type="sleep", limit=7)
                
                if gfit_steps:
                    st.markdown("**📊 歩数 (直近7日)**")
                    df_steps = pd.DataFrame(gfit_steps)
                    df_steps["date"] = pd.to_datetime(df_steps["date"])
                    df_steps = df_steps.sort_values("date")
                    st.bar_chart(df_steps.set_index("date")["value"], use_container_width=True)
                
                if gfit_sleep:
                    st.markdown("**😴 睡眠時間 (直近7日, 分)**")
                    df_sleep = pd.DataFrame(gfit_sleep)
                    df_sleep["date"] = pd.to_datetime(df_sleep["date"])
                    df_sleep = df_sleep.sort_values("date")
                    st.bar_chart(df_sleep.set_index("date")["value"], use_container_width=True)
                
                if st.button("🚪 Google Fit ログアウト"):
                    google_oauth.logout()
                    st.rerun()
            else:
                st.info("Google Fit に接続して、Samsung Health のデータを取得できます。")
                auth_url = google_oauth.get_authorization_url()
                st.link_button("🔗 Google Fit にログイン", auth_url)
    
    # 設定（サイドバー - 折りたたみ）
    with st.sidebar:
        st.header("⚙️ 設定")
        
        with st.expander("🔐 API連携", expanded=False):
            if withings_oauth.is_authenticated():
                st.success("✅ Withings: 認証済み")
                if st.button("🔓 Withings認証解除"):
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
                if google_oauth.is_authenticated():
                    st.success("✅ Google Fit: 認証済み")
                else:
                    st.warning("⚠️ Google Fit: 未認証")
        
        with st.expander("ℹ️ システム情報", expanded=False):
            st.info(f"**環境:** {db_manager.env}")
            st.info(f"**DB:** {db_manager.db_config['type']}")
            st.caption(f"Model: {gemini_settings.get('model_name', 'N/A')}")


if __name__ == "__main__":
    main()
