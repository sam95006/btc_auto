"""Hard-ban enforcement for PUB17-D subscription product boundary."""
from __future__ import annotations

import os
from typing import Any, Iterable

from backend.nexus_public_subscription_boundary.constants import (
    BILLING_PROVIDER,
    EXECUTION_CONTROL_MARKERS,
    FORBIDDEN_PRODUCT_ALIASES,
    HARD_BANS,
    LIVE_BILLING_ENABLED,
    MEMBER_BUYABLE_PRODUCT_IDS,
    MEMBER_FORBIDDEN_PRODUCT_IDS,
)


class HardBanViolation(RuntimeError):
    """Raised when a PUB17-D subscription product hard ban would be violated."""


def normalize_product_id(product_id: str) -> str:
    return str(product_id or "").strip().lower().replace("-", "_").replace(" ", "_")


def is_forbidden_product(product_id: str) -> bool:
    pid = normalize_product_id(product_id)
    return (
        pid in MEMBER_FORBIDDEN_PRODUCT_IDS
        or pid in FORBIDDEN_PRODUCT_ALIASES
        or pid in EXECUTION_CONTROL_MARKERS
    )


def is_buyable_product(product_id: str) -> bool:
    pid = normalize_product_id(product_id)
    if is_forbidden_product(pid):
        return False
    return pid in MEMBER_BUYABLE_PRODUCT_IDS


def refuse_forbidden_product(product_id: str) -> None:
    if is_forbidden_product(product_id):
        raise HardBanViolation(
            f"HARD BAN: members must never buy/grant product {product_id!r}"
        )


def refuse_member_execution_controls() -> None:
    raise HardBanViolation(
        "HARD BAN: members must never receive execution controls via subscription"
    )


def refuse_live_billing() -> None:
    raise HardBanViolation("HARD BAN: live billing / production billing claims refused")


def assert_env_hard_bans() -> None:
    if os.environ.get("NEXUS_PUBLIC_LIVE_BILLING", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        refuse_live_billing()
    if LIVE_BILLING_ENABLED or BILLING_PROVIDER != "NONE_NON_PRODUCTION":
        refuse_live_billing()


def assert_no_forbidden_in_iterable(items: Iterable[str], *, context: str) -> None:
    bad = sorted({normalize_product_id(i) for i in items} & set(EXECUTION_CONTROL_MARKERS))
    if bad:
        raise HardBanViolation(
            f"HARD BAN: {context} exposes member execution controls: {bad}"
        )


def assert_buyable_catalog_clean(buyable_ids: Iterable[str]) -> None:
    for pid in buyable_ids:
        refuse_forbidden_product(pid)
        if normalize_product_id(pid) not in MEMBER_BUYABLE_PRODUCT_IDS:
            raise HardBanViolation(
                f"HARD BAN: unknown member-buyable product {pid!r}"
            )


def hard_ban_snapshot() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "live_billing_enabled": False,
        "billing_provider": BILLING_PROVIDER,
        "member_forbidden_products": sorted(MEMBER_FORBIDDEN_PRODUCT_IDS),
        "member_buyable_products": sorted(MEMBER_BUYABLE_PRODUCT_IDS),
        "member_execution_controls_allowed": False,
    }
