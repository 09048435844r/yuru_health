import logging
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

logger = logging.getLogger(__name__)
from src.database_manager import DatabaseManager
from src.fetchers.withings_fetcher import WithingsFetcher
from src.fetchers.oura_fetcher import OuraFetcher
from src.fetchers.weather_fetcher import WeatherFetcher
from src.fetchers.switchbot_fetcher import SwitchBotFetcher
from auth.withings_oauth import WithingsOAuth
from src.evaluators.gemini_evaluator import GeminiEvaluator
from auth.google_oauth import GoogleOAuth
from src.fetchers.google_fit_fetcher import GoogleFitFetcher
from src.utils.sparkline import build_footprint_html
from src.utils.config_loader import load_settings

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
    if obj is None or not hasattr(obj, "_payload_hash"):
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
            if withings_oauth.is_authenticated():
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
                if google_oauth.is_authenticated():
                    st.success("✅ Google Fit: 認証済み")
                else:
                    st.warning("⚠️ Google Fit: 未認証")

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
    rich_history = db_manager.get_data_arrival_rich(days=30)
    footprint_keys_df = pd.DataFrame(
        [{"source": source, "fetched_date": fetched_date} for (source, fetched_date) in rich_history.keys()]
    )
    if not footprint_keys_df.empty:
        recent_dates = (
            footprint_keys_df.sort_values("fetched_date")["fetched_date"]
            .drop_duplicates()
            .tail(7)
            .tolist()
        )
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
        auth_code = query_params.get("code")
        if auth_code and not google_oauth.is_authenticated():
            if google_oauth.exchange_code_for_token(auth_code):
                st.query_params.clear()
                st.rerun()

    # ── タブ化 UI ──
    tab_summary, tab_sleep, tab_weight, tab_env = st.tabs([
        "📊 サマリー",
        "💤 睡眠詳細",
        "⚖️ 体重推移",
        "🌡️ 環境ログ",
    ])

    with tab_summary:
        if "deep_insight" not in st.session_state:
            st.session_state.deep_insight = ""

        evaluator = get_gemini_evaluator(default_model)
        insight_container = st.container()

        if evaluator.is_available():
            if st.button("🔍 Gemini 分析（Deep Insight） / 再分析", use_container_width=True):
                target_date = insight_date.strftime("%Y-%m-%d")
                with st.spinner("Geminiが昨日のデータを読み解いています..."):
                    raw_data = db_manager.get_raw_data_by_date(target_date)
                    if not raw_data:
                        st.session_state.deep_insight = ""
                        st.warning(f"⚠️ {target_date} の生データがありません。🔄ボタンでデータを更新してください。")
                    else:
                        st.session_state.deep_insight = evaluator.deep_analyze(raw_data, target_model=selected_model)

        with insight_container:
            if st.session_state.deep_insight:
                st.success(st.session_state.deep_insight.split("\n")[0])
                with st.expander("📋 詳細分析を見る", expanded=False):
                    st.markdown(st.session_state.deep_insight)
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

    with tab_sleep:
        st.subheader("� 睡眠詳細")
        oura_data = data["oura_data"]

        if oura_data:
            df = pd.DataFrame(oura_data)
            df["measured_at"] = pd.to_datetime(df["measured_at"])
            df = df.sort_values("measured_at", ascending=False)

            score_cols = ["sleep_score", "activity_score", "readiness_score"]
            if all(col in df.columns for col in score_cols):
                st.line_chart(df.set_index("measured_at")[score_cols], use_container_width=True)

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

            st.line_chart(df.set_index("measured_at")["weight_kg"], use_container_width=True)

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
                import plotly.graph_objects as go

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=df_corr["date"],
                    y=df_corr["sleep_score"],
                    name="睡眠スコア",
                    marker_color="rgba(126,87,194,0.7)",
                    yaxis="y",
                ))

                if df_corr["co2_avg"].notna().any():
                    fig.add_trace(go.Scatter(
                        x=df_corr["date"],
                        y=df_corr["co2_avg"],
                        name="CO₂ (ppm)",
                        mode="lines+markers",
                        line=dict(color="#FF7043", width=2),
                        marker=dict(size=5),
                        yaxis="y2",
                    ))

                fig.update_layout(
                    height=360,
                    margin=dict(l=0, r=0, t=30, b=0),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                    yaxis=dict(title="睡眠スコア", range=[0, 100], side="left"),
                    yaxis2=dict(title="CO₂ (ppm)", overlaying="y", side="right", showgrid=False),
                    xaxis=dict(title=""),
                    bargap=0.3,
                )
                st.plotly_chart(fig, use_container_width=True)

                has_temp = df_corr["temp_avg"].notna().any()
                has_hum = df_corr["humidity_avg"].notna().any()
                if has_temp or has_hum:
                    fig2 = go.Figure()
                    if has_temp:
                        fig2.add_trace(go.Scatter(
                            x=df_corr["date"],
                            y=df_corr["temp_avg"],
                            name="室温 (℃)",
                            mode="lines+markers",
                            line=dict(color="#26A69A", width=2),
                        ))
                    if has_hum:
                        fig2.add_trace(go.Scatter(
                            x=df_corr["date"],
                            y=df_corr["humidity_avg"],
                            name="湿度 (%)",
                            mode="lines+markers",
                            line=dict(color="#42A5F5", width=2),
                            yaxis="y2",
                        ))
                    fig2.update_layout(
                        height=280,
                        margin=dict(l=0, r=0, t=10, b=0),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                        yaxis=dict(title="室温 (℃)", side="left"),
                        yaxis2=dict(title="湿度 (%)", overlaying="y", side="right", showgrid=False),
                    )
                    st.plotly_chart(fig2, use_container_width=True)

                with st.expander("📋 データテーブル", expanded=False):
                    st.dataframe(df_corr, use_container_width=True, hide_index=True)
        except Exception as e:
            logger.warning(f"Deep Analytics error: {e}")
            st.caption("📊 分析データの取得中にエラーが発生しました。")


if __name__ == "__main__":
    main()
