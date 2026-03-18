"""
Timeline - 記録の足跡
データ到達状況をSparklineで可視化
"""
import streamlit as st
from datetime import datetime, timedelta, timezone
from ui_lib.session import get_database_manager
from components.responsive import inject_responsive_css
from src.utils.sparkline import build_footprint_html

JST = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="Timeline - YuruHealth",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

inject_responsive_css()

st.title("📊 記録の足跡")
st.caption("過去のデータ到達状況を可視化")

db_manager = get_database_manager()

# 表示日数の選択
days = st.select_slider(
    "表示期間",
    options=[7, 14, 30],
    value=14,
    key="timeline_days"
)

# データ取得
try:
    rich_history = db_manager.get_data_arrival_rich(days=days)
    
    if rich_history:
        # Sparkline HTML生成
        footprint_html = build_footprint_html(rich_history, days=days)
        st.markdown(footprint_html, unsafe_allow_html=True)
    else:
        st.info("データがまだありません。データ取得を実行してください。")
        
except Exception as e:
    st.error(f"データ取得エラー: {e}")
    st.caption("データベース接続を確認してください。")

# Raw Data View（オプション）
with st.expander("🔍 Raw Data View", expanded=False):
    show_raw = st.checkbox("raw_data_lake の最新100件を表示", value=False)
    
    if show_raw:
        try:
            raw_data = db_manager.supabase.table("raw_data_lake").select("*").order("fetched_at", desc=True).limit(100).execute()
            if raw_data.data:
                st.dataframe(raw_data.data, use_container_width=True)
            else:
                st.info("raw_data_lake にデータがありません")
        except Exception as e:
            st.error(f"Raw Data取得エラー: {e}")
