"""DTO for member subscription product catalog and access (PUB17-D)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_public_subscription_boundary.constants import (
    BILLING_PROVIDER,
    MEMBER_BUYABLE_PRODUCTS,
    MEMBER_FORBIDDEN_PRODUCTS,
    SCHEMA_VERSION,
)
from backend.nexus_public_subscription_boundary.hard_bans import (
    HardBanViolation,
    assert_buyable_catalog_clean,
    assert_no_forbidden_in_iterable,
)


@dataclass(frozen=True)
class ProductDto:
    product_id: str
    label: str
    member_buyable: bool
    execution_control: bool = False


@dataclass(frozen=True)
class SubscriptionCatalogDto:
    schema_version: str = SCHEMA_VERSION
    buyable: tuple[ProductDto, ...] = field(default_factory=tuple)
    not_for_sale: tuple[ProductDto, ...] = field(default_factory=tuple)
    live_billing_enabled: bool = False
    billing_provider: str = BILLING_PROVIDER
    member_execution_control_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "buyable": [asdict(p) for p in self.buyable],
            "not_for_sale": [asdict(p) for p in self.not_for_sale],
            "live_billing_enabled": False,
            "billing_provider": self.billing_provider,
            "member_execution_control_count": self.member_execution_control_count,
            "execution_controls": False,
        }
        validate_catalog_payload(payload)
        return payload


@dataclass(frozen=True)
class MemberSubscriptionAccessDto:
    account_id: str
    tier: str
    entitled_products: tuple[str, ...]
    denied_products: tuple[str, ...]
    live_billing_enabled: bool = False
    member_execution_control_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "account_id": self.account_id,
            "tier": self.tier,
            "entitled_products": list(self.entitled_products),
            "denied_products": list(self.denied_products),
            "live_billing_enabled": False,
            "member_execution_control_count": self.member_execution_control_count,
            "execution_controls": False,
        }
        assert_no_forbidden_in_iterable(
            self.entitled_products, context="MemberSubscriptionAccessDto.entitled"
        )
        return payload


def build_catalog_dto() -> SubscriptionCatalogDto:
    buyable = tuple(
        ProductDto(product_id=pid, label=label, member_buyable=True, execution_control=False)
        for pid, label in MEMBER_BUYABLE_PRODUCTS
    )
    not_for_sale = tuple(
        ProductDto(
            product_id=pid,
            label=label,
            member_buyable=False,
            execution_control=True,
        )
        for pid, label in MEMBER_FORBIDDEN_PRODUCTS
    )
    dto = SubscriptionCatalogDto(
        buyable=buyable,
        not_for_sale=not_for_sale,
        member_execution_control_count=0,
    )
    assert_buyable_catalog_clean(p.product_id for p in buyable)
    return dto


def validate_catalog_payload(payload: dict[str, Any]) -> None:
    buyable = payload.get("buyable") or []
    ids = []
    for item in buyable:
        if isinstance(item, dict):
            pid = str(item.get("product_id", ""))
            if item.get("member_buyable") is False:
                raise HardBanViolation(
                    f"HARD BAN: buyable list contains non-buyable {pid!r}"
                )
            if item.get("execution_control") is True:
                raise HardBanViolation(
                    f"HARD BAN: buyable list marks execution_control for {pid!r}"
                )
            ids.append(pid)
        else:
            ids.append(str(item))
    assert_buyable_catalog_clean(ids)
    assert_no_forbidden_in_iterable(ids, context="catalog.buyable")
    if int(payload.get("member_execution_control_count", 0) or 0) != 0:
        raise HardBanViolation(
            "HARD BAN: member_execution_control_count must be 0 on catalog DTO"
        )
