"""
AI Insights - Gemini Deep Insight + 相関分析
健康データの深い洞察と環境データとの相関を可視化
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from ui_lib.session import get_database_manager, load_gemini_settings, get_gemini_evaluator
from components.responsive import inject_responsive_css, responsive_columns
from components.charts import create_co2_sleep_correlation_chart, create_temp_humidity_chart

JST = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="AI Insights - YuruHealth",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

inject_responsive_css()

st.title("🧠 AI Insights")
st.caption("Gemini Deep Insight + 環境データ相関分析")

db_manager = get_database_manager()
gemini_settings = load_gemini_settings()

# サイドバー設定
with st.sidebar:
    st.header("⚙️ 分析設定")
    
    # 分析対象日
    insight_date = st.date_input(
        "分析対象日",
        value=datetime.now(JST).date() - timedelta(days=1),
        max_value=datetime.now(JST).date(),
        key="insight_date"
    )
    
    # モデル選択
    default_model = gemini_settings.get("model_name", "gemini-2.0-flash")
    available_models = gemini_settings.get("available_models") or [default_model]
    selected_model = st.selectbox(
        "Gemini モデル",
        options=available_models,
        index=0 if default_model in available_models else 0,
        key="selected_model"
    )
    
    # 相関分析期間
    analytics_days = st.select_slider(
        "相関分析期間",
        options=[7, 14, 30, 60, 90],
        value=30,
        key="analytics_days"
    )

# Gemini Deep Insight セクション
st.header("🔍 Gemini Deep Insight")

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

# 日付変更時はDBの最新結果を基準に表示を同期
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
            st.warning(f"⚠️ {target_date} の生データがありません。データを更新してください。")
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

# 環境データ相関分析セクション
st.header("📊 環境データ相関分析")

try:
    df_corr = db_manager.get_correlation_data(days=analytics_days)
    
    if df_corr.empty or df_corr["sleep_score"].isna().all():
        st.info("分析に必要なデータがまだありません。Oura の睡眠データが蓄積されると表示されます。")
    else:
        # CO2と睡眠スコアの相関
        latest_co2 = df_corr["co2_avg"].dropna().iloc[-1] if df_corr["co2_avg"].notna().any() else None
        co2_title = f"CO₂ と睡眠スコア（現在CO₂: {latest_co2:.0f}ppm）" if latest_co2 is not None else "CO₂ と睡眠スコア"
        st.markdown(f"### {co2_title}")
        
        fig_co2 = create_co2_sleep_correlation_chart(df_corr)
        st.plotly_chart(fig_co2, use_container_width=True)
        
        # 室温・湿度の推移
        has_temp = df_corr["temp_avg"].notna().any()
        has_hum = df_corr["humidity_avg"].notna().any()
        
        if has_temp or has_hum:
            latest_temp = df_corr["temp_avg"].dropna().iloc[-1] if has_temp else None
            temp_title = f"室温・湿度の推移（現在室温: {latest_temp:.1f}℃）" if latest_temp is not None else "室温・湿度の推移"
            st.markdown(f"### {temp_title}")
            
            fig_temp = create_temp_humidity_chart(df_corr)
            st.plotly_chart(fig_temp, use_container_width=True)
        
        # データテーブル
        with st.expander("📋 データテーブル", expanded=False):
            st.dataframe(df_corr, use_container_width=True, hide_index=True)
            
except Exception as e:
    st.error(f"相関分析エラー: {e}")
    st.caption("データベース接続を確認してください。")
