"""NEXUS Phase 6.5 — Membership / entitlement foundation (no billing).

Production / Zeabur default = ANONYMOUS (fail-closed).
FOUNDER only via explicit verified identity or local test mode.
Never trust client headers / query / localStorage for Founder.
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# Product / identity tiers (Gate B / J)
class PlanTier(str, Enum):
    ANONYMOUS = "ANONYMOUS"
    FREE = "FREE"
    PRO = "PRO"
    ADVANCED = "ADVANCED"
    ELITE = "ELITE"
    ENTERPRISE = "ENTERPRISE"
    INTERNAL_ADMIN = "INTERNAL_ADMIN"
    FOUNDER = "FOUNDER"


# Entitlement keys (Gate J)
ENTITLEMENT_KEYS = frozenset({
    "market.delayed",
    "market.realtime",
    "market.chart.basic",
    "market.chart.advanced",
    "market.orderflow",
    "market.derivatives",
    "market.alerts",
    "market.watchlist",
    "ai.summary",
    "ai.evidence.basic",
    "ai.evidence.full",
    "performance.basic",
    "performance.advanced",
    "replay.view",
    "api.access",
    "enterprise.audit",
    "enterprise.model_governance",
    "enterprise.custom_risk",
    "founder.autonomous_execution",
    "founder.strategy_config",
    "founder.production_control",
})

_TIER_ENTITLEMENTS: dict[PlanTier, frozenset[str]] = {
    PlanTier.ANONYMOUS: frozenset({"market.delayed", "market.chart.basic"}),
    PlanTier.FREE: frozenset({"market.delayed", "market.chart.basic", "ai.summary"}),
    PlanTier.PRO: frozenset({
        "market.delayed", "market.realtime", "market.chart.basic", "market.chart.advanced",
        "market.watchlist", "ai.summary", "ai.evidence.basic", "performance.basic",
    }),
    PlanTier.ADVANCED: frozenset({
        "market.realtime", "market.chart.advanced", "market.orderflow", "market.derivatives",
        "market.alerts", "ai.evidence.full", "performance.basic", "replay.view",
    }),
    PlanTier.ELITE: frozenset({
        "market.realtime", "market.chart.advanced", "market.orderflow", "market.derivatives",
        "market.alerts", "ai.evidence.full", "performance.advanced", "replay.view", "api.access",
    }),
    PlanTier.ENTERPRISE: frozenset({
        "market.realtime", "market.chart.advanced", "market.orderflow", "market.derivatives",
        "ai.evidence.full", "performance.advanced", "replay.view", "api.access",
        "enterprise.audit", "enterprise.model_governance", "enterprise.custom_risk",
    }),
    PlanTier.INTERNAL_ADMIN: frozenset({
        "market.realtime", "market.chart.advanced", "market.orderflow", "market.derivatives",
        "ai.evidence.full", "performance.advanced", "replay.view", "api.access",
        "enterprise.audit", "enterprise.model_governance", "enterprise.custom_risk",
    }),
    PlanTier.FOUNDER: ENTITLEMENT_KEYS,
}

_FOUNDER_ONLY = frozenset({
    "founder.autonomous_execution",
    "founder.strategy_config",
    "founder.production_control",
})


@dataclass
class ActorContext:
    user_id: str = "anonymous"
    organization_id: Optional[str] = None
    tier: PlanTier = PlanTier.ANONYMOUS
    roles: list[str] = field(default_factory=lambda: ["ANONYMOUS"])
    request_id: Optional[str] = None
    identity_source: str = "default_anonymous"


def is_production_like() -> bool:
    """Zeabur / production-like hosts are fail-closed to ANONYMOUS."""
    if str(os.environ.get("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "")).strip().lower() in (
        "1", "true", "yes", "on",
    ):
        return True
    if any(os.environ.get(k) for k in ("ZEABUR", "ZEABUR_SERVICE_ID", "ZEABUR_PROJECT_ID", "ZEABUR_ENVIRONMENT")):
        return True
    env = (os.environ.get("NEXUS_ENV") or os.environ.get("FLASK_ENV") or "").strip().lower()
    return env in ("production", "prod", "zeabur")


def is_local_test_mode() -> bool:
    """Explicit local/test mode only — never inferred from client headers."""
    if is_production_like():
        return False
    return str(os.environ.get("NEXUS_ENTITLEMENT_TEST_MODE", "")).strip().lower() in (
        "1", "true", "yes", "on",
    )


def founder_routes_enabled() -> bool:
    """Live Founder routes stay disabled until verified auth exists.

    Enable only with explicit local test mode or NEXUS_FOUNDER_ROUTES_ENABLED=1
    outside production-like environments.
    """
    if is_production_like():
        return False
    if is_local_test_mode():
        return True
    return str(os.environ.get("NEXUS_FOUNDER_ROUTES_ENABLED", "")).strip().lower() in (
        "1", "true", "yes", "on",
    )


def resolve_actor_context(*, request_headers: Optional[dict[str, str]] = None) -> ActorContext:
    """Resolve caller context.

    Rules:
    - Production/Zeabur → ANONYMOUS unless future verified auth (not implemented).
    - Client X-Nexus-Role / ?tier= / localStorage MUST be ignored.
    - Local test mode may set NEXUS_MEMBERSHIP_TIER=FOUNDER explicitly.
    """
    # Ignore any client-supplied identity (headers/query) — never trust.
    _ = request_headers  # documented reject surface

    if is_production_like():
        return ActorContext(
            user_id="anonymous",
            tier=PlanTier.ANONYMOUS,
            roles=["ANONYMOUS"],
            identity_source="production_default_anonymous",
        )

    if is_local_test_mode():
        tier_raw = (os.environ.get("NEXUS_MEMBERSHIP_TIER") or "FOUNDER").strip().upper()
        try:
            tier = PlanTier(tier_raw)
        except ValueError:
            tier = PlanTier.ANONYMOUS
        uid = os.environ.get("NEXUS_OPERATOR_USER_ID") or "local-test-operator"
        org = os.environ.get("NEXUS_ORGANIZATION_ID")
        roles = [tier.value]
        if tier == PlanTier.FOUNDER:
            roles = ["FOUNDER", "OPERATOR"]
        return ActorContext(
            user_id=uid,
            organization_id=org,
            tier=tier,
            roles=roles,
            identity_source="local_test_mode",
        )

    # Non-production, non-test: still anonymous until real auth exists
    return ActorContext(
        user_id="anonymous",
        tier=PlanTier.ANONYMOUS,
        roles=["ANONYMOUS"],
        identity_source="default_anonymous",
    )


def has_entitlement(actor: ActorContext, key: str) -> bool:
    if key not in ENTITLEMENT_KEYS:
        return False
    if key in _FOUNDER_ONLY:
        if actor.tier != PlanTier.FOUNDER and "FOUNDER" not in actor.roles:
            return False
        if actor.identity_source not in ("local_test_mode",):
            # Until verified auth exists, founder keys only in local test mode
            return False
    return key in _TIER_ENTITLEMENTS.get(actor.tier, frozenset())


def require_entitlement(key: str) -> tuple[bool, Optional[str]]:
    actor = resolve_actor_context()
    if has_entitlement(actor, key):
        return True, None
    return False, f"entitlement_denied:{key}:tier={actor.tier.value}:source={actor.identity_source}"


def audit_event(
    action: str,
    resource_type: str,
    resource_id: str = "",
    *,
    permission: str = "",
    result: str = "OK",
    reason: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Minimal audit event (Gate L). Persist best-effort to research store."""
    actor = resolve_actor_context()
    event = {
        "event_id": hashlib.sha256(f"{time.time()}:{action}:{resource_id}".encode()).hexdigest()[:32],
        "organization_id": actor.organization_id,
        "user_id": actor.user_id,
        "actor_type": actor.tier.value,
        "identity_source": actor.identity_source,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "permission": permission,
        "request_id": actor.request_id,
        "created_at": int(time.time() * 1000),
        "result": result,
        "reason": reason,
        "metadata_hash": hashlib.sha256(str(metadata or {}).encode()).hexdigest()[:16],
        "researchOnly": True,
    }
    try:
        from backend.nexus_research.storage import get_research_store

        get_research_store().append("audit_events", event)
    except Exception:  # noqa: BLE001
        pass
    return event
