"""
YuruHealth 自動データ取得エントリーポイント
GitHub Actions (cron) やローカルから実行可能。

Usage:
    python -m src.main --auto
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

JST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

USER_ID = "user_001"
DEFAULT_BOOTSTRAP_DAYS = 30


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
    from src.database_manager import DatabaseManager

    db_manager = DatabaseManager()
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
    withings_measuregrps: List[Dict[str, Any]] = []
    for row in withings_rows:
        payload = row.get("payload")
        if isinstance(payload, dict):
            withings_measuregrps.append(payload)

    for grp in withings_measuregrps:
        measured_at = datetime.fromtimestamp(int(grp.get("date", 0)), tz=JST).strftime("%Y-%m-%d %H:%M:%S")
        if not _in_window(measured_at, start_date, end_date):
            continue
        for measure in grp.get("measures", []):
            if measure.get("type") != 1:
                continue
            weight_kg = measure.get("value")
            unit = measure.get("unit")
            if weight_kg is None or unit is None:
                continue
            db_manager.insert_weight_data(
                user_id=USER_ID,
                measured_at=measured_at,
                weight_kg=round(float(weight_kg) * (10 ** int(unit)), 2),
                raw_data={"status": 0, "body": {"measuregrps": [grp]}},
            )
            results["Withings"] += 1

    # ── Google Fit ──
    gfit_rows = _load_raw_rows(db_manager, user_id=USER_ID, source="google_fit", start_iso=start_iso, end_iso=end_iso)
    for row in gfit_rows:
        category = str(row.get("category") or "")
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue

        if category == "steps":
            for bucket in payload.get("bucket", []):
                date_text = datetime.fromtimestamp(int(bucket.get("startTimeMillis", "0")) / 1000, tz=JST).strftime("%Y-%m-%d")
                if not _in_window(date_text, start_date, end_date):
                    continue
                steps = 0
                for dataset in bucket.get("dataset", []):
                    for point in dataset.get("point", []):
                        for val in point.get("value", []):
                            steps += int(val.get("intVal", 0))
                db_manager.insert_google_fit_data(
                    user_id=USER_ID,
                    date=date_text,
                    data_type="steps",
                    value=steps,
                    raw_data=bucket,
                )
                results["GoogleFit"] += 1

        elif category == "weight":
            for point in payload.get("point", []):
                start_nanos = point.get("startTimeNanos")
                if not start_nanos:
                    continue
                measured_at = datetime.fromtimestamp(int(start_nanos) / 1e9, tz=JST).isoformat()
                if not _in_window(measured_at, start_date, end_date):
                    continue
                for val in point.get("value", []):
                    if "fpVal" not in val:
                        continue
                    db_manager.insert_google_fit_data(
                        user_id=USER_ID,
                        date=measured_at,
                        data_type="weight",
                        value=round(float(val["fpVal"]), 2),
                        raw_data=point,
                    )
                    results["GoogleFit"] += 1

        elif category == "sleep":
            for session in payload.get("session", []):
                start_ms = session.get("startTimeMillis")
                end_ms = session.get("endTimeMillis")
                if not start_ms or not end_ms:
                    continue
                start_time = datetime.fromtimestamp(int(start_ms) / 1000, tz=JST)
                end_time = datetime.fromtimestamp(int(end_ms) / 1000, tz=JST)
                date_text = start_time.strftime("%Y-%m-%d")
                if not _in_window(date_text, start_date, end_date):
                    continue
                db_manager.insert_google_fit_data(
                    user_id=USER_ID,
                    date=date_text,
                    data_type="sleep",
                    value=int((end_time - start_time).total_seconds() / 60),
                    raw_data=session,
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
        if not isinstance(dt_unix, (int, float)):
            continue
        timestamp = datetime.fromtimestamp(float(dt_unix), tz=JST).isoformat()
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

    logger.info(
        "parse-only done | Oura:%s | Withings:%s | GoogleFit:%s | Weather:%s",
        results["Oura"],
        results["Withings"],
        results["GoogleFit"],
        results["Weather"],
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
    google_fit_existing_dates = db_manager.get_google_fit_dates(USER_ID, window_start_str, end_str)

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
        db_manager.get_latest_google_fit_date(USER_ID),
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
