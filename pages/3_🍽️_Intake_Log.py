"""
Intake Log - 摂取記録
サプリメント・食事の記録とトラッキング
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from ui_lib.session import get_database_manager
from components.responsive import inject_responsive_css
from src.utils.supplements_loader import (
    build_intake_snapshot,
    format_nutrient_label,
    get_scene_preset,
    load_supplements,
)

JST = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="Intake Log - YuruHealth",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

inject_responsive_css()

st.title("🍽️ 摂取ログ・トラッキング")
st.caption("サプリメント・食事の記録")

db_manager = get_database_manager()
user_id = "user_001"

supplements = load_supplements()
items_master = supplements.get("items", {})
presets = supplements.get("presets", {})

if not items_master:
    st.warning("config/supplements.yaml に items が未定義です。")
    st.stop()

# シーン選択
scene_options = list(presets.keys()) or ["Morning", "Noon", "Night", "Workout", "Anytime"]
selected_scene = st.selectbox("シーン", options=scene_options, index=0)
scene_preset = get_scene_preset(selected_scene, supplements)
default_items = set(scene_preset.get("default_items", []))

# 日時設定
now_jst = datetime.now(JST)
scene_time_presets = {
    "Morning": (7, 0),
    "Noon": (12, 0),
    "Night": (21, 0),
    "Workout": (18, 0),
}

if "intake_log_date" not in st.session_state:
    st.session_state["intake_log_date"] = now_jst.date()
if "intake_log_time" not in st.session_state:
    hh_mm = scene_time_presets.get(selected_scene)
    if hh_mm:
        st.session_state["intake_log_time"] = now_jst.replace(
            hour=hh_mm[0], minute=hh_mm[1], second=0, microsecond=0
        ).time()
    else:
        st.session_state["intake_log_time"] = now_jst.time().replace(second=0, microsecond=0)

prev_scene_key = "_intake_prev_scene"
if st.session_state.get(prev_scene_key) != selected_scene:
    hh_mm = scene_time_presets.get(selected_scene)
    if hh_mm:
        st.session_state["intake_log_time"] = now_jst.replace(
            hour=hh_mm[0], minute=hh_mm[1], second=0, microsecond=0
        ).time()
    st.session_state[prev_scene_key] = selected_scene

# 日付ショートカット
st.caption("後から入力しやすいように、日付ショートカットとシーン時刻プリセットを使えます。")
quick_today, quick_yesterday, quick_two_days, quick_scene_time = st.columns(4)
if quick_today.button("今日", key="intake_date_today"):
    st.session_state["intake_log_date"] = now_jst.date()
    st.rerun()
if quick_yesterday.button("昨日", key="intake_date_yesterday"):
    st.session_state["intake_log_date"] = (now_jst - timedelta(days=1)).date()
    st.rerun()
if quick_two_days.button("一昨日", key="intake_date_two_days"):
    st.session_state["intake_log_date"] = (now_jst - timedelta(days=2)).date()
    st.rerun()
if quick_scene_time.button("シーン時刻", key="intake_apply_scene_time"):
    hh_mm = scene_time_presets.get(selected_scene)
    if hh_mm:
        st.session_state["intake_log_time"] = now_jst.replace(
            hour=hh_mm[0], minute=hh_mm[1], second=0, microsecond=0
        ).time()
    else:
        st.session_state["intake_log_time"] = now_jst.time().replace(second=0, microsecond=0)
    st.rerun()

col_date, col_time = st.columns(2)
intake_date = col_date.date_input("摂取日", key="intake_log_date")
intake_time = col_time.time_input("摂取時刻", step=600, key="intake_log_time")
intake_timestamp = datetime.combine(intake_date, intake_time).replace(tzinfo=JST)

# 重複チェック
recent_logs = db_manager.get_intake_logs(user_id=user_id, hours=12, limit=20)
recent_same_scene = []
for row in recent_logs:
    if row.get("scene") != selected_scene:
        continue
    ts = row.get("timestamp")
    try:
        row_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if row_dt.tzinfo is None:
            row_dt = row_dt.replace(tzinfo=JST)
        row_dt = row_dt.astimezone(JST)
    except Exception:
        continue
    if abs((intake_timestamp - row_dt).total_seconds()) <= 30 * 60:
        recent_same_scene.append(row_dt)

if recent_same_scene:
    latest = max(recent_same_scene)
    st.warning(
        f"⚠️ 直近30分に同じシーン（{selected_scene}）の記録があります: {latest.strftime('%m/%d %H:%M')}"
    )

# アイテム選択
grouped_items = {"base": [], "optional": []}
for item_id, item in items_master.items():
    item_type = item.get("type", "optional")
    if item_type not in grouped_items:
        item_type = "optional"
    grouped_items[item_type].append((item_id, item))

selected_item_quantities = {}

for item_type, label in (("base", "🧱 ベース"), ("optional", "✨ オプション")):
    items = grouped_items.get(item_type, [])
    if not items:
        continue
    st.markdown(f"**{label}**")
    for item_id, item in items:
        item_name = item.get("name", item_id)
        unit_type = str(item.get("unit_type", "回") or "回")
        default_quantity = item.get("default_quantity", 1.0)
        try:
            default_quantity = max(0.0, float(default_quantity))
        except (TypeError, ValueError):
            default_quantity = 1.0
        checked = st.checkbox(
            item_name,
            value=item_id in default_items,
            key=f"intake_chk_{selected_scene}_{item_id}",
        )
        if checked:
            if unit_type in {"錠", "粒", "カプセル", "ソフトジェル"}:
                quantity = st.number_input(
                    f"{item_name} の数量（{unit_type}）",
                    min_value=0,
                    max_value=20,
                    value=int(round(default_quantity)),
                    step=1,
                    key=f"intake_qty_{selected_scene}_{item_id}",
                )
            else:
                quantity = st.number_input(
                    f"{item_name} の数量（{unit_type}）",
                    min_value=0.0,
                    max_value=20.0,
                    value=float(default_quantity),
                    step=0.5,
                    key=f"intake_qty_{selected_scene}_{item_id}",
                )
            selected_item_quantities[item_id] = float(quantity)

# スナップショット確認
snapshot_payload = build_intake_snapshot(items_master, selected_item_quantities)
if selected_item_quantities:
    with st.expander("🧪 スナップショット確認", expanded=False):
        total_nutrients = snapshot_payload.get("total_nutrients", {})
        nutrient_rows = [
            {"成分": format_nutrient_label(k), "摂取量": v}
            for k, v in total_nutrients.items()
        ]
        if nutrient_rows:
            st.dataframe(pd.DataFrame(nutrient_rows), use_container_width=True, hide_index=True)
        st.json(snapshot_payload)
else:
    st.info("記録するアイテムを1つ以上選択してください。")

# 記録ボタン
st.markdown(
    """
    <style>
    div[data-testid="stButton"] button[kind="primary"] {
        min-height: 56px;
        font-size: 1.05rem;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if st.button("✅ 記録する", type="primary", use_container_width=True, key="save_intake_log"):
    if not selected_item_quantities:
        st.error("保存するには最低1アイテムを選択してください。")
    else:
        db_manager.insert_intake_log(
            user_id=user_id,
            timestamp=intake_timestamp.isoformat(),
            scene=selected_scene,
            snapshot_payload=snapshot_payload,
        )
        st.success(
            f"保存しました: {selected_scene} / {intake_timestamp.strftime('%Y-%m-%d %H:%M')}"
        )
        st.rerun()

# タイムライン
st.markdown("#### 🕘 直近12時間タイムライン")
if recent_logs:
    for row in recent_logs:
        payload = row.get("snapshot_payload") or {}
        items = payload.get("items", []) if isinstance(payload, dict) else []
        total_nutrients = payload.get("total_nutrients", {}) if isinstance(payload, dict) else {}
        intake_log_id = row.get("id")
        ts = row.get("timestamp")
        ts_label = str(ts)
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
            ts_label = dt.astimezone(JST).strftime("%m/%d %H:%M")
        except Exception:
            pass

        row_col, action_col = st.columns([6, 2])
        with row_col:
            st.caption(
                f"{ts_label} / {row.get('scene', '-')} / アイテム{len(items)}件 / 成分{len(total_nutrients)}件"
            )
        with action_col:
            if intake_log_id and st.button("🗑️ 取消", key=f"intake_delete_{intake_log_id}"):
                st.session_state["pending_intake_delete_id"] = intake_log_id

        if intake_log_id and st.session_state.get("pending_intake_delete_id") == intake_log_id:
            confirm_col, cancel_col = st.columns([3, 2])
            with confirm_col:
                if st.button("この記録を削除", key=f"intake_confirm_delete_{intake_log_id}", type="primary"):
                    db_manager.delete_intake_log(intake_log_id=intake_log_id, user_id=user_id)
                    st.session_state.pop("pending_intake_delete_id", None)
                    st.success("記録を削除しました。")
                    st.rerun()
            with cancel_col:
                if st.button("キャンセル", key=f"intake_cancel_delete_{intake_log_id}"):
                    st.session_state.pop("pending_intake_delete_id", None)
                    st.rerun()
else:
    st.caption("直近12時間の摂取ログはまだありません。")
