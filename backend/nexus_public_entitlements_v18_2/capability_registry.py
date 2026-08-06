"""Single public read-only capability registry (V18.2)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_public_entitlements_v18_2.constants import FORBIDDEN_CAPABILITY_IDS


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    capability_id: str
    read_only: bool
    category: str
    description: str


READ_ONLY_CAPABILITIES: tuple[str, ...] = (
    "MARKET_OVERVIEW",
    "MARKET_STATUS_REALTIME",
    "MARKET_STATUS_DELAYED",
    "TOP_OPPORTUNITY_PREVIEW",
    "TOP_OPPORTUNITY_FULL",
    "SCANNER_PREVIEW",
    "SCANNER_FULL",
    "SCANNER_ADVANCED_FILTERS",
    "DECISION_DIRECTION",
    "DECISION_REASON_SUMMARY",
    "SUPPORTING_EVIDENCE",
    "CONTRADICTING_EVIDENCE",
    "INVALIDATION",
    "RISK_EXPLANATION",
    "DATA_TRUST_BASIC",
    "DATA_TRUST_DETAILED",
    "REGIME_BASIC",
    "REGIME_PROBABILITY",
    "FUNDING_SUMMARY",
    "FUNDING_HISTORY",
    "OI_SUMMARY",
    "OI_HISTORY",
    "LIQUIDATION_SUMMARY",
    "ORDER_FLOW",
    "SPREAD_DEPTH",
    "CROSS_EXCHANGE_COMPARE",
    "HISTORICAL_SIMILARITY",
    "DECISION_TIMELINE",
    "SHADOW_OUTCOME_SUMMARY",
    "SHADOW_OUTCOME_HISTORY",
    "PROCESS_CLASSIFICATION",
    "COUNTERFACTUAL_SUMMARY",
    "WATCHLIST",
    "CUSTOM_ALERTS",
    "AI_BASIC",
    "AI_MARKET_ANALYST",
    "AI_RESEARCH",
    "CSV_EXPORT",
    "REPORT_EXPORT",
    "READONLY_API",
    "WEBHOOK",
    "TEAM_WATCHLIST",
    "TEAM_ALERTS",
    "ORG_DASHBOARD",
    "ORG_ROLES",
    "AUDIT_LOG",
    "SSO",
    "IP_ALLOWLIST",
    "SLA",
    "WHITE_LABEL_REPORT",
)


def _build_registry() -> dict[str, CapabilityDefinition]:
    registry: dict[str, CapabilityDefinition] = {}
    for cap_id in READ_ONLY_CAPABILITIES:
        if cap_id in FORBIDDEN_CAPABILITY_IDS:
            raise RuntimeError(f"HARD BAN: forbidden capability in catalog: {cap_id}")
        registry[cap_id] = CapabilityDefinition(
            capability_id=cap_id,
            read_only=True,
            category="intelligence_read",
            description=f"Read-only intelligence capability {cap_id}",
        )
    overlap = set(registry) & FORBIDDEN_CAPABILITY_IDS
    if overlap:
        raise RuntimeError(f"HARD BAN: forbidden capabilities registered: {sorted(overlap)}")
    return registry


class PublicCapabilityRegistry:
    """Canonical read-only capability catalog."""

    __slots__ = ("_caps",)

    def __init__(self) -> None:
        self._caps = _build_registry()

    def all_ids(self) -> frozenset[str]:
        return frozenset(self._caps)

    def get(self, capability_id: str) -> CapabilityDefinition | None:
        if capability_id in FORBIDDEN_CAPABILITY_IDS:
            return None
        return self._caps.get(capability_id)

    def assert_read_only(self, capability_id: str) -> None:
        if capability_id in FORBIDDEN_CAPABILITY_IDS:
            raise ValueError(f"HARD BAN: forbidden capability {capability_id}")
        cap = self._caps.get(capability_id)
        if cap is None:
            raise KeyError(f"unknown capability {capability_id}")
        if not cap.read_only:
            raise ValueError(f"capability must be read-only: {capability_id}")

    def snapshot(self) -> dict[str, Any]:
        return {
            "registry_id": "PUBLIC_CAPABILITY_REGISTRY_V18_2",
            "count": len(self._caps),
            "read_only_only": True,
            "forbidden_count": len(FORBIDDEN_CAPABILITY_IDS),
            "capabilities": [
                {
                    "capability_id": c.capability_id,
                    "read_only": c.read_only,
                    "category": c.category,
                }
                for c in sorted(self._caps.values(), key=lambda x: x.capability_id)
            ],
        }


# Singleton — acceptance: single_capability_registry_count = 1
PUBLIC_CAPABILITY_REGISTRY = PublicCapabilityRegistry()
