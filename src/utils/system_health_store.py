from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.sys_info import get_system_health

logger = logging.getLogger(__name__)

DB_PATH = Path("data/system_health.db")
TABLE_NAME = "system_health_logs"


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_system_health_db(db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                measured_at TEXT NOT NULL,
                cpu_temp_c REAL,
                cpu_percent REAL NOT NULL,
                memory_percent REAL NOT NULL,
                disk_percent REAL NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_measured_at
            ON {TABLE_NAME} (measured_at)
            """
        )
        conn.commit()


def _parse_iso_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _delete_old_rows(conn: sqlite3.Connection, retention_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
    conn.execute(
        f"DELETE FROM {TABLE_NAME} WHERE measured_at < ?",
        (_to_iso_utc(cutoff),),
    )


def get_latest_system_health(db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
    init_system_health_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT measured_at, cpu_temp_c, cpu_percent, memory_percent, disk_percent
            FROM {TABLE_NAME}
            ORDER BY measured_at DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def ensure_system_health_sample(
    *,
    sample_interval_seconds: int = 300,
    retention_days: int = 30,
    disk_path: str = "/",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    """Insert a sample only when latest point is older than sample interval.

    Also rotates data by deleting rows older than retention_days.
    """
    init_system_health_db(db_path)
    now_utc = datetime.now(timezone.utc)
    interval = max(60, int(sample_interval_seconds))

    with _connect(db_path) as conn:
        latest = conn.execute(
            f"SELECT measured_at FROM {TABLE_NAME} ORDER BY measured_at DESC LIMIT 1"
        ).fetchone()

        should_insert = True
        if latest and latest[0]:
            last_dt = _parse_iso_utc(str(latest[0]))
            if last_dt and (now_utc - last_dt).total_seconds() < interval:
                should_insert = False

        if should_insert:
            metrics = get_system_health(disk_path=disk_path)
            measured_at = str(metrics.get("measured_at") or _to_iso_utc(now_utc))
            conn.execute(
                f"""
                INSERT INTO {TABLE_NAME} (measured_at, cpu_temp_c, cpu_percent, memory_percent, disk_percent)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    measured_at,
                    metrics.get("cpu_temp_c"),
                    float(metrics.get("cpu_percent") or 0.0),
                    float(metrics.get("memory_percent") or 0.0),
                    float(metrics.get("disk_percent") or 0.0),
                ),
            )

        _delete_old_rows(conn, retention_days=retention_days)
        conn.commit()

    latest_row = get_latest_system_health(db_path=db_path)
    return {
        "inserted": should_insert,
        "latest": latest_row,
    }


def fetch_system_health_history(
    *,
    since_utc: datetime,
    db_path: Path = DB_PATH,
) -> List[Dict[str, Any]]:
    init_system_health_db(db_path)
    query_since = _to_iso_utc(since_utc)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT measured_at, cpu_temp_c, cpu_percent, memory_percent, disk_percent
            FROM {TABLE_NAME}
            WHERE measured_at >= ?
            ORDER BY measured_at ASC
            """,
            (query_since,),
        ).fetchall()
    return [dict(r) for r in rows]


def main() -> None:
    """Entry point for python -m src.utils.system_health_store"""
    logging.basicConfig(level=logging.INFO, format="[system-health] %(asctime)s %(levelname)s %(message)s")
    
    try:
        interval = int(os.getenv("SYSTEM_HEALTH_INTERVAL_SECONDS", "300"))
        retention_days = int(os.getenv("SYSTEM_HEALTH_RETENTION_DAYS", "30"))
        disk_path = os.getenv("SYSTEM_HEALTH_DISK_PATH", "/app")
    except ValueError:
        logger.warning("Invalid environment variables, using defaults")
        interval = 300
        retention_days = 30
        disk_path = "/app"
    
    result = ensure_system_health_sample(
        sample_interval_seconds=interval,
        retention_days=retention_days,
        disk_path=disk_path,
    )
    
    inserted = result.get("inserted", False) if isinstance(result, dict) else False
    latest = result.get("latest") if isinstance(result, dict) else None
    measured_at = latest.get("measured_at") if isinstance(latest, dict) else None
    
    logger.info("system health sample completed inserted=%s measured_at=%s", inserted, measured_at)


if __name__ == "__main__":
    main()
