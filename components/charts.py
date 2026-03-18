"""
Plotly chart components for YuruHealth
再利用可能なグラフコンポーネント
"""
import plotly.graph_objects as go
import pandas as pd
from typing import Optional


def create_sleep_score_chart(df: pd.DataFrame) -> go.Figure:
    """
    睡眠スコア推移グラフを作成
    
    Args:
        df: measured_at, sleep_score, activity_score, readiness_score を含むDataFrame
    
    Returns:
        Plotly Figure
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df["measured_at"],
        y=df["sleep_score"],
        name="睡眠スコア",
        mode="lines+markers",
        line=dict(color="#2E7D9A", width=3),
        marker=dict(size=9, color="#2E7D9A"),
        hovertemplate="%{x|%m/%d}<br>睡眠スコア: %{y:.0f}点<extra></extra>",
    ))
    
    fig.add_trace(go.Scatter(
        x=df["measured_at"],
        y=df["activity_score"],
        name="活動スコア",
        mode="lines+markers",
        line=dict(color="#4DB6AC", width=2.5),
        marker=dict(size=8, color="#4DB6AC"),
        hovertemplate="%{x|%m/%d}<br>活動スコア: %{y:.0f}点<extra></extra>",
    ))
    
    fig.add_trace(go.Scatter(
        x=df["measured_at"],
        y=df["readiness_score"],
        name="レディネス",
        mode="lines+markers",
        line=dict(color="#80CBC4", width=2.5),
        marker=dict(size=8, color="#80CBC4"),
        hovertemplate="%{x|%m/%d}<br>レディネス: %{y:.0f}点<extra></extra>",
    ))
    
    fig.add_hline(
        y=80,
        line_width=1.5,
        line_dash="dash",
        line_color="#26A69A",
        annotation_text="目標ライン: 80点",
        annotation_position="top left",
    )
    
    fig.update_layout(
        height=340,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        yaxis=dict(title="スコア", range=[50, 100]),
        xaxis=dict(title=""),
        hovermode="x unified",
        hoverlabel=dict(font_size=14),
    )
    
    return fig


def create_weight_chart(df: pd.DataFrame, target_weight_kg: float = 60.0) -> go.Figure:
    """
    体重推移グラフを作成
    
    Args:
        df: measured_at, weight_kg を含むDataFrame
        target_weight_kg: 目標体重
    
    Returns:
        Plotly Figure
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df["measured_at"],
        y=df["weight_kg"],
        name="体重",
        mode="lines+markers",
        line=dict(color="#5DADE2", width=3),
        marker=dict(size=9, color="#90CAF9"),
        hovertemplate="%{x|%m/%d}<br>体重: %{y:.1f}kg<extra></extra>",
    ))
    
    fig.add_hline(
        y=target_weight_kg,
        line_width=1.5,
        line_dash="dash",
        line_color="#90A4AE",
        annotation_text=f"目標体重: {target_weight_kg:.1f}kg",
        annotation_position="top left",
    )
    
    fig.update_layout(
        height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        yaxis=dict(title="体重 (kg)"),
        xaxis=dict(title=""),
        hovermode="x unified",
        hoverlabel=dict(font_size=14),
    )
    
    return fig


def create_co2_sleep_correlation_chart(df: pd.DataFrame) -> go.Figure:
    """
    CO2と睡眠スコアの相関グラフを作成
    
    Args:
        df: date, sleep_score, co2_avg を含むDataFrame
    
    Returns:
        Plotly Figure
    """
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df["date"],
        y=df["sleep_score"],
        name="睡眠スコア",
        marker_color="rgba(79,195,247,0.72)",
        yaxis="y",
        hovertemplate="%{x}<br>睡眠スコア: %{y:.0f}点<extra></extra>",
    ))
    
    if df["co2_avg"].notna().any():
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["co2_avg"],
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
    
    return fig


def create_temp_humidity_chart(df: pd.DataFrame) -> go.Figure:
    """
    室温・湿度推移グラフを作成
    
    Args:
        df: date, temp_avg, humidity_avg を含むDataFrame
    
    Returns:
        Plotly Figure
    """
    fig = go.Figure()
    
    has_temp = df["temp_avg"].notna().any()
    has_hum = df["humidity_avg"].notna().any()
    
    if has_temp:
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["temp_avg"],
            name="室温 (℃)",
            mode="lines+markers",
            line=dict(color="#F57C00", width=3),
            marker=dict(size=9, color="#FB8C00"),
            hovertemplate="%{x}<br>室温: %{y:.1f}℃<extra></extra>",
        ))
        
        fig.add_hline(
            y=28,
            line_width=1.5,
            line_dash="dash",
            line_color="#E53935",
            annotation_text="高温注意ライン: 28℃",
            annotation_position="top left",
        )
    
    if has_hum:
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["humidity_avg"],
            name="湿度 (%)",
            mode="lines+markers",
            line=dict(color="#90A4AE", width=2.5),
            marker=dict(size=8, color="#B0BEC5"),
            yaxis="y2",
            hovertemplate="%{x}<br>湿度: %{y:.1f}%<extra></extra>",
        ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        yaxis=dict(title="室温 (℃)", side="left"),
        yaxis2=dict(title="湿度 (%)", overlaying="y", side="right", showgrid=False),
        hovermode="x unified",
        hoverlabel=dict(font_size=14),
    )
    
    return fig


def create_system_health_temp_chart(df: pd.DataFrame, cfg: dict) -> go.Figure:
    """
    システムヘルス（CPU温度）グラフを作成
    
    Args:
        df: measured_at, cpu_temp_c を含むDataFrame
        cfg: 警告・危険閾値を含む設定辞書
    
    Returns:
        Plotly Figure
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df["measured_at"],
        y=df["cpu_temp_c"],
        name="CPU温度",
        mode="lines",
        line=dict(color="#ef4444", width=2.5),
        hovertemplate="%{x|%m/%d %H:%M}<br>CPU温度: %{y:.1f}°C<extra></extra>",
    ))
    
    fig.add_hline(
        y=cfg.get("temp_warn_c", 60.0),
        line_width=1,
        line_dash="dash",
        line_color="#d97706",
        annotation_text=f"警告 {cfg.get('temp_warn_c', 60.0):.0f}°C",
        annotation_position="top left",
    )
    
    fig.add_hline(
        y=cfg.get("temp_critical_c", 70.0),
        line_width=1,
        line_dash="dash",
        line_color="#dc2626",
        annotation_text=f"危険 {cfg.get('temp_critical_c', 70.0):.0f}°C",
        annotation_position="top left",
    )
    
    fig.update_layout(
        height=280,
        margin=dict(l=0, r=0, t=20, b=0),
        xaxis=dict(title=""),
        yaxis=dict(title="温度 (°C)"),
        hovermode="x unified",
    )
    
    return fig


def create_system_health_usage_chart(df: pd.DataFrame) -> go.Figure:
    """
    システムヘルス（CPU/メモリ/ディスク使用率）グラフを作成
    
    Args:
        df: measured_at, cpu_percent, memory_percent, disk_percent を含むDataFrame
    
    Returns:
        Plotly Figure
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df["measured_at"],
        y=df["cpu_percent"],
        name="CPU",
        mode="lines",
        line=dict(color="#2563eb", width=2.2),
    ))
    
    fig.add_trace(go.Scatter(
        x=df["measured_at"],
        y=df["memory_percent"],
        name="Memory",
        mode="lines",
        line=dict(color="#0891b2", width=2.2),
    ))
    
    fig.add_trace(go.Scatter(
        x=df["measured_at"],
        y=df["disk_percent"],
        name="Disk",
        mode="lines",
        line=dict(color="#4f46e5", width=2.2),
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(title=""),
        yaxis=dict(title="使用率 (%)", range=[0, 100]),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )
    
    return fig
