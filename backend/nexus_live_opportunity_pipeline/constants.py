"""V18-D Live Opportunity Pipeline — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V18_D_LIVE_OPPORTUNITY_PIPELINE"
LANE = "V18-D"
LANE_NAME = "LIVE_OPPORTUNITY_PIPELINE_E2E"
BRANCH = "feature/v18-live-opportunity-pipeline"
BASE_COMMIT = "324e52f0573d7e3ad32feb2968274a52b8d8da75"
CAMPAIGN_ID = "v18_d_opportunity_pipeline"
RANDOM_SEED = 20260806
AS_OF_MS_DEFAULT = 1_720_000_000_000
DEFAULT_MARKET = "bybit_linear"

# Shadow decision enum (includes BLOCK; candidate is never a trade signal).
DECISION_ENUM: tuple[str, ...] = (
    "LONG",
    "SHORT",
    "WAIT",
    "REDUCE",
    "ABSTAIN",
    "BLOCK",
)

DECISION_SEVERITY: dict[str, int] = {
    "LONG": 0,
    "SHORT": 0,
    "WAIT": 1,
    "REDUCE": 2,
    "ABSTAIN": 3,
    "BLOCK": 4,
}

ENTRY_SIDES = frozenset({"LONG", "SHORT"})
NO_TRADE_SIDES = frozenset({"WAIT", "REDUCE", "ABSTAIN", "BLOCK"})

PIPELINE_STAGES: tuple[str, ...] = (
    "eligible_universe",
    "feature_snapshot",
    "regime",
    "strategy_experts",
    "candidate_score",
    "supporting_evidence",
    "contradicting_evidence",
    "cost_feasibility",
    "uncertainty",
    "risk_review",
    "shadow_decision",
)

REQUIRED_DECISION_FIELDS: tuple[str, ...] = (
    "decision_id",
    "symbol",
    "market",
    "as_of",
    "data_class",
    "data_trust",
    "regime_probabilities",
    "strategy_expert",
    "supporting_evidence",
    "contradicting_evidence",
    "cost_estimate",
    "uncertainty",
    "risk_status",
    "invalidation",
    "freshness",
    "lineage",
    "decision_status",
    "actual_ordered",
    "actual_filled",
)

DECISION_STATUS_VALUES: tuple[str, ...] = (
    "OBSERVED",
    "CANDIDATE",
    "REVIEWED",
    "SHADOW_READY",
    "BLOCKED",
    "ABSTAINED",
    "WAITING",
)

DATA_CLASSES: tuple[str, ...] = (
    "FIXTURE",
    "LIVE_READ_ONLY",
    "BOUNDED_SAMPLE",
)

# Modules wired from tip (present on V17 integrated HEAD).
TIP_MODULES: dict[str, str] = {
    "data_trust": "backend.nexus_data_trust_engine_v2",
    "gold_feature_factory": "backend.nexus_gold_feature_factory",
    "probabilistic_regime": "backend.nexus_probabilistic_regime_v2",
    "strategy_router": "backend.nexus_strategy_expert_router",
    "abstention": "backend.nexus_uncertainty_abstention",
    "risk_capacity": "backend.nexus_risk_capacity",
    "decision_memory_graph": "backend.nexus_decision_memory_graph",
    "historical_universe": "backend.nexus_historical_universe",
    "cost_sensitivity": "backend.nexus_cost_sensitivity",
}

MAX_COST_BPS_FEASIBLE = 35.0
MIN_CANDIDATE_SCORE_FOR_ENTRY = 0.45

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_live_opportunity_pipeline",
    "tools/research/live_opportunity_pipeline",
    "tests/live_opportunity_pipeline",
)

HARD_BANS: frozenset[str] = frozenset(
    {
        "no_exchange_write",
        "no_demo_orders",
        "no_mainnet",
        "no_pr26_merge",
        "no_pr27_merge",
        "no_acceleration_report_edit",
        "no_archive_rebuild",
        "no_ai_override_data_trust",
        "no_ai_override_risk",
        "candidate_is_not_trade_signal",
        "actual_ordered_must_be_false",
        "actual_filled_must_be_false",
    }
)

EVIDENCE_PATH = r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_d_opportunity_pipeline.json"
