"""
Server Health - システムヘルス監視
Raspberry Piのリソース使用状況を可視化
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from ui_lib.session import get_database_manager
from components.responsive import inject_responsive_css
from components.charts import create_system_health_temp_chart, create_system_health_usage_chart
from components.metrics import display_system_health_metrics
from src.utils.system_health_store import ensure_system_health_sample, fetch_system_health_history
from src.utils.config_loader import load_settings

JST = timezone(timedelta(hours=9))
SYSTEM_HEALTH_SAMPLE_INTERVAL_SECONDS = 300

st.set_page_config(
    page_title="Server Health - YuruHealth",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

inject_responsive_css()

st.title("🖥️ サーバー・ヘルス")
st.caption("保存先: data/system_health.db（SQLite, Supabaseとは完全分離）")

db_manager = get_database_manager()


@st.cache_data(ttl=SYSTEM_HEALTH_SAMPLE_INTERVAL_SECONDS, show_spinner=False)
def collect_system_health_sample():
    """5分間隔でシステムメトリクスを SQLite に保存する"""
    return ensure_system_health_sample(
        sample_interval_seconds=SYSTEM_HEALTH_SAMPLE_INTERVAL_SECONDS,
        retention_days=30,
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_system_health_history(hours: int):
    since_utc = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))
    return fetch_system_health_history(since_utc=since_utc)


def system_health_records_to_df(records):
    if not records:
        return pd.DataFrame(columns=["measured_at", "cpu_temp_c", "cpu_percent", "memory_percent", "disk_percent"])
    df = pd.DataFrame(records)
    if "measured_at" in df.columns:
        df["measured_at"] = pd.to_datetime(df["measured_at"], errors="coerce")
    return df.dropna(subset=["measured_at"]).sort_values("measured_at")


def downsample_df(df: pd.DataFrame, max_points: int):
    if len(df) <= max_points:
        return df
    step = max(1, (len(df) + max_points - 1) // max_points)
    return df.iloc[::step].copy()


def get_system_health_ui_config():
    defaults = {
        "temp_warn_c": 60.0,
        "temp_critical_c": 70.0,
        "cpu_warn_percent": 70.0,
        "cpu_critical_percent": 90.0,
        "memory_warn_percent": 70.0,
        "memory_critical_percent": 90.0,
        "disk_warn_percent": 70.0,
        "disk_critical_percent": 90.0,
    }
    try:
        settings = load_settings()
        ui_cfg = ((settings.get("system_health") or {}).get("ui") or {}) if isinstance(settings, dict) else {}
        for key in defaults:
            if key in ui_cfg:
                defaults[key] = float(ui_cfg[key])
    except Exception:
        pass
    return defaults


# 表示期間選択
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

# 最新サンプルを確保
collect_system_health_sample()

# データ取得
records = load_system_health_history(period_map[selected_period])
df_health = system_health_records_to_df(records)

if df_health.empty:
    st.info("システムヘルスデータがまだありません。数分後に再表示してください。")
else:
    max_points = 720 if selected_period == "1ヶ月" else 2000
    df_plot = downsample_df(df_health, max_points=max_points)
    cfg = get_system_health_ui_config()
    
    # メトリクス表示
    display_system_health_metrics(df_health, cfg)
    
    # CPU温度グラフ
    fig_temp = create_system_health_temp_chart(df_plot, cfg)
    st.plotly_chart(fig_temp, use_container_width=True)
    
    # CPU/メモリ/ディスク使用率グラフ
    fig_usage = create_system_health_usage_chart(df_plot)
    st.plotly_chart(fig_usage, use_container_width=True)
    
    if len(df_plot) < len(df_health):
        st.caption(f"1ヶ月表示の見やすさのため、{len(df_health)}点 → {len(df_plot)}点に間引いて表示しています。")
    else:
        st.caption(f"表示ポイント数: {len(df_plot)}")
