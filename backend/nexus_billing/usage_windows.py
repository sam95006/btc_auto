"""Deterministic UTC usage windows for BILLING-6.

Centralized so nobody computes window boundaries ad-hoc. Windows are in UTC.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.nexus_billing.usage_policy import WINDOW_DAILY, WINDOW_MONTHLY, WINDOW_NONE


def _utc(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def daily_window_start(now: datetime) -> datetime:
    d = _utc(now)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def monthly_window_start(now: datetime) -> datetime:
    d = _utc(now)
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def window_start_for(window_type: str, now: datetime) -> Optional[datetime]:
    if window_type == WINDOW_DAILY:
        return daily_window_start(now)
    if window_type == WINDOW_MONTHLY:
        return monthly_window_start(now)
    return None  # WINDOW_NONE / capacity


def window_reset_at(window_type: str, now: datetime) -> Optional[datetime]:
    """The next boundary at which the window resets (UTC)."""
    if window_type == WINDOW_DAILY:
        return daily_window_start(now) + timedelta(days=1)
    if window_type == WINDOW_MONTHLY:
        start = monthly_window_start(now)
        if start.month == 12:
            return start.replace(year=start.year + 1, month=1)
        return start.replace(month=start.month + 1)
    return None
