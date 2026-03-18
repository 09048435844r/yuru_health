"""
YuruHealth - メインダッシュボード
今日のコンディションを瞬時に把握
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone

# UI Library & Components
from ui_lib.session import get_database_manager, get_google_oauth
from ui_lib.data_fetcher import fetch_latest_data
from components.responsive import inject_responsive_css, responsive_columns
from components.metrics import display_health_metrics, display_weight_metric
from components.charts import create_sleep_score_chart, create_weight_chart

# Fetchers
from src.fetchers.weather_fetcher import WeatherFetcher

JST = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="YuruHealth - Dashboard",
    page_icon="💚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Galaxy Z Fold 7対応のレスポンシブCSS注入
inject_responsive_css()

# ヘッダー
st.title("💚 YuruHealth")
st.caption("ゆるストイック健康管理 - 今日のコンディション")

# データベース接続
db_manager = get_database_manager()
google_oauth = get_google_oauth(db_manager)

# 最新データ取得
try:
    data = fetch_latest_data(db_manager)
    latest_weight = data["latest_weight"]
    latest_oura = data["latest_oura"]
    weight_data = data["weight_data"]
    oura_data = data["oura_data"]
except Exception as e:
    st.error(f"データ取得エラー: {e}")
    st.stop()

# 天気情報取得
weather_info = {}
try:
    weather_fetcher = WeatherFetcher(db_manager=db_manager)
    if weather_fetcher.is_available():
        weather_data = weather_fetcher.fetch_data("user_001")
        if weather_data:
            weather_info = weather_data[0] if isinstance(weather_data, list) else weather_data
except Exception:
    pass

# サイドバー
with st.sidebar:
    st.header("🔄 データ更新")
    
    if st.button("📥 全データ更新", use_container_width=True):
        with st.spinner("データ更新中..."):
            try:
                # Google Fit
                if google_oauth.is_authenticated():
                    from src.fetchers.google_fit_fetcher import GoogleFitFetcher
                    creds = google_oauth.get_credentials()
                    if creds:
                        fetcher = GoogleFitFetcher(creds, db_manager=db_manager)
                        end_dt = datetime.now(JST)
                        start_dt = end_dt - timedelta(days=3)
                        fit_data = fetcher.fetch_all("user_001", start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))
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
                                except Exception:
                                    pass
                
                # Oura
                try:
                    from src.fetchers.oura_fetcher import OuraFetcher
                    oura_fetcher = OuraFetcher(db_manager=db_manager)
                    if oura_fetcher.is_available():
                        oura_fetcher.fetch_data("user_001")
                except Exception:
                    pass
                
                # Withings
                try:
                    from src.fetchers.withings_fetcher import WithingsFetcher
                    from auth.withings_oauth import WithingsOAuth
                    withings_oauth = WithingsOAuth(db_manager)
                    if withings_oauth.is_authenticated():
                        withings_fetcher = WithingsFetcher(withings_oauth, db_manager=db_manager)
                        withings_fetcher.fetch_data("user_001")
                except Exception:
                    pass
                
                # Weather
                if weather_fetcher.is_available():
                    weather_fetcher.fetch_data("user_001")
                
                # SwitchBot
                try:
                    from src.fetchers.switchbot_fetcher import SwitchBotFetcher
                    switchbot_fetcher = SwitchBotFetcher(db_manager=db_manager)
                    if switchbot_fetcher.is_available():
                        switchbot_fetcher.fetch_data("user_001")
                except Exception:
                    pass
                
                st.success("✅ データ更新完了")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 更新エラー: {e}")
    
    st.divider()
    
    # 天気情報
    if weather_info:
        st.markdown("### 🌤️ 現在の天気")
        if weather_info.get("weather_summary"):
            st.caption(f"{weather_info.get('weather_summary', '')} / {weather_info.get('temp', 'ー')}℃")

# メインコンテンツ
st.header("📊 今日のコンディション")

# 健康メトリクス（レディネス、活動、歩数）
display_health_metrics(latest_oura)

st.divider()

# 2カラムレイアウト
col_left, col_right = responsive_columns(2)

with col_left:
    st.subheader("💤 睡眠スコア推移")
    if oura_data:
        df = pd.DataFrame(oura_data)
        df["measured_at"] = pd.to_datetime(df["measured_at"])
        df = df.sort_values("measured_at", ascending=False)
        df_chart = df.sort_values("measured_at")
        
        score_cols = ["sleep_score", "activity_score", "readiness_score"]
        if all(col in df.columns for col in score_cols):
            latest_sleep_score = df.iloc[0]["sleep_score"]
            st.caption(f"現在: {latest_sleep_score}点")
            
            fig_sleep = create_sleep_score_chart(df_chart)
            st.plotly_chart(fig_sleep, use_container_width=True)
            
            # データテーブル
            with st.expander("📋 詳細データ", expanded=False):
                st.dataframe(
                    df[["measured_at", "sleep_score", "activity_score", "readiness_score", "steps"]].head(10),
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.info("睡眠スコアデータがありません")
    else:
        st.info("Ouraデータがありません")

with col_right:
    st.subheader("⚖️ 体重推移")
    if weight_data:
        df = pd.DataFrame(weight_data)
        df["measured_at"] = pd.to_datetime(df["measured_at"])
        df = df.sort_values("measured_at", ascending=False)
        df_chart = df.sort_values("measured_at")
        latest_weight_kg = df.iloc[0]["weight_kg"]
        target_weight_kg = 60.0
        
        st.caption(f"現在: {latest_weight_kg:.1f}kg")
        
        fig_weight = create_weight_chart(df_chart, target_weight_kg)
        st.plotly_chart(fig_weight, use_container_width=True)
        
        # データテーブル
        with st.expander("📋 詳細データ", expanded=False):
            st.dataframe(
                df[["measured_at", "weight_kg"]].head(10),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("体重データがありません")

st.divider()

# ナビゲーション案内
st.info("""
� **他のページへのアクセス**

サイドバー（左上の > ボタン）から以下のページにアクセスできます：
- 📊 **Timeline**: 記録の足跡（データ到達状況）
- 🧠 **AI Insights**: Gemini分析 + 環境相関分析
- 🍽️ **Intake Log**: 摂取記録・トラッキング
- ⚙️ **Settings**: API連携設定
- 🖥️ **Server Health**: システムヘルス監視
""")

# フッター
st.divider()
st.caption("YuruHealth - ゆるストイック健康管理システム")
