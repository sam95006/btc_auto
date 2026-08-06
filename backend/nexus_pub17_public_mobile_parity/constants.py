"""V17 deep — Public/Mobile contract parity constants.

Canonical shared vocabulary for PUB17 web surfaces and Mobile V17
read-only DTOs. This round freezes field sets, freshness honesty, and
PROVIDER_REQUIRED rules. No claim that Live providers are bound.
"""
from __future__ import annotations

SCHEMA = "pub17_public_mobile_parity_contract_v1"
SCHEMA_VERSION = "1"
PACKAGE = "backend.nexus_pub17_public_mobile_parity"
LANE = "V17-DEEP-PARITY"
LANE_NAME = "PUBLIC_MOBILE_CONTRACT_PARITY"
BRANCH = "feature/v17-deep-public-mobile-parity"
PROGRAM_ID = "NEXUS_V17_PUBLIC_MOBILE_CONTRACT_PARITY"

ARTIFACT_REL = "artifacts/readiness/immutable/pub17_public_mobile_parity"
CONTRACT_REL = f"{ARTIFACT_REL}/public_mobile_parity_contract.json"

# Public first-screen answer ids (PUB17-B) — order is UI-stable.
PUBLIC_MARKET_PULSE_ANSWER_IDS: tuple[str, ...] = (
    "global_market_state",
    "crypto_derivatives_risk",
    "top_3_markets_contracts",
    "ai_posture",
    "supporting_evidence",
    "counter_evidence",
    "invalidation",
    "data_freshness",
    "analysis_vs_actual_trading",
)

# Mobile MarketPulseDto wire keys that must remain present and public-safe.
MOBILE_MARKET_PULSE_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "as_of",
    "retrieved_at",
    "availability",
    "data_mode",
    "market_state",
    "crypto_pulse",
    "global_pulse",
    "ai_posture",
    "data_freshness",
    "provider_status",
    "top_opportunities",
    "evidence_summary",
    "counter_evidence_summary",
    "risk_explanation",
    "lineage_id",
    "demo",
    "stale_indicator",
    "execution_control_count",
    "exchange_write_capability",
    "customer_trading_capability_count",
)

# Semantic map: public first-screen answer id -> mobile DTO field(s).
PUBLIC_TO_MOBILE_SEMANTIC_MAP: dict[str, tuple[str, ...]] = {
    "global_market_state": ("market_state", "global_pulse"),
    "crypto_derivatives_risk": ("crypto_pulse", "risk_explanation"),
    "top_3_markets_contracts": ("top_opportunities",),
    "ai_posture": ("ai_posture",),
    "supporting_evidence": ("evidence_summary",),
    "counter_evidence": ("counter_evidence_summary",),
    "invalidation": ("risk_explanation",),
    "data_freshness": ("data_freshness", "stale_indicator"),
    "analysis_vs_actual_trading": (
        "execution_control_count",
        "exchange_write_capability",
        "customer_trading_capability_count",
    ),
}

# Shared freshness vocabulary (union of public pulse + global contracts + mobile).
SHARED_FRESHNESS_STATES: tuple[str, ...] = (
    "LIVE",
    "FRESH",
    "STALE",
    "DEGRADED",
    "UNAVAILABLE",
    "PROVIDER_REQUIRED",
    "BLOCKED",
    "DEMO_DATA",
)

# Shared availability vocabulary.
SHARED_AVAILABILITY_STATES: tuple[str, ...] = (
    "AVAILABLE",
    "CONTRACT_READY",
    "PROVIDER_REQUIRED",
    "UNAVAILABLE",
    "BLOCKED",
    "DEMO_DATA",
    "STALE",
    "DEGRADED",
)

# Normalized market source DTO required fields (PUB17-A) — parity baseline.
PUBLIC_NORMALIZED_SOURCE_DTO_FIELDS: tuple[str, ...] = (
    "schema",
    "schema_version",
    "domain",
    "source_id",
    "status",
    "mode",
    "freshness",
    "availability",
    "provenance",
    "license_visibility",
    "value",
    "unit",
    "as_of",
    "retrieved_at",
    "lineage_id",
    "fabricated",
)

# Mobile V17 required page labels (must match MarketPulseDto.requiredPageLabels).
MOBILE_REQUIRED_PAGE_LABELS: tuple[str, ...] = (
    "Market Pulse",
    "Opportunity",
    "Regime",
    "Evidence",
    "Counter Evidence",
    "Risk",
    "Watchlist",
    "Alerts",
    "Global Brief",
    "Data Freshness",
    "Subscription Access",
)

# Subscription product boundary labels (PUB17-D ↔ mobile SubscriptionAccessDto).
SHARED_BUYABLE_PRODUCT_LABELS: tuple[str, ...] = (
    "Market Data",
    "AI Intelligence",
    "Decision Context",
    "Risk Explanation",
    "Alerts",
    "Historical Comparisons",
    "Global Market Briefs",
)

SHARED_FORBIDDEN_PRODUCT_LABELS: tuple[str, ...] = (
    "Auto Trading",
    "Copy Trading",
    "Exchange Execution",
    "Private Strategy",
    "Founder Portfolio Access",
)

# Surface ban markers — must never appear as member controls.
FORBIDDEN_MEMBER_CONTROL_MARKERS: tuple[str, ...] = (
    "trade_button",
    "TradeButton",
    "copy_trade",
    "copy_trading",
    "CopyTrading",
    "place_order",
    "submit_order",
    "create_order",
    "execute_trade",
    "leverage_control",
    "position_control",
    "api_key_entry",
    "EXCHANGE_WRITE=True",
    "MAINNET=True",
    "REAL_MONEY=True",
)

# Paths scanned for forbidden member controls (public tip owned surfaces).
SURFACE_SCAN_GLOBS: tuple[str, ...] = (
    "backend/nexus_pub17_market_pulse/**/*.py",
    "backend/nexus_pub17_global_market_contracts/**/*.py",
    "backend/nexus_public_subscription_boundary/**/*.py",
    "backend/nexus_private_to_public_projection_v3/**/*.py",
    "backend/nexus_pub17_public_mobile_parity/**/*.py",
    "frontend/src/member/pulse/**/*.{ts,tsx}",
    "frontend/src/pages/member/**/*.{ts,tsx}",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_pub17_public_mobile_parity",
    "tests/pub17_public_mobile_parity",
    "artifacts/readiness/immutable/pub17_public_mobile_parity",
    "docs/runbooks/V17_TIME_DEPENDENT_BLOCKERS_AND_RESUME.md",
)

HARD_BANS: tuple[str, ...] = (
    "no_member_trade_controls",
    "no_member_copy_trading",
    "no_member_exchange_write",
    "no_fabricated_live_values",
    "no_provider_required_as_live",
    "no_claim_time_dependent_complete",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
)

PASS_RECOMMENDATION = "NEXUS_V17_PUBLIC_MOBILE_CONTRACT_PARITY_PASS"
FAIL_RECOMMENDATION = "NEXUS_V17_PUBLIC_MOBILE_CONTRACT_PARITY_FAIL"
