"""Canonical PERSONAL PRODUCT ACCESS resolver — the single source of truth.

Personal product access is NOT the raw billing subscription. A member on an
active 30-day Starter trial has NO paid billing row, yet their effective Personal
plan is Starter and they must receive Starter entitlements AND Starter quotas.
This module is the ONE place that resolves the effective Personal plan and the
entitlement/quota policy that follows, so /personal/subscription, /personal/
features, entitlement enforcement, quota enforcement, and the membership surfaces
never disagree.

Rule (paid wins, then active trial, else free):
  * a live, non-free, non-enterprise billing subscription  -> that paid plan;
  * else if the account registration (accounts.created_at) is inside the 30-day
    Starter trial                                           -> starter;
  * else                                                    -> free.

Enterprise is a SEPARATE product and is NEVER returned as a Personal plan. When
the registration origin cannot be resolved truthfully and there is no paid plan,
the plan is free — never a fabricated Starter.

Billing truth is NOT corrupted here: a trial member still has no paid billing
row / an inactive billing status. This module only decides which effective plan
supplies entitlement + quota POLICY; it never mints a paid subscription.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from backend.nexus_billing.entitlements import (
    EntitlementResolution,
    resolve_entitlements_for_plan,
)
from backend.nexus_billing.subscription import STATUS_INACTIVE
from backend.nexus_platform import plans as _plans
from backend.nexus_platform import trial as _trial

ENTERPRISE = _plans.PLAN_ENTERPRISE

# The ONLY plans a Personal member can hold as a paid effective plan. Enterprise
# is a separate product and is deliberately excluded; anything else (unknown,
# malformed, or a non-Personal code) is never a Personal paid plan (fail closed).
PERSONAL_PAID_PLANS: frozenset[str] = frozenset(
    {_plans.PLAN_STARTER, _plans.PLAN_PRO, _plans.PLAN_ADVANCED}
)


def parse_registered_at(value: Any) -> Optional[datetime]:
    """Parse an account registration timestamp (accounts.created_at) to a
    timezone-aware datetime. Accepts a datetime or an ISO-8601 string; returns
    None when missing/unparseable (caller must NOT fabricate a trial)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return None


def personal_paid_plan(subscription: Any) -> Optional[str]:
    """The paid Personal plan from a billing subscription, or None (fail closed).

    Only a LIVE subscription whose plan is in the explicit Personal paid allowlist
    (starter/pro/advanced) yields a paid Personal plan. Free, Enterprise, unknown,
    or malformed codes never become a Personal paid plan."""
    if subscription is None:
        return None
    try:
        live = bool(subscription.is_live)
    except Exception:  # noqa: BLE001 - any malformed subscription => not paid
        return None
    code = getattr(subscription, "plan_code", None)
    if live and isinstance(code, str) and code in PERSONAL_PAID_PLANS:
        return code
    return None


def effective_personal_plan(
    *, registered_at: Any, subscription: Any, now: Optional[datetime] = None
) -> str:
    """The canonical effective Personal plan (paid wins, then active trial, else
    free). `registered_at` may be a datetime, an ISO string, or None."""
    moment = now or datetime.now(timezone.utc)
    reg = parse_registered_at(registered_at)
    plan = _trial.effective_plan(moment, registered_at=reg, paid_plan=personal_paid_plan(subscription))
    # Defence in depth: Enterprise must never surface as a Personal effective plan.
    return _plans.PLAN_FREE if plan == ENTERPRISE else plan


def personal_trial_status(
    *, registered_at: Any, subscription: Any, now: Optional[datetime] = None
) -> dict:
    """The canonical trial status dict (trial_active / days_remaining /
    trial_started_at / trial_ends_at, or PAID/FREE) for the Personal member."""
    moment = now or datetime.now(timezone.utc)
    reg = parse_registered_at(registered_at)
    return _trial.trial_status(moment, registered_at=reg, paid_plan=personal_paid_plan(subscription))


def personal_entitlement_resolution(
    *, registered_at: Any, subscription: Any, now: Optional[datetime] = None
) -> EntitlementResolution:
    """Entitlements for the canonical effective Personal plan. The reported
    subscription_status stays the raw billing status (billing truth preserved);
    only the effective plan that drives entitlements is trial-aware."""
    plan = effective_personal_plan(registered_at=registered_at, subscription=subscription, now=now)
    status = getattr(subscription, "status", STATUS_INACTIVE) if subscription is not None else STATUS_INACTIVE
    return resolve_entitlements_for_plan(plan, subscription_status=status)
