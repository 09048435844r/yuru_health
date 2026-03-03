#!/bin/bash
# Worker script with system health collection

# Read environment variables with defaults
FETCH_INTERVAL="${FETCH_INTERVAL_SECONDS:-900}"
HEALTH_INTERVAL="${SYSTEM_HEALTH_INTERVAL_SECONDS:-300}"
RETENTION_DAYS="${SYSTEM_HEALTH_RETENTION_DAYS:-30}"
DISK_PATH="${SYSTEM_HEALTH_DISK_PATH:-/app}"

# Validate intervals
case "$FETCH_INTERVAL" in
    ''|*[!0-9]*)
        echo "[worker] invalid FETCH_INTERVAL_SECONDS='$FETCH_INTERVAL', fallback to 900"
        FETCH_INTERVAL=900
        ;;
esac

case "$HEALTH_INTERVAL" in
    ''|*[!0-9]*)
        echo "[worker] invalid SYSTEM_HEALTH_INTERVAL_SECONDS='$HEALTH_INTERVAL', fallback to 300"
        HEALTH_INTERVAL=300
        ;;
esac

case "$RETENTION_DAYS" in
    ''|*[!0-9]*)
        echo "[worker] invalid SYSTEM_HEALTH_RETENTION_DAYS='$RETENTION_DAYS', fallback to 30"
        RETENTION_DAYS=30
        ;;
esac

echo "[worker] Starting with fetch_interval=${FETCH_INTERVAL}s health_interval=${HEALTH_INTERVAL}s retention_days=${RETENTION_DAYS}"

# Track last health collection time
last_health=0

while true; do
    now=$(date +%s)
    
    # Run system health collection if interval has passed
    if [ $((now - last_health)) -ge "$HEALTH_INTERVAL" ]; then
        echo "[worker] $(date -Iseconds) start system health collection"
        python -m src.utils.system_health_store || echo "[worker] system health collection failed"
        last_health=$now
    fi

    # Run main fetchers
    echo "[worker] $(date -Iseconds) start fetch"
    python -m src.main --auto
    rc=$?
    echo "[worker] $(date -Iseconds) done rc=$rc"
    
    sleep 60  # Check every minute for health collection
done
