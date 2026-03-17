"""
YuruHealth 自動データ取得エントリーポイント
GitHub Actions (cron) やローカルから実行可能。

Usage:
    python -m src.main --auto
"""
import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

JST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

USER_ID = "user_001"
DEFAULT_BOOTSTRAP_DAYS = 30
DEFAULT_AWAKE_KEYWORDS = ("awake", "wake", "覚醒")
SLEEP_SOURCE_ALIAS = {
    "oura": "com.ouraring.oura",
    "shealth": "com.sec.android.app.shealth",
    "healthsync": "nl.appyhapps.healthsync",
}


def _run_fetcher(name: str, func: Callable[[], object]) -> object:
    """Fetcher を実行し、失敗時はログを残して次のサービスへ進む。"""
    try:
        result = func()
        return result
    except Exception as e:
        logger.exception(f"{name}: error — {type(e).__name__}: {e}")
        return None


def _parse_latest_date(value: Optional[str]) -> Optional[datetime.date]:
    """DB から取得した日時文字列を date に正規化する。"""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass

    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _find_gap_start_date(
    existing_dates: Set[str],
    window_start: datetime.date,
    window_end: datetime.date,
) -> datetime.date:
    """window 内で最初に欠損している日付を返す（欠損がなければ window_end）。"""
    day = window_start
    while day <= window_end:
        if day.strftime("%Y-%m-%d") not in existing_dates:
            return day
        day += timedelta(days=1)
    return window_end


def _split_interval_by_day(start_dt: datetime, end_dt: datetime) -> List[Tuple[str, datetime, datetime]]:
    segments: List[Tuple[str, datetime, datetime]] = []
    if end_dt <= start_dt:
        return segments

    day = start_dt.date()
    last_day = end_dt.date()
    while day <= last_day:
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=JST)
        day_end = day_start + timedelta(days=1)
        seg_start = max(start_dt, day_start)
        seg_end = min(end_dt, day_end)
        if seg_end > seg_start:
            segments.append((day.strftime("%Y-%m-%d"), seg_start, seg_end))
        day += timedelta(days=1)

    return segments


def _merge_intervals(intervals: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda x: x[0])
    merged: List[Tuple[datetime, datetime]] = [(ordered[0][0], ordered[0][1])]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _subtract_intervals(
    base: List[Tuple[datetime, datetime]],
    subtract: List[Tuple[datetime, datetime]],
) -> List[Tuple[datetime, datetime]]:
    if not base:
        return []
    if not subtract:
        return base

    result: List[Tuple[datetime, datetime]] = []
    cuts = _merge_intervals(subtract)
    for b_start, b_end in base:
        fragments = [(b_start, b_end)]
        for s_start, s_end in cuts:
            next_fragments: List[Tuple[datetime, datetime]] = []
            for f_start, f_end in fragments:
                if s_end <= f_start or s_start >= f_end:
                    next_fragments.append((f_start, f_end))
                    continue
                if s_start > f_start:
                    next_fragments.append((f_start, s_start))
                if s_end < f_end:
                    next_fragments.append((s_end, f_end))
            fragments = next_fragments
            if not fragments:
                break
        result.extend(fragments)
    return result


def _interval_minutes(intervals: List[Tuple[datetime, datetime]]) -> int:
    return int(sum((end - start).total_seconds() for start, end in intervals) / 60)


def _is_awake_session(session: Dict[str, Any]) -> bool:
    return _is_awake_session_with_keywords(session, DEFAULT_AWAKE_KEYWORDS)


def _is_awake_session_with_keywords(session: Dict[str, Any], keywords: List[str]) -> bool:
    text = " ".join(
        [
            str(session.get("name") or ""),
            str(session.get("description") or ""),
            str(session.get("id") or ""),
        ]
    ).lower()
    normalized = [str(k).strip().lower() for k in keywords if str(k).strip()]
    return any(keyword in text for keyword in normalized)


def _session_app_key(session: Dict[str, Any]) -> str:
    app = session.get("application") or {}
    if isinstance(app, dict):
        return str(app.get("packageName") or app.get("name") or "unknown")
    return "unknown"


def _load_google_fit_sleep_parser_settings() -> Dict[str, Any]:
    try:
        from src.utils.config_loader import load_settings

        settings = load_settings()
    except Exception as e:
        logger.info("Failed to load parser settings; fallback defaults: %s", e)
        settings = {}

    gfit = settings.get("google_fit", {}) if isinstance(settings, dict) else {}
    parser_cfg = gfit.get("sleep_parser", {}) if isinstance(gfit, dict) else {}

    policy = str(parser_cfg.get("source_policy") or "min").strip().lower()
    min_candidate_minutes = parser_cfg.get("min_candidate_minutes", 120)
    try:
        min_candidate_minutes = max(0, int(min_candidate_minutes))
    except (TypeError, ValueError):
        min_candidate_minutes = 120

    raw_keywords = parser_cfg.get("awake_keywords")
    if isinstance(raw_keywords, list):
        awake_keywords = [str(v).strip().lower() for v in raw_keywords if str(v).strip()]
    else:
        awake_keywords = list(DEFAULT_AWAKE_KEYWORDS)

    return {
        "source_policy": policy,
        "min_candidate_minutes": min_candidate_minutes,
        "awake_keywords": awake_keywords or list(DEFAULT_AWAKE_KEYWORDS),
    }


def _select_sleep_source(
    app_minutes: Dict[str, int],
    source_policy: str,
    min_candidate_minutes: int,
) -> Tuple[Optional[str], int]:
    if not app_minutes:
        return None, 0

    positive_candidates = {k: v for k, v in app_minutes.items() if v >= min_candidate_minutes}
    candidates = positive_candidates or app_minutes

    if source_policy in SLEEP_SOURCE_ALIAS:
        preferred = SLEEP_SOURCE_ALIAS[source_policy]
        if preferred in candidates:
            return preferred, candidates[preferred]

    if source_policy.startswith("prefer:"):
        preferred = source_policy.split(":", 1)[1].strip()
        preferred = SLEEP_SOURCE_ALIAS.get(preferred, preferred)
        if preferred in candidates:
            return preferred, candidates[preferred]

    if source_policy == "max":
        chosen_app, minutes = max(candidates.items(), key=lambda kv: kv[1])
        return chosen_app, minutes

    # default: min
    chosen_app, minutes = min(candidates.items(), key=lambda kv: kv[1])
    return chosen_app, minutes


def _resolve_start_date(
    latest_value: Optional[str],
    existing_dates: Set[str],
    end_dt: datetime,
    lookback_days: int = DEFAULT_BOOTSTRAP_DAYS,
) -> str:
    """最新日付と欠損日を考慮して開始日を解決する。"""
    end_date = end_dt.date()
    window_start = (end_dt - timedelta(days=max(0, lookback_days))).date()

    gap_start = _find_gap_start_date(existing_dates, window_start, end_date)

    latest_date = _parse_latest_date(latest_value)
    if latest_date:
        latest_plus_one = latest_date + timedelta(days=1)
        if latest_plus_one > end_date:
            latest_plus_one = end_date
        start_date = min(gap_start, latest_plus_one)
    else:
        start_date = gap_start

    return start_date.strftime("%Y-%m-%d")


def _extract_date_string(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    return text[:10]


def _in_window(date_text: Optional[str], start_date: datetime.date, end_date: datetime.date) -> bool:
    extracted = _extract_date_string(date_text)
    if not extracted:
        return False
    try:
        target = datetime.strptime(extracted, "%Y-%m-%d").date()
    except ValueError:
        return False
    return start_date <= target <= end_date


def _to_jst_iso(value: Optional[str], fallback: datetime) -> str:
    if value:
        text = str(value).strip()
        if text:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(JST).isoformat()
            except ValueError:
                pass
    return fallback.astimezone(JST).isoformat()


def _payload_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _epoch_to_jst_datetime(value: Any) -> Optional[datetime]:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None

    abs_raw = abs(raw)
    if abs_raw >= 1e18:  # nanos
        seconds = raw / 1e9
    elif abs_raw >= 1e15:  # micros
        seconds = raw / 1e6
    elif abs_raw >= 1e12:  # millis
        seconds = raw / 1e3
    else:  # seconds
        seconds = raw

    try:
        return datetime.fromtimestamp(seconds, tz=JST)
    except (OSError, ValueError):
        return None


def _accumulate_sleep_minutes_by_day(
    totals: Dict[str, int],
    start_dt: datetime,
    end_dt: datetime,
    window_start: datetime.date,
    window_end: datetime.date,
) -> None:
    """睡眠セッションを JST 日次窓(00:00-24:00)に分割して分単位で加算する。"""
    if end_dt <= start_dt:
        return

    day = start_dt.date()
    last_day = end_dt.date()
    while day <= last_day:
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=JST)
        day_end = day_start + timedelta(days=1)

        overlap_start = max(start_dt, day_start)
        overlap_end = min(end_dt, day_end)
        if overlap_end > overlap_start and window_start <= day <= window_end:
            minutes = int((overlap_end - overlap_start).total_seconds() / 60)
            if minutes > 0:
                day_text = day.strftime("%Y-%m-%d")
                totals[day_text] = totals.get(day_text, 0) + minutes

        day += timedelta(days=1)


def _load_raw_rows(
    db_manager,
    *,
    user_id: str,
    source: str,
    start_iso: str,
    end_iso: str,
    category: Optional[str] = None,
    page_size: int = 1000,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        query = (
            db_manager.supabase.table("raw_data_lake")
            .select("fetched_at, recorded_at, source, category, payload")
            .eq("user_id", user_id)
            .eq("source", source)
            .gte("recorded_at", start_iso)
            .lte("recorded_at", end_iso)
            .order("recorded_at")
        )
        if category is not None:
            query = query.eq("category", category)

        batch = query.range(offset, offset + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    return rows


def _clear_parsed_tables_in_window(db_manager, start_date: datetime.date, end_date: datetime.date) -> None:
    start_day = start_date.strftime("%Y-%m-%d")
    end_day = end_date.strftime("%Y-%m-%d")
    start_measured = f"{start_day} 00:00:00"
    end_measured = f"{end_day} 23:59:59"
    start_iso = datetime.combine(start_date, datetime.min.time(), tzinfo=JST).isoformat()
    end_iso = datetime.combine(end_date, datetime.max.time(), tzinfo=JST).isoformat()

    db_manager.supabase.table("weight_data").delete().eq("user_id", USER_ID).gte("measured_at", start_measured).lte("measured_at", end_measured).execute()
    db_manager.supabase.table("oura_data").delete().eq("user_id", USER_ID).gte("measured_at", start_measured).lte("measured_at", end_measured).execute()
    db_manager.supabase.table("google_fit_data").delete().eq("user_id", USER_ID).gte("date", start_day).lte("date", f"{end_day}T23:59:59").execute()
    db_manager.supabase.table("environmental_logs").delete().gte("timestamp", start_iso).lte("timestamp", end_iso).execute()


def run_all_parsers(days: Optional[int] = None):
    """raw_data_lake の既存データのみを使って再パースし、各データテーブルを再構築する。"""
    from src.database_manager import DatabaseManager, _extract_switchbot_value

    db_manager = DatabaseManager()
    sleep_parser_cfg = _load_google_fit_sleep_parser_settings()
    end_dt = datetime.now(JST)
    lookback_days = days if days is not None else DEFAULT_BOOTSTRAP_DAYS
    start_dt = end_dt - timedelta(days=max(0, lookback_days))
    start_date = start_dt.date()
    end_date = end_dt.date()
    start_iso = datetime.combine(start_date, datetime.min.time(), tzinfo=JST).isoformat()
    end_iso = datetime.combine(end_date, datetime.max.time(), tzinfo=JST).isoformat()

    logger.info("parse-only mode | window(days=%s) %s..%s", lookback_days, start_date, end_date)

    _clear_parsed_tables_in_window(db_manager, start_date, end_date)

    results: Dict[str, int] = {
        "Oura": 0,
        "Withings": 0,
        "GoogleFit": 0,
        "Weather": 0,
        "SwitchBot": 0,
    }

    # ── Oura ──
    oura_rows = _load_raw_rows(db_manager, user_id=USER_ID, source="oura", start_iso=start_iso, end_iso=end_iso)
    oura_latest_by_day: Dict[str, Dict[str, Dict[str, Any]]] = {
        "activity": {},
        "sleep": {},
        "readiness": {},
    }
    for row in oura_rows:
        category = str(row.get("category") or "")
        payload = row.get("payload")
        if category not in oura_latest_by_day or not isinstance(payload, dict):
            continue
        day = str(payload.get("day") or "")
        if not _in_window(day, start_date, end_date):
            continue
        prev = oura_latest_by_day[category].get(day)
        if prev is None or str(row.get("fetched_at") or "") >= str(prev.get("fetched_at") or ""):
            oura_latest_by_day[category][day] = {"fetched_at": row.get("fetched_at"), "payload": payload}

    activity_resp = {"data": [v["payload"] for v in oura_latest_by_day["activity"].values()]}
    sleep_resp = {"data": [v["payload"] for v in oura_latest_by_day["sleep"].values()]}
    readiness_resp = {"data": [v["payload"] for v in oura_latest_by_day["readiness"].values()]}
    if activity_resp["data"] or sleep_resp["data"] or readiness_resp["data"]:
        from src.fetchers.oura_fetcher import OuraFetcher

        parsed_oura = OuraFetcher({}, db_manager=db_manager)._parse_oura_data(
            activity_resp,
            sleep_resp,
            readiness_resp,
            USER_ID,
        )
        for record in parsed_oura:
            if not _in_window(record.get("measured_at"), start_date, end_date):
                continue
            db_manager.insert_oura_data(
                user_id=record["user_id"],
                measured_at=record["measured_at"],
                activity_score=record.get("activity_score"),
                sleep_score=record.get("sleep_score"),
                readiness_score=record.get("readiness_score"),
                steps=record.get("steps"),
                total_sleep_duration=record.get("total_sleep_duration"),
                raw_data=record.get("raw_data", ""),
            )
            results["Oura"] += 1

    # ── Withings ──
    withings_rows = _load_raw_rows(
        db_manager,
        user_id=USER_ID,
        source="withings",
        category="measure",
        start_iso=start_iso,
        end_iso=end_iso,
    )
    # 1日1レコード（最新計測）に正規化
    withings_daily: Dict[str, Dict[str, Any]] = {}
    for row in withings_rows:
        grp = row.get("payload")
        if not isinstance(grp, dict):
            continue
        try:
            measured_dt = datetime.fromtimestamp(int(grp.get("date", 0)), tz=JST)
        except (TypeError, ValueError, OSError):
            continue
        if not _in_window(measured_dt.strftime("%Y-%m-%d"), start_date, end_date):
            continue
        for measure in grp.get("measures", []):
            if measure.get("type") != 1:
                continue
            weight_value = measure.get("value")
            unit = measure.get("unit")
            if weight_value is None or unit is None:
                continue
            weight_kg = round(float(weight_value) * (10 ** int(unit)), 2)
            day = measured_dt.strftime("%Y-%m-%d")
            prev = withings_daily.get(day)
            if prev is None or measured_dt > prev["measured_dt"]:
                withings_daily[day] = {
                    "measured_dt": measured_dt,
                    "weight_kg": weight_kg,
                    "raw_data": {"status": 0, "body": {"measuregrps": [grp]}},
                }

    for day, agg in sorted(withings_daily.items()):
        db_manager.insert_weight_data(
            user_id=USER_ID,
            measured_at=f"{day} 00:00:00",
            weight_kg=agg["weight_kg"],
            raw_data=agg["raw_data"],
        )
        results["Withings"] += 1

    # ── Google Fit ──
    gfit_rows = _load_raw_rows(db_manager, user_id=USER_ID, source="google_fit", start_iso=start_iso, end_iso=end_iso)
    gfit_seen_payload_hashes: Set[str] = set()
    gfit_steps_daily: Dict[str, Dict[str, Any]] = {}
    gfit_sleep_daily: Dict[str, int] = {}
    gfit_sleep_meta_daily: Dict[str, Dict[str, Any]] = {}
    gfit_weight_daily: Dict[str, Dict[str, Any]] = {}
    gfit_seen_sleep_sessions: Set[tuple] = set()
    gfit_seen_weight_points: Set[tuple] = set()
    gfit_sleep_intervals_by_day_app: Dict[str, Dict[str, List[Tuple[datetime, datetime]]]] = {}
    gfit_awake_intervals_by_day_app: Dict[str, Dict[str, List[Tuple[datetime, datetime]]]] = {}

    for row in gfit_rows:
        category = str(row.get("category") or "")
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue

        row_payload_hash = _payload_hash({"category": category, "payload": payload})
        if row_payload_hash in gfit_seen_payload_hashes:
            continue
        gfit_seen_payload_hashes.add(row_payload_hash)

        fetched_at = str(row.get("fetched_at") or "")

        if category == "steps":
            for bucket in payload.get("bucket", []):
                start_dt = _epoch_to_jst_datetime(bucket.get("startTimeMillis"))
                if start_dt is None:
                    continue
                date_text = start_dt.strftime("%Y-%m-%d")
                if not _in_window(date_text, start_date, end_date):
                    continue
                steps = 0
                for dataset in bucket.get("dataset", []):
                    for point in dataset.get("point", []):
                        for val in point.get("value", []):
                            try:
                                steps += int(val.get("intVal", 0))
                            except (TypeError, ValueError):
                                continue

                prev = gfit_steps_daily.get(date_text)
                if prev is None or fetched_at >= str(prev.get("fetched_at") or ""):
                    gfit_steps_daily[date_text] = {
                        "fetched_at": fetched_at,
                        "steps": steps,
                        "raw_data": bucket,
                    }

        elif category == "weight":
            for point in payload.get("point", []):
                point_key = (point.get("startTimeNanos"), point.get("endTimeNanos"))
                if point_key in gfit_seen_weight_points:
                    continue
                gfit_seen_weight_points.add(point_key)

                measured_dt = _epoch_to_jst_datetime(point.get("startTimeNanos"))
                if measured_dt is None:
                    continue
                measured_at = measured_dt.isoformat()
                if not _in_window(measured_at, start_date, end_date):
                    continue
                for val in point.get("value", []):
                    if "fpVal" not in val:
                        continue
                    day = measured_dt.strftime("%Y-%m-%d")
                    prev = gfit_weight_daily.get(day)
                    if prev is None or measured_dt > prev["measured_dt"]:
                        gfit_weight_daily[day] = {
                            "measured_dt": measured_dt,
                            "value": round(float(val["fpVal"]), 2),
                            "raw_data": point,
                        }

        elif category == "sleep":
            for session in payload.get("session", []):
                start_ms = session.get("startTimeMillis")
                end_ms = session.get("endTimeMillis")
                if not start_ms or not end_ms:
                    continue
                session_key = (start_ms, end_ms, session.get("id"), session.get("name"))
                if session_key in gfit_seen_sleep_sessions:
                    continue
                gfit_seen_sleep_sessions.add(session_key)

                start_time = _epoch_to_jst_datetime(start_ms)
                end_time = _epoch_to_jst_datetime(end_ms)
                if start_time is None or end_time is None:
                    continue
                is_awake = _is_awake_session_with_keywords(session, sleep_parser_cfg["awake_keywords"])
                app_key = _session_app_key(session)
                for day_text, seg_start, seg_end in _split_interval_by_day(start_time, end_time):
                    if not _in_window(day_text, start_date, end_date):
                        continue
                    if is_awake:
                        gfit_awake_intervals_by_day_app.setdefault(day_text, {}).setdefault(app_key, []).append((seg_start, seg_end))
                    else:
                        gfit_sleep_intervals_by_day_app.setdefault(day_text, {}).setdefault(app_key, []).append((seg_start, seg_end))

    for day_text, app_intervals in gfit_sleep_intervals_by_day_app.items():
        app_minutes: Dict[str, int] = {}
        for app_key, intervals in app_intervals.items():
            merged_sleep = _merge_intervals(intervals)
            merged_awake = _merge_intervals(gfit_awake_intervals_by_day_app.get(day_text, {}).get(app_key, []))
            effective_sleep = _subtract_intervals(merged_sleep, merged_awake)
            minutes = _interval_minutes(effective_sleep)
            if minutes > 0:
                app_minutes[app_key] = minutes

        if not app_minutes:
            continue

        chosen_app, minutes = _select_sleep_source(
            app_minutes,
            sleep_parser_cfg["source_policy"],
            sleep_parser_cfg["min_candidate_minutes"],
        )
        if minutes > 0:
            gfit_sleep_daily[day_text] = minutes
            gfit_sleep_meta_daily[day_text] = {
                "chosen_app": chosen_app,
                "candidate_minutes": app_minutes,
                "source_policy": sleep_parser_cfg["source_policy"],
                "awake_keywords": sleep_parser_cfg["awake_keywords"],
            }

    for day, steps_entry in sorted(gfit_steps_daily.items()):
        db_manager.insert_google_fit_data(
            user_id=USER_ID,
            date=day,
            data_type="steps",
            value=steps_entry["steps"],
            raw_data=steps_entry.get("raw_data") or {"day": day, "steps_sum": steps_entry["steps"]},
        )
        results["GoogleFit"] += 1

    for day, minutes in sorted(gfit_sleep_daily.items()):
        meta = gfit_sleep_meta_daily.get(day, {})
        db_manager.insert_google_fit_data(
            user_id=USER_ID,
            date=day,
            data_type="sleep",
            value=minutes,
            raw_data={
                "day": day,
                "sleep_minutes_sum": minutes,
                "chosen_app": meta.get("chosen_app"),
                "candidate_minutes": meta.get("candidate_minutes", {}),
                "source_policy": meta.get("source_policy"),
            },
        )
        results["GoogleFit"] += 1

    for day, agg in sorted(gfit_weight_daily.items()):
        db_manager.insert_google_fit_data(
            user_id=USER_ID,
            date=day,
            data_type="weight",
            value=agg["value"],
            raw_data=agg["raw_data"],
        )
        results["GoogleFit"] += 1

    # ── Weather ──
    weather_rows = _load_raw_rows(
        db_manager,
        user_id="system",
        source="weather",
        category="current_weather",
        start_iso=start_iso,
        end_iso=end_iso,
    )
    for row in weather_rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        dt_unix = payload.get("dt")
        if isinstance(dt_unix, (int, float)):
            timestamp = datetime.fromtimestamp(float(dt_unix), tz=JST).isoformat()
        else:
            fallback_dt = datetime.now(JST)
            timestamp = _to_jst_iso(row.get("fetched_at") or row.get("recorded_at"), fallback_dt)
        if not _in_window(timestamp, start_date, end_date):
            continue
        weather_desc = payload.get("weather", [{}])[0].get("description", "不明")
        weather_summary = f"🌤️ {weather_desc}"
        db_manager.insert_environmental_log(
            timestamp=timestamp,
            source="config_fallback",
            latitude=payload.get("coord", {}).get("lat"),
            longitude=payload.get("coord", {}).get("lon"),
            weather_summary=weather_summary,
            temp=payload.get("main", {}).get("temp"),
            humidity=payload.get("main", {}).get("humidity"),
            pressure=payload.get("main", {}).get("pressure"),
            raw_data=payload,
        )
        results["Weather"] += 1

    # ── SwitchBot (indoor) ──
    switchbot_rows = _load_raw_rows(
        db_manager,
        user_id="system",
        source="switchbot",
        category="environment",
        start_iso=start_iso,
        end_iso=end_iso,
    )
    for row in switchbot_rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        fallback_dt = datetime.now(JST)
        timestamp = _to_jst_iso(row.get("fetched_at") or row.get("recorded_at"), fallback_dt)
        if not _in_window(timestamp, start_date, end_date):
            continue
        db_manager.insert_environmental_log(
            timestamp=timestamp,
            source="switchbot",
            latitude=None,
            longitude=None,
            weather_summary="switchbot_indoor",
            temp=_extract_switchbot_value(payload, "temperature"),
            humidity=_extract_switchbot_value(payload, "humidity"),
            pressure=_extract_switchbot_value(payload, "atmosphericPressure"),
            raw_data=payload,
        )
        results["SwitchBot"] += 1

    logger.info(
        "parse-only done | Oura:%s | Withings:%s | GoogleFit:%s | Weather:%s | SwitchBot:%s",
        results["Oura"],
        results["Withings"],
        results["GoogleFit"],
        results["Weather"],
        results["SwitchBot"],
    )


def run_all_fetchers(days: Optional[int] = None):
    """すべての Fetcher を実行し、Supabase へ保存する"""
    from src.database_manager import DatabaseManager

    db_manager = DatabaseManager()

    end_dt = datetime.now(JST)
    end_str = end_dt.strftime("%Y-%m-%d")
    lookback_days = days if days is not None else DEFAULT_BOOTSTRAP_DAYS

    window_start_str = (end_dt - timedelta(days=max(0, lookback_days))).strftime("%Y-%m-%d")
    oura_existing_dates = db_manager.get_oura_dates(USER_ID, window_start_str, end_str)
    withings_existing_dates = db_manager.get_weight_dates(USER_ID, window_start_str, end_str)
    google_fit_existing_dates = db_manager.get_google_fit_dates(
        USER_ID,
        window_start_str,
        end_str,
        data_type="steps",
    )

    oura_start_str = _resolve_start_date(
        db_manager.get_latest_oura_measured_at(USER_ID),
        oura_existing_dates,
        end_dt,
        lookback_days=lookback_days,
    )
    withings_start_str = _resolve_start_date(
        db_manager.get_latest_weight_measured_at(USER_ID),
        withings_existing_dates,
        end_dt,
        lookback_days=lookback_days,
    )
    google_fit_start_str = _resolve_start_date(
        db_manager.get_latest_google_fit_date(USER_ID, data_type="steps"),
        google_fit_existing_dates,
        end_dt,
        lookback_days=lookback_days,
    )

    logger.info(
        "backfill window(days=%s) | Oura:%s..%s | Withings:%s..%s | GoogleFit:%s..%s",
        lookback_days,
        oura_start_str,
        end_str,
        withings_start_str,
        end_str,
        google_fit_start_str,
        end_str,
    )

    results = {}

    # ── Oura ──
    def fetch_oura():
        from src.fetchers.oura_fetcher import OuraFetcher
        fetcher = OuraFetcher({}, db_manager=db_manager)
        if not fetcher.authenticate():
            return "skip"
        data = fetcher.fetch_data(USER_ID, oura_start_str, end_str)
        saved = 0
        for record in data:
            db_manager.insert_oura_data(
                user_id=record["user_id"],
                measured_at=record["measured_at"],
                activity_score=record.get("activity_score"),
                sleep_score=record.get("sleep_score"),
                readiness_score=record.get("readiness_score"),
                steps=record.get("steps"),
                total_sleep_duration=record.get("total_sleep_duration"),
                raw_data=record.get("raw_data", ""),
            )
            saved += 1
        return saved
    results["Oura"] = _run_fetcher("Oura", fetch_oura)

    # ── Withings ──
    def fetch_withings():
        from auth.exceptions import OAuthRefreshError
        from auth.withings_oauth import WithingsOAuth
        from src.fetchers.withings_fetcher import WithingsFetcher
        withings_oauth = WithingsOAuth(db_manager)
        try:
            withings_oauth.get_valid_access_token(strict=True)
        except OAuthRefreshError as e:
            raise RuntimeError(f"Withings OAuth failed: {e}") from e
        fetcher = WithingsFetcher({}, withings_oauth, db_manager=db_manager)
        data = fetcher.fetch_data(USER_ID, withings_start_str, end_str)
        saved = 0
        for record in data:
            db_manager.insert_weight_data(
                user_id=record["user_id"],
                measured_at=record["measured_at"],
                weight_kg=record["weight_kg"],
                raw_data=record.get("raw_data", ""),
            )
            saved += 1
        return saved
    results["Withings"] = _run_fetcher("Withings", fetch_withings)

    # ── Weather ──
    def fetch_weather():
        from src.fetchers.weather_fetcher import WeatherFetcher
        wf = WeatherFetcher(db_manager=db_manager)
        if not wf.is_available():
            return "skip"
        weather = wf.fetch_weather()
        if not weather:
            return 0
        db_manager.insert_environmental_log(
            timestamp=weather["timestamp"],
            source=weather["source"],
            latitude=weather["latitude"],
            longitude=weather["longitude"],
            weather_summary=weather["weather_summary"],
            temp=weather["temp"],
            humidity=weather["humidity"],
            pressure=weather["pressure"],
            raw_data=weather["raw_data"],
        )
        return 1
    results["Weather"] = _run_fetcher("Weather", fetch_weather)

    # ── SwitchBot ──
    def fetch_switchbot():
        from src.fetchers.switchbot_fetcher import SwitchBotFetcher
        sf = SwitchBotFetcher(db_manager=db_manager)
        if not sf.is_available():
            return "skip"
        return 1 if sf.fetch_device_status() else 0
    results["SwitchBot"] = _run_fetcher("SwitchBot", fetch_switchbot)

    # ── Google Fit ──
    # OAuth ブラウザフローが必要なため CI では通常スキップ。
    # DB に保存済みトークンがあればリフレッシュして取得を試みる。
    def fetch_google_fit():
        from auth.exceptions import OAuthRefreshError
        from auth.google_oauth import GoogleOAuth
        from src.fetchers.google_fit_fetcher import GoogleFitFetcher
        gauth = GoogleOAuth(db_manager)
        try:
            gauth.ensure_credentials(strict=True)
            creds = gauth.get_credentials(strict=True)
        except OAuthRefreshError as e:
            logger.warning(
                "GoogleFit skipped: %s. Authenticate via Streamlit UI (API連携 > Google Fit にログイン) first.",
                e,
            )
            return "skip"
        gfit = GoogleFitFetcher(creds, db_manager=db_manager)
        
        # Regular fetch for date range
        fit_data = gfit.fetch_all(USER_ID, google_fit_start_str, end_str)
        saved = 0
        for records in fit_data.values():
            for record in records:
                db_manager.insert_google_fit_data(
                    user_id=record["user_id"],
                    date=record["date"],
                    data_type=record["data_type"],
                    value=record["value"],
                    raw_data=record["raw_data"],
                )
                saved += 1
        
        # Daily finalization: fetch previous day's confirmed data at 00:30 JST
        current_hour = datetime.now(JST).hour
        current_minute = datetime.now(JST).minute
        if current_hour == 0 and current_minute >= 30 and current_minute < 45:
            logger.info("Google Fit: fetching previous day's finalized steps data")
            finalized = gfit.fetch_steps_finalized(USER_ID)
            if finalized:
                db_manager.insert_google_fit_data(
                    user_id=finalized["user_id"],
                    date=finalized["date"],
                    data_type=finalized["data_type"],
                    value=finalized["value"],
                    raw_data=finalized["raw_data"],
                )
                logger.info(f"Google Fit: finalized steps for {finalized['date']}: {finalized['value']} steps")
                saved += 1
        
        return saved
    results["GoogleFit"] = _run_fetcher("GoogleFit", fetch_google_fit)

    # ── サマリー（1行ログ） ──
    parts = []
    for name, val in results.items():
        if val is None:
            parts.append(f"{name}:ERR")
        elif val == "skip":
            parts.append(f"{name}:--")
        else:
            parts.append(f"{name}:{val}")
    logger.info("fetch done | " + " | ".join(parts))


def main():
    parser = argparse.ArgumentParser(description="YuruHealth CLI")
    parser.add_argument("--auto", action="store_true", help="Run all fetchers automatically")
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Skip external fetchers and parse only existing raw_data_lake records",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Backfill/reparse lookback days. Example: --auto --days 14 or --parse-only --days 14",
    )
    args = parser.parse_args()

    if args.days is not None and args.days < 0:
        parser.error("--days must be 0 or greater")

    # 引数なしでも既定で auto 実行（ラズパイ定期実行を簡素化）
    should_run_auto = args.auto or (args.days is not None and not args.parse_only) or len(sys.argv) == 1

    if args.parse_only:
        try:
            run_all_parsers(days=args.days)
        except Exception:
            logger.error("parse-only failed; exiting with status 1")
            sys.exit(1)
    elif should_run_auto:
        try:
            run_all_fetchers(days=args.days)
        except Exception:
            logger.error("auto-fetch failed; exiting with status 1")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
