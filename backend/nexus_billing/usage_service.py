"""Central usage resolver + quota enforcement service for BILLING-6.

Composes with (never replaces) BILLING-2 entitlements. The effective plan comes
from the BILLING-1 subscription via the BILLING-2 resolver, so a downgrade /
past_due / canceled / expired subscription safely falls back to the free policy.

Fail-closed: any missing/invalid/unavailable condition denies a metered action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.nexus_billing.entitlements import (
    PLAN_TIER_ORDER,
    effective_plan_code,
    plan_has_entitlement,
)
from backend.nexus_billing.usage_policy import (
    QUOTA_CATALOG,
    TYPE_CONSUMABLE,
    get_quota_spec,
    is_valid_quota,
    plan_quota_codes,
    quota_limit,
)
from backend.nexus_billing.usage_windows import window_reset_at, window_start_for


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


@dataclass(frozen=True)
class UsageDecision:
    allowed: bool
    quota_code: str
    limit: int
    used: int
    remaining: int
    reason: Optional[str] = None
    reset_at: Optional[datetime] = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "quota_code": self.quota_code,
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "reset_at": _iso(self.reset_at),
        }


class UsageService:
    def __init__(self, *, usage_repo, subscription_repo, clock: Callable[[], datetime] = _utcnow) -> None:
        self._usage = usage_repo
        self._subs = subscription_repo
        self._clock = clock

    def _effective_plan(self, account_id: str) -> str:
        subscription = self._subs.get_by_account(account_id)
        return effective_plan_code(subscription)

    def _plan_for(self, account_id: str, effective_plan: Optional[str]) -> Optional[str]:
        """Resolve the plan whose policy applies. Default is billing-only. A caller
        MAY pass an explicit canonical effective plan (e.g. the trial-aware Personal
        access plan); it is validated fail-closed — an unknown/malformed override
        returns None (the caller must deny / fall back to the free floor), never a
        silent grant."""
        if effective_plan is None:
            return self._effective_plan(account_id)
        return effective_plan if effective_plan in PLAN_TIER_ORDER else None

    def resolve_usage(self, account_id: str, *, effective_plan: Optional[str] = None) -> dict[str, Any]:
        # Display path: an invalid override falls back to the free floor (never
        # over-grants), while a valid override (or None) resolves normally.
        plan = self._plan_for(account_id, effective_plan) or "free"
        now = self._clock()
        quotas: list[dict[str, Any]] = []
        for code in plan_quota_codes(plan):
            spec = QUOTA_CATALOG[code]
            limit = quota_limit(plan, code) or 0
            # Consistency: a quota is only presented as usable when the effective
            # plan actually holds the gating entitlement (BILLING-2). Otherwise it
            # is shown as unavailable rather than as a usable allowance.
            entitled = plan_has_entitlement(plan, spec.entitlement)
            if spec.quota_type == TYPE_CONSUMABLE:
                window_start = window_start_for(spec.window, now)
                used = self._usage.get_used(account_id, code, spec.window, window_start)
                reset_at = window_reset_at(spec.window, now)
            else:
                # Capacity limits have no consumption ledger in BILLING-6.
                used = 0
                reset_at = None
            quotas.append(
                {
                    "quota_code": code,
                    "label": spec.label,
                    "quota_type": spec.quota_type,
                    "window": spec.window,
                    "entitled": entitled,
                    "limit": limit if entitled else 0,
                    "used": used,
                    "remaining": max(0, (limit if entitled else 0) - used),
                    "reset_at": _iso(reset_at),
                }
            )
        return {"effective_plan_code": plan, "quotas": quotas}

    def consume(
        self, *, account_id: str, quota_code: str, amount: int = 1, idempotency_key: str,
        effective_plan: Optional[str] = None,
    ) -> UsageDecision:
        # Fail closed on any invalid/unknown input.
        if not is_valid_quota(quota_code):
            return UsageDecision(False, str(quota_code), 0, 0, 0, reason="unknown_quota")
        if not isinstance(amount, int) or amount <= 0:
            return UsageDecision(False, quota_code, 0, 0, 0, reason="invalid_amount")
        if not idempotency_key:
            return UsageDecision(False, quota_code, 0, 0, 0, reason="missing_idempotency_key")

        spec = get_quota_spec(quota_code)
        assert spec is not None
        if spec.quota_type != TYPE_CONSUMABLE:
            return UsageDecision(False, quota_code, 0, 0, 0, reason="not_consumable")

        plan = self._plan_for(account_id, effective_plan)
        if plan is None:
            # Fail closed: an explicit but unknown/malformed effective-plan override
            # never grants a metered action.
            return UsageDecision(False, quota_code, 0, 0, 0, reason="invalid_effective_plan")
        # Entitlement AND Quota: without the gating entitlement there is no usable
        # quota, regardless of any numeric limit.
        if not plan_has_entitlement(plan, spec.entitlement):
            return UsageDecision(False, quota_code, 0, 0, 0, reason="entitlement_required")
        limit = quota_limit(plan, quota_code)
        if limit is None or limit <= 0:
            # No paid allowance under the effective plan.
            return UsageDecision(False, quota_code, int(limit or 0), 0, 0, reason="no_quota")

        now = self._clock()
        window_start = window_start_for(spec.window, now)
        try:
            allowed, used = self._usage.consume(
                account_id=account_id,
                quota_code=quota_code,
                window_type=spec.window,
                window_start=window_start,
                amount=amount,
                limit=limit,
                idempotency_key=idempotency_key,
            )
        except Exception:  # noqa: BLE001 - fail closed on any metering error
            return UsageDecision(False, quota_code, limit, 0, 0, reason="usage_unavailable")

        remaining = max(0, limit - used)
        reset_at = window_reset_at(spec.window, now)
        return UsageDecision(
            allowed=allowed,
            quota_code=quota_code,
            limit=limit,
            used=used,
            remaining=remaining,
            reason=None if allowed else "quota_exceeded",
            reset_at=reset_at,
        )
