"""
Settings - API連携設定
OAuth認証とデータ取得
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from ui_lib.session import get_database_manager, get_google_oauth, has_oauth_token
from ui_lib.formatters import minutes_to_hhmm, extract_sleep_chosen_app, to_jst_date_text
from ui_lib.data_fetcher import get_google_fit_sleep_policy
from components.responsive import inject_responsive_css
from src.fetchers.google_fit_fetcher import GoogleFitFetcher

JST = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="Settings - YuruHealth",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

inject_responsive_css()

st.title("⚙️ API連携設定")
st.caption("OAuth認証とデータ取得")

db_manager = get_database_manager()
google_oauth = get_google_oauth(db_manager)

# Google Fit セクション
st.header("🏃 Google Fit")

if google_oauth.is_authenticated():
    st.success("✅ Google Fit: 認証済み")
    
    if st.button("📥 Google Fit データ取得（過去7日）", use_container_width=True):
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
    
    # 歩数データ表示
    gfit_steps = db_manager.get_google_fit_data(user_id="user_001", data_type="steps", limit=7)
    if gfit_steps:
        st.markdown("**📊 歩数 (直近7日)**")
        df_steps = pd.DataFrame(gfit_steps)
        df_steps["date"] = pd.to_datetime(df_steps["date"])
        df_steps = df_steps.sort_values("date")
        st.bar_chart(df_steps.set_index("date")["value"], use_container_width=True)
    
    # 睡眠データ表示
    gfit_sleep = db_manager.get_google_fit_data(user_id="user_001", data_type="sleep", limit=7)
    if gfit_sleep:
        st.markdown("**😴 睡眠時間 (直近7日, h:mm)**")
        st.caption(f"source policy: {get_google_fit_sleep_policy()}")
        df_sleep = pd.DataFrame(gfit_sleep)
        df_sleep["date"] = pd.to_datetime(df_sleep["date"])
        df_sleep = df_sleep.sort_values("date")
        df_sleep["sleep_hhmm"] = df_sleep["value"].apply(minutes_to_hhmm)
        df_sleep["source"] = df_sleep.get("raw_data", pd.Series([None] * len(df_sleep))).apply(extract_sleep_chosen_app)
        st.dataframe(
            df_sleep[["date", "sleep_hhmm", "source"]].rename(columns={"date": "日付", "sleep_hhmm": "睡眠", "source": "採用ソース"}),
            use_container_width=True,
            hide_index=True,
        )
    
    if st.button("🚪 Google Fit ログアウト", use_container_width=True):
        google_oauth.logout()
        st.rerun()
else:
    if google_oauth.is_available():
        st.info("Google Fit に接続して、Samsung Health のデータを取得できます。")
        st.caption("初回のみブラウザ認証が必要です。")
        auth_url = google_oauth.get_authorization_url()
        st.link_button("🔗 Google Fit にログイン", auth_url, use_container_width=True)
    else:
        st.warning("Google Fit 連携が未設定です。config/secrets.yaml を確認してください。")

# その他のAPI連携情報
st.header("📡 その他のAPI連携")

api_status = []

# Oura Ring
if has_oauth_token(db_manager, "oura"):
    api_status.append({"API": "Oura Ring", "状態": "✅ 設定済み"})
else:
    api_status.append({"API": "Oura Ring", "状態": "⚠️ 未設定"})

# Withings
if has_oauth_token(db_manager, "withings"):
    api_status.append({"API": "Withings", "状態": "✅ 認証済み"})
else:
    api_status.append({"API": "Withings", "状態": "⚠️ 未認証"})

# SwitchBot
try:
    from src.utils.secrets_loader import load_secrets
    secrets = load_secrets()
    if secrets.get("switchbot", {}).get("token"):
        api_status.append({"API": "SwitchBot", "状態": "✅ 設定済み"})
    else:
        api_status.append({"API": "SwitchBot", "状態": "⚠️ 未設定"})
except:
    api_status.append({"API": "SwitchBot", "状態": "⚠️ 未設定"})

# Weather
try:
    from src.utils.secrets_loader import load_secrets
    secrets = load_secrets()
    if secrets.get("openweathermap", {}).get("api_key"):
        api_status.append({"API": "OpenWeatherMap", "状態": "✅ 設定済み"})
    else:
        api_status.append({"API": "OpenWeatherMap", "状態": "⚠️ 未設定"})
except:
    api_status.append({"API": "OpenWeatherMap", "状態": "⚠️ 未設定"})

st.dataframe(pd.DataFrame(api_status), use_container_width=True, hide_index=True)

st.info("詳細な設定は `config/secrets.yaml` を編集してください。")
