"""
Sparkline (SVG ミニ折れ線グラフ) と Badge (サマリーバッジ) の生成ユーティリティ。
Streamlit の st.markdown(html, unsafe_allow_html=True) で描画する。
"""
from typing import Dict, Any, List, Optional


def _svg_sparkline(values: List[float], width: int = 60, height: int = 28,
                   color: str = "#4CAF50", bg_color: str = "rgba(76,175,80,0.08)") -> str:
    """数値リストから SVG ミニ折れ線グラフを生成"""
    if not values or len(values) < 2:
        return ""
    vmin = min(values)
    vmax = max(values)
    vrange = vmax - vmin if vmax != vmin else 1
    padding = 2

    points = []
    for i, v in enumerate(values):
        x = padding + (width - 2 * padding) * i / (len(values) - 1)
        y = padding + (height - 2 * padding) * (1 - (v - vmin) / vrange)
        points.append(f"{x:.1f},{y:.1f}")

    polyline = " ".join(points)
    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{width}" height="{height}" rx="4" fill="{bg_color}"/>'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


def render_sparkline_cell(rich_data: Optional[Dict[str, Any]], source: str) -> str:
    """SwitchBot / Weather 用: 時系列データからスパークライン HTML を生成"""
    if not rich_data or not rich_data.get("has_data"):
        return _empty_cell()

    ts = rich_data.get("timeseries", [])
    summary = rich_data.get("summary", {})

    if source == "switchbot":
        temps = [p["temp"] for p in ts if p.get("temp") is not None]
        color = "#FF7043"
        bg = "rgba(255,112,67,0.08)"
        label = f'{summary.get("temp_avg", "--")}°' if summary.get("temp_avg") else ""
    elif source == "weather":
        temps = [p["temp"] for p in ts if p.get("temp") is not None]
        color = "#42A5F5"
        bg = "rgba(66,165,245,0.08)"
        label = f'{summary.get("temp_avg", "--")}°' if summary.get("temp_avg") else ""
    else:
        return _empty_cell()

    if not temps:
        return _has_data_dot()

    svg = _svg_sparkline(temps, color=color, bg_color=bg)
    return (
        f'<div style="text-align:center;line-height:1.1">'
        f'{svg}'
        f'<div style="font-size:9px;color:#888;margin-top:1px">{label}</div>'
        f'</div>'
    )


def render_badge_cell(rich_data: Optional[Dict[str, Any]], source: str) -> str:
    """Oura / Withings / Google Fit 用: サマリーバッジ HTML を生成"""
    if not rich_data or not rich_data.get("has_data"):
        return _empty_cell()

    badge = rich_data.get("badge", {})
    if not badge:
        return _has_data_dot()

    if source == "oura":
        return _oura_badge(badge)
    elif source == "withings":
        return _withings_badge(badge)
    elif source == "google_fit":
        return _google_fit_badge(badge)
    return _has_data_dot()


def _oura_badge(badge: dict) -> str:
    parts = []
    s = badge.get("sleep_score")
    a = badge.get("activity_score")
    r = badge.get("readiness_score")
    if s is not None:
        parts.append(f'<span style="background:#7E57C2;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600" title="Sleep">😴{s}</span>')
    if a is not None:
        parts.append(f'<span style="background:#66BB6A;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600" title="Activity">🏃{a}</span>')
    if r is not None:
        parts.append(f'<span style="background:#42A5F5;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600" title="Readiness">💪{r}</span>')
    if not parts:
        return _has_data_dot()
    return f'<div style="text-align:center;line-height:1.6;display:flex;flex-direction:column;align-items:center;gap:1px">{"".join(parts)}</div>'


def _withings_badge(badge: dict) -> str:
    w = badge.get("weight_kg")
    if w is None:
        return _has_data_dot()
    return (
        f'<div style="text-align:center">'
        f'<span style="background:#26A69A;color:#fff;border-radius:8px;padding:2px 6px;font-size:11px;font-weight:600">'
        f'⚖️{w}kg</span></div>'
    )


def _google_fit_badge(badge: dict) -> str:
    parts = []
    steps = badge.get("steps")
    w = badge.get("weight_kg")
    slp = badge.get("sleep_min")
    if steps is not None:
        parts.append(f'<span style="background:#FF7043;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600">🚶{steps:,}</span>')
    if w is not None:
        parts.append(f'<span style="background:#26A69A;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600">⚖️{w}</span>')
    if slp is not None:
        hrs = slp // 60
        mins = slp % 60
        parts.append(f'<span style="background:#7E57C2;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600">😴{hrs}h{mins:02d}</span>')
    if not parts:
        return _has_data_dot()
    return f'<div style="text-align:center;line-height:1.6;display:flex;flex-direction:column;align-items:center;gap:1px">{"".join(parts)}</div>'


def _empty_cell() -> str:
    return '<div style="text-align:center;color:#ddd;font-size:16px">⚪</div>'


def _has_data_dot() -> str:
    return '<div style="text-align:center;font-size:16px">🟢</div>'
