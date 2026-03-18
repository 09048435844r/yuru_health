"""
Metrics display components for YuruHealth
メトリクス表示コンポーネント
"""
import streamlit as st
from typing import Optional, Any


def display_health_metrics(latest_oura: Optional[dict]):
    """
    健康メトリクス（レディネス、活動、歩数）を3カラムで表示
    
    Args:
        latest_oura: Ouraデータの最新レコード
    """
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


def display_system_health_metrics(df, cfg: dict):
    """
    システムヘルスメトリクス（温度、CPU、メモリ、ディスク）を4カラムで表示
    
    Args:
        df: システムヘルスデータのDataFrame
        cfg: UI設定（警告閾値など）
    """
    import pandas as pd
    
    peak_temp = df["cpu_temp_c"].max(skipna=True)
    avg_cpu = df["cpu_percent"].mean(skipna=True)
    avg_memory = df["memory_percent"].mean(skipna=True)
    avg_disk = df["disk_percent"].mean(skipna=True)
    
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


def display_weight_metric(latest_weight: Optional[dict]):
    """
    体重メトリクスを表示
    
    Args:
        latest_weight: 体重データの最新レコード
    """
    if latest_weight and latest_weight.get("weight_kg") is not None:
        st.metric("⚖️ 体重", f"{latest_weight.get('weight_kg'):.1f}kg")
    else:
        st.metric("⚖️ 体重", "ー")
