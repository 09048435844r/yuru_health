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
from typing import Callable, Optional, Set

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
        "--days",
        type=int,
        default=None,
        help="Backfill lookback days (manual recovery). Example: --auto --days 14",
    )
    args = parser.parse_args()

    if args.days is not None and args.days < 0:
        parser.error("--days must be 0 or greater")

    # 引数なしでも既定で auto 実行（ラズパイ定期実行を簡素化）
    should_run_auto = args.auto or args.days is not None or len(sys.argv) == 1

    if should_run_auto:
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
