"""Count member-facing execution-control exposures (must be 0)."""
from __future__ import annotations

from typing import Any, Iterable, Optional

from backend.nexus_public_subscription_boundary.constants import (
    EXECUTION_CONTROL_MARKERS,
    MEMBER_BUYABLE_PRODUCT_IDS,
    MEMBER_FORBIDDEN_PRODUCT_IDS,
)
from backend.nexus_public_subscription_boundary.entitlements import TIER_PRODUCTS
from backend.nexus_public_subscription_boundary.hard_bans import normalize_product_id


def _hits_in(ids: Iterable[str]) -> list[str]:
    found: list[str] = []
    for raw in ids:
        pid = normalize_product_id(raw)
        if pid in EXECUTION_CONTROL_MARKERS:
            found.append(pid)
    return found


def count_member_execution_controls(
    *,
    entitled_products: Optional[Iterable[str]] = None,
    buyable_catalog: Optional[Iterable[str]] = None,
    nav_destinations: Optional[Iterable[str]] = None,
    audit_granted_products: Optional[Iterable[str]] = None,
    extra_surfaces: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """Return member_execution_control_count across subscription surfaces.

    A hit is any forbidden/execution product appearing as member-buyable,
    entitled, navigable, or audit-granted.
    """
    survivors: list[dict[str, str]] = []

    def _absorb(surface: str, ids: Optional[Iterable[str]]) -> None:
        if not ids:
            return
        for hit in _hits_in(ids):
            survivors.append({"surface": surface, "product_id": hit})

    # Default surfaces from the sealed product matrix.
    _absorb("tier_products", (p for products in TIER_PRODUCTS.values() for p in products))
    _absorb("buyable_catalog", buyable_catalog or MEMBER_BUYABLE_PRODUCT_IDS)
    _absorb("entitled_products", entitled_products)
    _absorb("nav_destinations", nav_destinations)
    _absorb("audit_granted", audit_granted_products)
    _absorb("extra_surfaces", extra_surfaces)

    # Explicit: forbidden products must never appear in buyable catalog.
    for pid in MEMBER_FORBIDDEN_PRODUCT_IDS:
        if buyable_catalog is not None and pid in set(buyable_catalog):
            survivors.append({"surface": "buyable_catalog", "product_id": pid})

    # Deduplicate by surface+product.
    uniq: dict[tuple[str, str], dict[str, str]] = {}
    for row in survivors:
        uniq[(row["surface"], row["product_id"])] = row
    survivors = list(uniq.values())

    return {
        "member_execution_control_count": len(survivors),
        "survivors": survivors,
        "status": "PASS" if not survivors else "FAIL",
    }
