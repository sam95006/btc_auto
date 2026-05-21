import os

from backend.core.time_utils import meeting_timezone_name

DAILY_REPORT_ENABLED = os.getenv("NEXUS_DAILY_REPORT_ENABLE", "1").strip().lower() in {"1", "true", "yes", "on"}
DAILY_REPORT_SLOTS = tuple(
    slot.strip()
    for slot in os.getenv("NEXUS_DAILY_REPORT_SLOTS", "00:00,12:00").split(",")
    if slot.strip()
)
DAILY_REPORT_TIMEZONE = meeting_timezone_name()
