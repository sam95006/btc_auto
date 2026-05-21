import os
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


def meeting_timezone_name():
    return str(os.getenv("NEXUS_MEETING_TIMEZONE", "Asia/Taipei") or "Asia/Taipei").strip()


def nexus_now():
    """Wall-clock for meetings and UI timestamps (default: Asia/Taipei)."""
    tz_name = meeting_timezone_name()
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    return datetime.now()
