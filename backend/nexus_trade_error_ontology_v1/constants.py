"""V16-A Trade Error Ontology V1 — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v16_a_trade_error_ontology_v1"
SCHEMA_GENE = "v16_a_trade_error_gene_v1"
SCHEMA_CLASSIFICATION = "v16_a_trade_error_classification_v1"
SCHEMA_AI_PROPOSAL = "v16_a_trade_error_ai_proposal_v1"
ONTOLOGY_VERSION = "v1.0.0"
PACKAGE = "backend.nexus_trade_error_ontology_v1"
LANE = "V16-A"
LANE_NAME = "TRADE_ERROR_ONTOLOGY_V1"
BRANCH = "feature/v16-trade-error-ontology-v1"
ARTIFACT_REL = "artifacts/readiness/immutable/v16_trade_error_ontology_v1"
BASE_COMMIT = "f01407e5d7c7e4c00e0eb1616dc5ef74d91a58b5"
SCHEMA_REL = f"{ARTIFACT_REL}/trade_error_ontology_v1.schema.json"
GENE_BANK_REL = f"{ARTIFACT_REL}/gene_bank_v1.json"

PROCESS_CLASSES: tuple[str, ...] = (
    "GOOD_PROCESS_WIN",
    "GOOD_PROCESS_LOSS",
    "BAD_PROCESS_WIN",
    "BAD_PROCESS_LOSS",
    "UNAVOIDABLE_SHOCK",
    "INSUFFICIENT_EVIDENCE",
)

INFORMATIVE_CLASSES = frozenset(
    {
        "GOOD_PROCESS_WIN",
        "GOOD_PROCESS_LOSS",
        "BAD_PROCESS_WIN",
        "BAD_PROCESS_LOSS",
        "UNAVOIDABLE_SHOCK",
    }
)

ERROR_DIMENSIONS: tuple[str, ...] = (
    "DATA",
    "REGIME",
    "STRATEGY",
    "ENTRY",
    "EXIT",
    "EXECUTION",
    "LIQUIDITY",
    "COST",
    "AI_REASONING",
    "RISK",
    "PORTFOLIO",
    "INFRASTRUCTURE",
    "EXTERNAL_SHOCK",
)

SEVERITY_LEVELS: tuple[str, ...] = (
    "NONE",
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
)

AVOIDABILITY_LEVELS: tuple[str, ...] = (
    "AVOIDABLE",
    "PARTIALLY_AVOIDABLE",
    "UNAVOIDABLE",
    "UNKNOWN",
)

# Legacy class aliases → V16-A canonical.
LEGACY_CLASS_MAP: dict[str, str] = {
    "UNDETERMINED": "INSUFFICIENT_EVIDENCE",
    "UNDETERMINED_PROCESS": "INSUFFICIENT_EVIDENCE",
    "PROCESS_UNDETERMINED": "INSUFFICIENT_EVIDENCE",
    "INCONCLUSIVE": "INSUFFICIENT_EVIDENCE",
    "INCOMPLETE_EVIDENCE": "INSUFFICIENT_EVIDENCE",
    "EXTERNAL_SHOCK": "UNAVOIDABLE_SHOCK",
}

HARD_BANS: tuple[str, ...] = (
    "no_real_money",
    "no_mainnet",
    "no_exchange_write",
    "no_oos",
    "no_walkforward",
    "no_fabricated_ai_learning",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_ai_override_of_deterministic_class",
    "no_pnl_alone_decides_process",
    "no_loss_as_automatic_bad_process",
    "no_win_as_automatic_good_process",
    "no_status_json_lane_artifact",
    "no_acceleration_report_edit",
    "no_auto_integrate",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_trade_error_ontology_v1/",
    "tests/trade_error_ontology_v1/",
    ARTIFACT_REL + "/",
)

FORBIDDEN_LOG_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "token",
        "private_key",
        "authorization",
        "raw_prompt",
        "raw_response",
        "bybit_api_key",
        "bybit_api_secret",
        "account_balance",
        "wallet_address",
    }
)

CONTROL_FIXTURE_LABEL = "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"
