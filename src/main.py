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

JST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

USER_ID = "user_001"


def _run_fetcher(name: str, func):
    """Fetcher を安全に実行し、結果を1行で返す"""
    try:
        result = func()
        return result
    except Exception as e:
        logger.warning(f"{name}: error — {type(e).__name__}")
        return None


def run_all_fetchers():
    """すべての Fetcher を実行し、Supabase へ保存する"""
    from src.database_manager import DatabaseManager

    db_manager = DatabaseManager()

    end_dt = datetime.now(JST)
    start_dt = end_dt - timedelta(days=7)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    results = {}

    # ── Oura ──
    def fetch_oura():
        from src.fetchers.oura_fetcher import OuraFetcher
        fetcher = OuraFetcher({}, db_manager=db_manager)
        if not fetcher.authenticate():
            return "skip"
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
        return saved
    results["Oura"] = _run_fetcher("Oura", fetch_oura)

    # ── Withings ──
    def fetch_withings():
        from auth.withings_oauth import WithingsOAuth
        from src.withings_fetcher import WithingsFetcher
        withings_oauth = WithingsOAuth(db_manager)
        if not withings_oauth.is_authenticated():
            return "skip"
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
        from auth.google_oauth import GoogleOAuth
        from src.fetchers.google_fit_fetcher import GoogleFitFetcher
        gauth = GoogleOAuth(db_manager)
        gauth.ensure_credentials()
        if not gauth.is_authenticated():
            return "skip"
        creds = gauth.get_credentials()
        if not creds:
            return "skip"
        gfit = GoogleFitFetcher(creds, db_manager=db_manager)
        fit_data = gfit.fetch_all(USER_ID, start_str, end_str)
        saved = 0
        for records in fit_data.values():
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

    if args.auto:
        run_all_fetchers()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
