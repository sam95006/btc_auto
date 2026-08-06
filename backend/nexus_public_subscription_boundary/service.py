"""Facade service for PUB17-D subscription product boundary."""
from __future__ import annotations

from typing import Any, Optional

from backend.nexus_public_subscription_boundary.audit import (
    SubscriptionAuditLog,
    get_default_audit_log,
)
from backend.nexus_public_subscription_boundary.authorization import (
    authorize_member_product_access,
)
from backend.nexus_public_subscription_boundary.constants import (
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    MEMBER_BUYABLE_PRODUCT_IDS,
    MEMBER_FORBIDDEN_PRODUCT_IDS,
    PACKAGE,
    SCHEMA_VERSION,
)
from backend.nexus_public_subscription_boundary.dto import (
    build_catalog_dto,
    MemberSubscriptionAccessDto,
)
from backend.nexus_public_subscription_boundary.entitlements import (
    entitlement_product_snapshot,
    grant_product_manual,
    products_for_tier,
)
from backend.nexus_public_subscription_boundary.execution_control import (
    count_member_execution_controls,
)
from backend.nexus_public_subscription_boundary.hard_bans import (
    HardBanViolation,
    assert_env_hard_bans,
    hard_ban_snapshot,
    is_forbidden_product,
)
from backend.nexus_public_subscription_boundary.nav import (
    FORBIDDEN_MOBILE_NAV_ROUTES,
    FORBIDDEN_WEB_NAV_PATHS,
    member_mobile_nav_snapshot,
    member_web_nav_snapshot,
)


class SubscriptionBoundaryService:
    def __init__(self, audit: Optional[SubscriptionAuditLog] = None) -> None:
        assert_env_hard_bans()
        self.audit = audit or get_default_audit_log()

    def foundation_status(self) -> dict[str, Any]:
        catalog = build_catalog_dto().to_dict()
        count = count_member_execution_controls(
            buyable_catalog=MEMBER_BUYABLE_PRODUCT_IDS,
            entitled_products=MEMBER_BUYABLE_PRODUCT_IDS,
            nav_destinations=list(MEMBER_BUYABLE_PRODUCT_IDS),
            audit_granted_products=[],
        )
        return {
            "lane": LANE,
            "lane_name": LANE_NAME,
            "package": PACKAGE,
            "schema_version": SCHEMA_VERSION,
            "branch": BRANCH,
            "base_commit": BASE_COMMIT,
            "hard_bans": sorted(HARD_BANS),
            "hard_ban_snapshot": hard_ban_snapshot(),
            "catalog": catalog,
            "member_buyable_products": sorted(MEMBER_BUYABLE_PRODUCT_IDS),
            "member_forbidden_products": sorted(MEMBER_FORBIDDEN_PRODUCT_IDS),
            "member_execution_control_count": count["member_execution_control_count"],
            "execution_control_scan": count,
            "live_billing_enabled": False,
            "pr26_merged": False,
            "pr27_merged": False,
            "forbidden_web_nav_paths": sorted(FORBIDDEN_WEB_NAV_PATHS),
            "forbidden_mobile_nav_routes": sorted(FORBIDDEN_MOBILE_NAV_ROUTES),
        }

    def catalog(self) -> dict[str, Any]:
        return build_catalog_dto().to_dict()

    def access_for(self, *, account_id: str, tier: str) -> dict[str, Any]:
        entitled = products_for_tier(tier)
        denied = MEMBER_FORBIDDEN_PRODUCT_IDS
        dto = MemberSubscriptionAccessDto(
            account_id=account_id,
            tier=tier,
            entitled_products=tuple(sorted(entitled)),
            denied_products=tuple(sorted(denied)),
            member_execution_control_count=0,
        )
        self.audit.record(
            action="access_snapshot",
            result="ok",
            account_id=account_id,
            metadata={"tier": tier, "entitled": sorted(entitled)},
        )
        return dto.to_dict()

    def authorize(
        self, *, account_id: str, product_id: str, action: str = "read"
    ) -> dict[str, Any]:
        try:
            result = authorize_member_product_access(
                account_id=account_id, product_id=product_id, action=action
            )
            self.audit.record(
                action=f"authorize_{action}",
                result="authorized",
                account_id=account_id,
                product_id=product_id,
            )
            return {"ok": True, **result}
        except HardBanViolation as exc:
            self.audit.record(
                action=f"authorize_{action}",
                result="denied",
                account_id=account_id,
                product_id=product_id,
                metadata={"error": str(exc)},
            )
            raise

    def grant_manual(
        self, *, tier: str, product_id: str, actor: str, account_id: str
    ) -> dict[str, Any]:
        if is_forbidden_product(product_id):
            self.audit.record(
                action="grant_manual",
                result="denied",
                account_id=account_id,
                product_id=product_id,
            )
            raise HardBanViolation(
                f"HARD BAN: members must never buy/grant product {product_id!r}"
            )
        result = grant_product_manual(tier=tier, product_id=product_id, actor=actor)
        self.audit.record(
            action="grant_manual",
            result="granted",
            account_id=account_id,
            product_id=product_id,
            metadata={"tier": tier, "actor": actor},
        )
        return result

    def entitlement_snapshot(self, tier: str) -> dict[str, Any]:
        return entitlement_product_snapshot(tier)

    def audit_events(self, account_id: Optional[str] = None) -> list[dict[str, Any]]:
        return self.audit.list_events(account_id=account_id)

    def web_nav_check(self, paths: list[str]) -> dict[str, Any]:
        return member_web_nav_snapshot(paths)

    def mobile_nav_check(self, routes: list[str]) -> dict[str, Any]:
        return member_mobile_nav_snapshot(routes)

    def execution_control_count(self) -> dict[str, Any]:
        granted = [
            e["product_id"]
            for e in self.audit.list_events()
            if e.get("result") in {"granted", "authorized"} and e.get("product_id")
        ]
        return count_member_execution_controls(
            buyable_catalog=MEMBER_BUYABLE_PRODUCT_IDS,
            entitled_products=MEMBER_BUYABLE_PRODUCT_IDS,
            audit_granted_products=granted,
        )
