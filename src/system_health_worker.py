from __future__ import annotations

import logging
import os
import time

from src.utils.system_health_store import ensure_system_health_sample

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[system-health-worker] %(asctime)s %(levelname)s %(message)s")


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        logger.warning("invalid %s=%r, fallback to %s", name, raw, default)
        return default
    return max(60, value)


def main() -> None:
    interval = _read_int_env("SYSTEM_HEALTH_INTERVAL_SECONDS", 300)
    retention_days = _read_int_env("SYSTEM_HEALTH_RETENTION_DAYS", 30)
    disk_path = os.getenv("SYSTEM_HEALTH_DISK_PATH", "/app").strip() or "/app"

    logger.info(
        "starting collector interval=%ss retention_days=%s disk_path=%s",
        interval,
        retention_days,
        disk_path,
    )

    while True:
        try:
            result = ensure_system_health_sample(
                sample_interval_seconds=interval,
                retention_days=retention_days,
                disk_path=disk_path,
            )
            latest = result.get("latest") if isinstance(result, dict) else None
            inserted = bool(result.get("inserted")) if isinstance(result, dict) else False
            measured_at = latest.get("measured_at") if isinstance(latest, dict) else None
            logger.info("sample checked inserted=%s measured_at=%s", inserted, measured_at)
        except Exception as exc:
            logger.exception("collector loop error: %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    main()
