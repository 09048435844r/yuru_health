"""
YuruHealth 自動データ取得エントリーポイント
GitHub Actions (cron) やローカルから実行可能。

Usage:
    python src/main.py --auto
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

USER_ID = "user_001"


def run_all_fetchers():
    """すべての Fetcher を実行し、Supabase へ保存する"""
    from src.database_manager import DatabaseManager

    logger.info("=== YuruHealth auto-fetch started ===")
    db_manager = DatabaseManager()

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=7)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    # ── Oura ──
    try:
        from src.fetchers.oura_fetcher import OuraFetcher
        fetcher = OuraFetcher({}, db_manager=db_manager)
        if fetcher.authenticate():
            logger.info("Oura: authenticated, fetching 7-day data...")
            data = fetcher.fetch_data(USER_ID, start_str, end_str)
            saved = 0
            for record in data:
                try:
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
                except Exception:
                    pass
            logger.info(f"Oura: {saved} records saved")
        else:
            logger.info("Oura: not configured, skipping")
    except Exception as e:
        logger.warning(f"Oura fetch error: {e}")

    # ── Withings ──
    try:
        from auth.withings_oauth import WithingsOAuth
        from src.withings_fetcher import WithingsFetcher
        withings_oauth = WithingsOAuth(db_manager)
        if withings_oauth.is_authenticated():
            logger.info("Withings: authenticated, fetching data...")
            fetcher = WithingsFetcher({}, withings_oauth, db_manager=db_manager)
            data = fetcher.fetch_data(USER_ID, start_str, end_str)
            saved = 0
            for record in data:
                try:
                    db_manager.insert_weight_data(
                        user_id=record["user_id"],
                        measured_at=record["measured_at"],
                        weight_kg=record["weight_kg"],
                        raw_data=record.get("raw_data", ""),
                    )
                    saved += 1
                except Exception:
                    pass
            logger.info(f"Withings: {saved} records saved")
        else:
            logger.info("Withings: not authenticated (OAuth token missing), skipping")
    except Exception as e:
        logger.warning(f"Withings fetch error: {e}")

    # ── Weather ──
    try:
        from src.fetchers.weather_fetcher import WeatherFetcher
        weather_fetcher = WeatherFetcher(db_manager=db_manager)
        if weather_fetcher.is_available():
            logger.info("Weather: fetching current data...")
            weather = weather_fetcher.fetch_weather()
            if weather:
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
                logger.info("Weather: data saved")
            else:
                logger.info("Weather: no data returned")
        else:
            logger.info("Weather: not configured, skipping")
    except Exception as e:
        logger.warning(f"Weather fetch error: {e}")

    # ── SwitchBot ──
    try:
        from src.fetchers.switchbot_fetcher import SwitchBotFetcher
        switchbot_fetcher = SwitchBotFetcher(db_manager=db_manager)
        if switchbot_fetcher.is_available():
            logger.info("SwitchBot: fetching device status...")
            result = switchbot_fetcher.fetch_device_status()
            if result:
                logger.info("SwitchBot: data saved")
            else:
                logger.info("SwitchBot: no data returned")
        else:
            logger.info("SwitchBot: not configured, skipping")
    except Exception as e:
        logger.warning(f"SwitchBot fetch error: {e}")

    # ── Google Fit ──
    # Google Fit は OAuth ブラウザフローが必要なため CI では実行不可。
    # トークンが DB に保存されていればリフレッシュして取得を試みる。
    try:
        from auth.google_oauth import GoogleOAuth
        from src.fetchers.google_fit_fetcher import GoogleFitFetcher
        google_oauth = GoogleOAuth(db_manager)
        google_oauth.ensure_credentials()
        if google_oauth.is_authenticated():
            creds = google_oauth.get_credentials()
            if creds:
                logger.info("Google Fit: authenticated, fetching 7-day data...")
                gfit_fetcher = GoogleFitFetcher(creds, db_manager=db_manager)
                fit_data = gfit_fetcher.fetch_all(USER_ID, start_str, end_str)
                saved = 0
                for data_type, records in fit_data.items():
                    for record in records:
                        try:
                            db_manager.insert_google_fit_data(
                                user_id=record["user_id"],
                                date=record["date"],
                                data_type=record["data_type"],
                                value=record["value"],
                                raw_data=record["raw_data"],
                            )
                            saved += 1
                        except Exception:
                            pass
                logger.info(f"Google Fit: {saved} records saved")
        else:
            logger.info("Google Fit: not authenticated, skipping")
    except Exception as e:
        logger.warning(f"Google Fit fetch error: {e}")

    logger.info("=== YuruHealth auto-fetch completed ===")


def main():
    parser = argparse.ArgumentParser(description="YuruHealth CLI")
    parser.add_argument("--auto", action="store_true", help="Run all fetchers automatically")
    args = parser.parse_args()

    if args.auto:
        run_all_fetchers()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
