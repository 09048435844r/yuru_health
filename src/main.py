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
from typing import Callable, Optional

JST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

USER_ID = "user_001"
DEFAULT_BOOTSTRAP_DAYS = 30


def _run_fetcher(name: str, func: Callable[[], object]) -> object:
    """Fetcher を実行し、失敗時は詳細ログを出して例外を再送出する。"""
    try:
        result = func()
        return result
    except Exception as e:
        logger.exception(f"{name}: error — {type(e).__name__}: {e}")
        raise


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


def _resolve_start_date(
    latest_value: Optional[str],
    end_dt: datetime,
    bootstrap_days: int = DEFAULT_BOOTSTRAP_DAYS,
) -> str:
    """最新日付の翌日を開始日にし、未登録時は bootstrap_days 分遡る。"""
    latest_date = _parse_latest_date(latest_value)
    if latest_date:
        start_date = latest_date + timedelta(days=1)
    else:
        start_date = (end_dt - timedelta(days=bootstrap_days)).date()

    end_date = end_dt.date()
    if start_date > end_date:
        start_date = end_date

    return start_date.strftime("%Y-%m-%d")


def run_all_fetchers():
    """すべての Fetcher を実行し、Supabase へ保存する"""
    from src.database_manager import DatabaseManager

    db_manager = DatabaseManager()

    end_dt = datetime.now(JST)
    end_str = end_dt.strftime("%Y-%m-%d")

    oura_start_str = _resolve_start_date(db_manager.get_latest_oura_measured_at(USER_ID), end_dt)
    withings_start_str = _resolve_start_date(db_manager.get_latest_weight_measured_at(USER_ID), end_dt)
    google_fit_start_str = _resolve_start_date(db_manager.get_latest_google_fit_date(USER_ID), end_dt)

    logger.info(
        "backfill window | Oura:%s..%s | Withings:%s..%s | GoogleFit:%s..%s",
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
            raise RuntimeError(f"Google OAuth failed: {e}") from e
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
    args = parser.parse_args()

    # 引数なしでも既定で auto 実行（ラズパイ定期実行を簡素化）
    should_run_auto = args.auto or len(sys.argv) == 1

    if should_run_auto:
        try:
            run_all_fetchers()
        except Exception:
            logger.error("auto-fetch failed; exiting with status 1")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
