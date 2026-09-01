"""Starter-trial contract (NEXUS-EXPERIENCE-1A). Pure functions — no DB, no
side effects, no auto-charge. The effective plan is resolved deterministically
from the registration timestamp and any explicit paid subscription."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.nexus_platform.plans import PLAN_FREE, PLAN_STARTER, STARTER_TRIAL_CODE, TRIAL_DAYS


@dataclass(frozen=True)
class TrialWindow:
    code: str
    started_at: datetime
    ends_at: datetime

    def is_active(self, now: datetime) -> bool:
        return self.started_at <= now < self.ends_at


def start_trial(registered_at: datetime) -> TrialWindow:
    """A new Personal user's trial begins at the exact registration timestamp."""
    started = registered_at if registered_at.tzinfo else registered_at.replace(tzinfo=timezone.utc)
    return TrialWindow(code=STARTER_TRIAL_CODE, started_at=started, ends_at=started + timedelta(days=TRIAL_DAYS))


def effective_plan(now: datetime, *, registered_at: Optional[datetime], paid_plan: Optional[str]) -> str:
    """Backend-authoritative effective plan. Paid subscription always wins; then
    an active Starter trial grants Starter; otherwise Free. Never auto-charges."""
    if paid_plan:
        return paid_plan
    if registered_at is not None:
        window = start_trial(registered_at)
        if window.is_active(now if now.tzinfo else now.replace(tzinfo=timezone.utc)):
            return PLAN_STARTER
    return PLAN_FREE


def trial_status(now: datetime, *, registered_at: Optional[datetime], paid_plan: Optional[str]) -> dict:
    if paid_plan:
        return {"state": "PAID", "plan": paid_plan, "trial_active": False}
    if registered_at is None:
        return {"state": "FREE", "plan": PLAN_FREE, "trial_active": False}
    w = start_trial(registered_at)
    n = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    active = w.is_active(n)
    return {
        "state": "TRIAL" if active else "TRIAL_EXPIRED",
        "plan": PLAN_STARTER if active else PLAN_FREE,
        "trial_active": active,
        "trial_code": w.code,
        "trial_started_at": w.started_at.isoformat(),
        "trial_ends_at": w.ends_at.isoformat(),
        "days_remaining": max(0, (w.ends_at - n).days) if active else 0,
    }
