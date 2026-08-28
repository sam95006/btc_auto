"""Centralized billing plan catalog.

Plans are identified by a stable internal ``code`` — never by price. Pricing and
display names are replaceable metadata and MUST NOT be used as the identity of a
plan or as the basis for authorization. Feature access (BILLING-2) will map a
plan ``code`` to entitlements; it must never inspect price or provider ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# Stable internal plan identifiers. These are contract-stable; display names and
# pricing may change freely without affecting authorization.
PLAN_FREE = "free"
PLAN_STARTER = "starter"
PLAN_PRO = "pro"
PLAN_ADVANCED = "advanced"
PLAN_ENTERPRISE = "enterprise"

DEFAULT_PLAN_CODE = PLAN_FREE


@dataclass(frozen=True)
class Plan:
    """A logical plan. Price is intentionally optional metadata, not identity."""

    code: str
    display_name: str
    description: str = ""
    billing_interval: Optional[str] = None  # e.g. "month" | "year" | None (free)
    price_amount: Optional[int] = None  # minor units; metadata only, replaceable
    currency: Optional[str] = None
    active: bool = True
    sort_order: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "display_name": self.display_name,
            "description": self.description,
            "billing_interval": self.billing_interval,
            "price_amount": self.price_amount,
            "currency": self.currency,
            "active": self.active,
            "sort_order": self.sort_order,
        }


# The catalog is defined in code (not a DB table) for BILLING-1 to avoid
# overbuilding pricing. Display names/prices here are placeholders and are NOT
# authoritative branding or commercial pricing.
_PLAN_CATALOG: tuple[Plan, ...] = (
    Plan(code=PLAN_FREE, display_name="Free", description="Default non-paid tier.", sort_order=0),
    Plan(code=PLAN_STARTER, display_name="Starter", billing_interval="month", sort_order=1),
    Plan(code=PLAN_PRO, display_name="Pro", billing_interval="month", sort_order=2),
    Plan(code=PLAN_ADVANCED, display_name="Advanced", billing_interval="month", sort_order=3),
    Plan(code=PLAN_ENTERPRISE, display_name="Enterprise", billing_interval="month", sort_order=4),
)

_PLANS_BY_CODE: dict[str, Plan] = {plan.code: plan for plan in _PLAN_CATALOG}

CANONICAL_PLAN_CODES: tuple[str, ...] = tuple(plan.code for plan in _PLAN_CATALOG)


def list_plans(*, include_inactive: bool = False) -> list[Plan]:
    plans = [p for p in _PLAN_CATALOG if include_inactive or p.active]
    return sorted(plans, key=lambda p: p.sort_order)


def get_plan(code: Optional[str]) -> Optional[Plan]:
    if not code:
        return None
    return _PLANS_BY_CODE.get(str(code).strip().lower())


def is_valid_plan_code(code: Optional[str]) -> bool:
    return get_plan(code) is not None


def normalize_plan_code(code: Optional[str]) -> str:
    """Return a valid plan code, falling back to the default (never a paid plan)
    for unknown/empty input. The backend never trusts a client-supplied plan."""
    plan = get_plan(code)
    return plan.code if plan is not None else DEFAULT_PLAN_CODE
