"""
Sparkline (SVG ミニ折れ線グラフ) と Badge (サマリーバッジ) の生成ユーティリティ。
Streamlit の st.markdown(html, unsafe_allow_html=True) で描画する。
"""
import datetime as _dt
from typing import Dict, Any, List, Optional, Tuple


# ────────────────────────────────────────────
# CSS (横スクロール + Sticky ソース名 + モバイル最適化)
# ────────────────────────────────────────────
FOOTPRINT_CSS = """
<style>
.fp-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -1rem;padding:0 1rem}
.fp-table{border-collapse:separate;border-spacing:0;width:max-content;min-width:100%}
.fp-table th,.fp-table td{padding:4px 2px;vertical-align:middle;text-align:center}
.fp-table th.fp-src,.fp-table td.fp-src{
  position:sticky;left:0;z-index:2;
  background:var(--background-color,#fff);
  min-width:76px;max-width:76px;
  text-align:left;font-size:11px;font-weight:600;color:#555;
  white-space:nowrap;padding-left:4px;
}
.fp-table td.fp-date{min-width:68px;max-width:80px}
.fp-table th.fp-date-hdr{min-width:68px;max-width:80px;font-size:10px;color:#999;font-weight:400}
@media(max-width:768px){
  .fp-table th.fp-src,.fp-table td.fp-src{min-width:62px;max-width:62px;font-size:10px}
  .fp-table td.fp-date{min-width:58px}
  .fp-table th.fp-date-hdr{min-width:58px;font-size:9px}
  .fp-badge{font-size:9px!important;padding:1px 3px!important}
  .fp-label{font-size:8px!important}
}
</style>
"""


# ────────────────────────────────────────────
# SVG Sparkline
# ────────────────────────────────────────────
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
        f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


# ────────────────────────────────────────────
# Cell renderers (return inner HTML for <td>)
# ────────────────────────────────────────────
def render_sparkline_cell(rich_data: Optional[Dict[str, Any]], source: str) -> str:
    """SwitchBot / Weather 用: 時系列データからスパークライン HTML を生成"""
    if not rich_data or not rich_data.get("has_data"):
        return _empty_cell()

    ts = rich_data.get("timeseries", [])
    summary = rich_data.get("summary", {})

    if source == "switchbot":
        temps = [p["co2"] for p in ts if p.get("co2") is not None]
        color = "#66BB6A"
        bg = "rgba(102,187,106,0.10)"
        label = f'{summary.get("co2_avg", "--")}ppm' if summary.get("co2_avg") is not None else ""
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
        f'<div class="fp-label" style="font-size:9px;color:#888;margin-top:1px">{label}</div>'
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
        parts.append(f'<span class="fp-badge" style="background:#7E57C2;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600" title="Sleep">😴{s}</span>')
    if a is not None:
        parts.append(f'<span class="fp-badge" style="background:#66BB6A;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600" title="Activity">🏃{a}</span>')
    if r is not None:
        parts.append(f'<span class="fp-badge" style="background:#42A5F5;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600" title="Readiness">💪{r}</span>')
    if not parts:
        return _has_data_dot()
    return f'<div style="display:flex;flex-direction:column;align-items:center;gap:1px">{"".join(parts)}</div>'


def _withings_badge(badge: dict) -> str:
    w = badge.get("weight_kg")
    if w is None:
        return _has_data_dot()
    return (
        f'<span class="fp-badge" style="background:#26A69A;color:#fff;border-radius:8px;'
        f'padding:2px 6px;font-size:11px;font-weight:600">⚖️{w}kg</span>'
    )


def _google_fit_badge(badge: dict) -> str:
    parts = []
    steps = badge.get("steps")
    w = badge.get("weight_kg")
    slp = badge.get("sleep_min")
    if steps is not None:
        parts.append(f'<span class="fp-badge" style="background:#FF7043;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600">🚶{steps:,}</span>')
    if w is not None:
        parts.append(f'<span class="fp-badge" style="background:#26A69A;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600">⚖️{w}</span>')
    if slp is not None:
        hrs = slp // 60
        mins = slp % 60
        parts.append(f'<span class="fp-badge" style="background:#7E57C2;color:#fff;border-radius:8px;padding:1px 5px;font-size:10px;font-weight:600">😴{hrs}:{mins:02d}</span>')
    if not parts:
        return _has_data_dot()
    return f'<div style="display:flex;flex-direction:column;align-items:center;gap:1px">{"".join(parts)}</div>'


def _empty_cell() -> str:
    return '<span style="color:#ddd;font-size:16px">⚪</span>'


def _has_data_dot() -> str:
    return '<span style="font-size:16px">🟢</span>'


# ────────────────────────────────────────────
# Full HTML table builder
# ────────────────────────────────────────────
_SPARKLINE_SOURCES = {"switchbot", "weather"}

_SOURCE_LABELS = {
    "oura": "Oura Ring",
    "withings": "Withings",
    "google_fit": "Google Fit",
    "weather": "Weather",
    "switchbot": "SwitchBot",
}


def build_footprint_html(
    rich_history: Dict[tuple, Dict[str, Any]],
    days: int = 14,
) -> Tuple[str, int, int]:
    """記録の足跡を横スクロール対応 HTML テーブルとして構築する。

    Returns:
        (html_string, total_cells, filled_cells)
    """
    _JST = _dt.timezone(_dt.timedelta(hours=9))
    today = _dt.datetime.now(_JST).date()
    date_range = [(today - _dt.timedelta(days=i)) for i in range(days - 1, -1, -1)]

    total_cells = 0
    filled_cells = 0

    # ── ヘッダー行 ──
    hdr = '<tr><th class="fp-src"></th>'
    for d in date_range:
        hdr += f'<th class="fp-date-hdr">{d.strftime("%m/%d")}</th>'
    hdr += '</tr>'

    # ── データ行 ──
    rows_html = ""
    for src_key, src_label in _SOURCE_LABELS.items():
        row = f'<tr><td class="fp-src">{src_label}</td>'
        for d in date_range:
            date_str = d.strftime("%Y-%m-%d")
            total_cells += 1
            cell_data = rich_history.get((src_key, date_str))
            has_data = cell_data is not None and cell_data.get("has_data")
            if has_data:
                filled_cells += 1

            if src_key in _SPARKLINE_SOURCES:
                inner = render_sparkline_cell(cell_data, src_key)
            else:
                inner = render_badge_cell(cell_data, src_key)
            row += f'<td class="fp-date">{inner}</td>'
        row += '</tr>'
        rows_html += row

    table_html = (
        f'{FOOTPRINT_CSS}'
        f'<div class="fp-wrap">'
        f'<table class="fp-table"><thead>{hdr}</thead>'
        f'<tbody>{rows_html}</tbody></table>'
        f'</div>'
    )
    return table_html, total_cells, filled_cells
