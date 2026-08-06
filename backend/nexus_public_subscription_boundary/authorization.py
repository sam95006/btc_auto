"""Authorization helpers for member subscription products."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_subscription_boundary.constants import (
    MEMBER_BUYABLE_PRODUCT_IDS,
    MEMBER_FORBIDDEN_PRODUCT_IDS,
)
from backend.nexus_public_subscription_boundary.hard_bans import (
    HardBanViolation,
    is_buyable_product,
    is_forbidden_product,
    normalize_product_id,
    refuse_forbidden_product,
)


def authorize_member_product_access(
    *,
    account_id: str,
    product_id: str,
    action: str = "read",
) -> dict[str, Any]:
    """Authorize member access to a product.

    Forbidden products are always denied (even for admins on the public realm).
    Buyable products may be read; purchase attempts never enable live billing.
    """
    pid = normalize_product_id(product_id)
    if not account_id:
        raise HardBanViolation("HARD BAN: account_id required for product authorization")
    if is_forbidden_product(pid):
        refuse_forbidden_product(pid)
    if action in {"buy", "purchase", "subscribe", "grant"}:
        if not is_buyable_product(pid):
            raise HardBanViolation(
                f"HARD BAN: members may not {action} product {product_id!r}"
            )
        # Non-production: catalog allow only — no payment collection.
        return {
            "authorized": True,
            "account_id": account_id,
            "product_id": pid,
            "action": action,
            "live_billing": False,
            "assignment_mode": "manual_non_production",
            "execution_controls": False,
        }
    if action in {"read", "view", "list"}:
        if pid in MEMBER_BUYABLE_PRODUCT_IDS or pid in {
            "catalog",
            "membership",
            "home",
        }:
            return {
                "authorized": True,
                "account_id": account_id,
                "product_id": pid,
                "action": action,
                "execution_controls": False,
            }
        raise HardBanViolation(f"entitlement denied: product={product_id!r}")
    raise HardBanViolation(f"HARD BAN: unsupported product action {action!r}")


def assert_member_cannot_buy_forbidden() -> dict[str, Any]:
    denied: list[str] = []
    for pid in sorted(MEMBER_FORBIDDEN_PRODUCT_IDS):
        try:
            authorize_member_product_access(
                account_id="acct_probe", product_id=pid, action="buy"
            )
            raise HardBanViolation(f"forbidden product {pid} was buyable")
        except HardBanViolation:
            denied.append(pid)
    return {
        "ok": True,
        "denied_products": denied,
        "member_execution_controls": False,
    }
