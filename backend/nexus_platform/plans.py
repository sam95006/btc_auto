"""Canonical commercial plan + trial contract (NEXUS-EXPERIENCE-1A).

Plan identity is the stable ``code`` (aligned with nexus_billing). Pricing is
metadata (USD minor units) and MUST NOT drive authorization. Annual pricing is a
fixed 20% discount on 12 months. Every newly registered Personal user starts a
30-day STARTER trial from the exact registration timestamp; on expiry they use
paid entitlements if any, else FREE. No auto-charge without explicit consent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

PLAN_FREE = "free"
PLAN_STARTER = "starter"
PLAN_PRO = "pro"
PLAN_ADVANCED = "advanced"
PLAN_ENTERPRISE = "enterprise"

CANONICAL_PLAN_CODES = (PLAN_FREE, PLAN_STARTER, PLAN_PRO, PLAN_ADVANCED, PLAN_ENTERPRISE)

# Fixed annual discount. Annual = round(monthly * 12 * (1 - ANNUAL_DISCOUNT), 2).
ANNUAL_DISCOUNT = 0.20

# Trial contract.
STARTER_TRIAL_CODE = "STARTER_TRIAL_30D"
TRIAL_DAYS = 30


@dataclass(frozen=True)
class Plan:
    code: str
    display_name: str
    monthly_usd_cents: Optional[int]      # None => custom / not self-serve
    annual_usd_cents: Optional[int]        # None => custom / free
    trial_grants: Optional[str] = None     # trial plan a NEW user receives, if any
    contact_sales: bool = False
    sort_order: int = 0

    def to_public_dict(self) -> dict:
        return {
            "code": self.code,
            "display_name": self.display_name,
            "monthly_usd_cents": self.monthly_usd_cents,
            "annual_usd_cents": self.annual_usd_cents,
            "monthly_usd": None if self.monthly_usd_cents is None else round(self.monthly_usd_cents / 100, 2),
            "annual_usd": None if self.annual_usd_cents is None else round(self.annual_usd_cents / 100, 2),
            "annual_discount_pct": round(ANNUAL_DISCOUNT * 100),
            "contact_sales": self.contact_sales,
            "sort_order": self.sort_order,
        }


def _annual_cents(monthly_cents: int) -> int:
    return round(monthly_cents * 12 * (1 - ANNUAL_DISCOUNT))


PLAN_CATALOG: tuple[Plan, ...] = (
    Plan(PLAN_FREE, "Free", monthly_usd_cents=0, annual_usd_cents=0, sort_order=0),
    Plan(PLAN_STARTER, "Starter", monthly_usd_cents=1900, annual_usd_cents=_annual_cents(1900), sort_order=1),
    Plan(PLAN_PRO, "Pro", monthly_usd_cents=3900, annual_usd_cents=_annual_cents(3900), sort_order=2),
    Plan(PLAN_ADVANCED, "Advanced", monthly_usd_cents=7900, annual_usd_cents=_annual_cents(7900), sort_order=3),
    Plan(PLAN_ENTERPRISE, "Enterprise", monthly_usd_cents=None, annual_usd_cents=None, contact_sales=True, sort_order=4),
)

_BY_CODE = {p.code: p for p in PLAN_CATALOG}


def get_plan(code: Optional[str]) -> Optional[Plan]:
    return _BY_CODE.get((code or "").strip().lower())


def list_plans() -> list[Plan]:
    return sorted(PLAN_CATALOG, key=lambda p: p.sort_order)


def public_catalog() -> dict:
    """Backend-owned plan catalog for the pricing surface (Corporate)."""
    return {
        "currency": "USD",
        "annual_discount_pct": round(ANNUAL_DISCOUNT * 100),
        "trial": {"code": STARTER_TRIAL_CODE, "grants": PLAN_STARTER, "days": TRIAL_DAYS,
                  "auto_charge": False, "on_expiry": "paid_else_free"},
        "plans": [p.to_public_dict() for p in list_plans()],
    }
