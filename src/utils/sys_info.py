from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency fallback
    psutil = None

THERMAL_PATHS = (
    Path("/sys/class/thermal/thermal_zone0/temp"),
    Path("/host_sys/class/thermal/thermal_zone0/temp"),
)


def _read_cpu_temperature_c() -> Optional[float]:
    """Read Raspberry Pi CPU temperature from sysfs (Celsius)."""
    for path in THERMAL_PATHS:
        try:
            if not path.exists():
                continue
            raw = path.read_text(encoding="utf-8").strip()
            value = float(raw)
            if value > 1000:
                value = value / 1000.0
            return round(value, 1)
        except Exception:
            continue
    return None


def _read_cpu_percent_fallback(interval: float = 0.2) -> float:
    def _read_cpu_times() -> Optional[tuple[int, int]]:
        try:
            first_line = Path("/host_proc/stat").read_text(encoding="utf-8").splitlines()[0]
        except Exception:
            try:
                first_line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
            except Exception:
                return None
        parts = first_line.split()
        if len(parts) < 8 or parts[0] != "cpu":
            return None
        nums = [int(x) for x in parts[1:8]]
        idle = nums[3] + nums[4]
        total = sum(nums)
        return total, idle

    a = _read_cpu_times()
    if not a:
        return 0.0
    time.sleep(max(0.05, interval))
    b = _read_cpu_times()
    if not b:
        return 0.0
    total_delta = b[0] - a[0]
    idle_delta = b[1] - a[1]
    if total_delta <= 0:
        return 0.0
    usage = (1.0 - (idle_delta / total_delta)) * 100.0
    return max(0.0, min(100.0, usage))


def _read_memory_percent_fallback() -> float:
    meminfo_paths = (Path("/host_proc/meminfo"), Path("/proc/meminfo"))
    raw = ""
    for path in meminfo_paths:
        try:
            raw = path.read_text(encoding="utf-8")
            if raw:
                break
        except Exception:
            continue
    if not raw:
        return 0.0

    values: Dict[str, int] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        parts = v.strip().split()
        if not parts:
            continue
        try:
            values[k] = int(parts[0])
        except ValueError:
            continue

    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    if total <= 0:
        return 0.0
    used_ratio = 1.0 - (available / total)
    return max(0.0, min(100.0, used_ratio * 100.0))


def _read_disk_percent_fallback(disk_path: str = "/") -> float:
    try:
        usage = shutil.disk_usage(disk_path)
    except Exception:
        usage = shutil.disk_usage("/")
    if usage.total <= 0:
        return 0.0
    return (usage.used / usage.total) * 100.0


def get_system_health(disk_path: str = "/") -> Dict[str, Any]:
    """Return lightweight host/system health metrics for UI widgets."""
    cpu_temp_c = _read_cpu_temperature_c()

    if psutil is not None:
        try:
            cpu_percent = float(psutil.cpu_percent(interval=0.2))
        except Exception:
            cpu_percent = _read_cpu_percent_fallback(interval=0.2)

        try:
            memory_percent = float(psutil.virtual_memory().percent)
        except Exception:
            memory_percent = _read_memory_percent_fallback()

        try:
            disk_percent = float(psutil.disk_usage(disk_path).percent)
        except Exception:
            disk_percent = _read_disk_percent_fallback(disk_path=disk_path)
    else:
        cpu_percent = _read_cpu_percent_fallback(interval=0.2)
        memory_percent = _read_memory_percent_fallback()
        disk_percent = _read_disk_percent_fallback(disk_path=disk_path)

    return {
        "cpu_temp_c": cpu_temp_c,
        "cpu_percent": round(cpu_percent, 1),
        "memory_percent": round(memory_percent, 1),
        "disk_percent": round(disk_percent, 1),
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }
