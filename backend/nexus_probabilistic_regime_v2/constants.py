"""V16-C Probabilistic Regime Engine V2 — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V16_C_PROBABILISTIC_REGIME_ENGINE_V2"
SCHEMA_VERSION = "probabilistic_regime_v2_1"
LANE = "V16-C"
LANE_NAME = "PROBABILISTIC_REGIME_ENGINE_V2"
BRANCH = "feature/v16-probabilistic-regime-engine-v2"
BASE_COMMIT = "f01407e5d7c7e4c00e0eb1616dc5ef74d91a58b5"
RANDOM_SEED = 20260806

# Multi-dimensional regimes — not crude bull/bear only.
REGIME_DIMENSIONS = (
    "Direction",
    "Volatility",
    "Liquidity",
    "LeverageCrowding",
    "TrendQuality",
    "CrossAssetCorrelation",
    "EventRisk",
    "Session",
    "CapitalFlow",
    "Microstructure",
)

# Founder-required probability / quality outputs.
OUTPUT_KEYS = (
    "strong_bull_probability",
    "strong_bear_probability",
    "volatility_expansion_probability",
    "liquidity_stress_probability",
    "long_crowding_probability",
    "correlation_breakdown_probability",
    "event_risk_probability",
    "regime_transition_probability",
    "regime_confidence",
    "regime_freshness",
)

# Formal first-class states (not silent nulls).
FORMAL_STATES = frozenset({"UNKNOWN", "MIXED", "CLEAR"})

HARD_BANS = frozenset(
    {
        "no_pr26_merge",
        "no_pr27_merge",
        "no_auto_integrate",
        "no_demo_orders",
        "no_shadow_orders",
        "no_exchange_write",
        "no_mainnet",
        "no_real_money",
        "no_formal_walk_forward",
        "no_oos_execution",
        "no_profitability_claims",
        "no_predictive_edge_claims",
        "no_strategy_promotion",
        "no_leverage_mutation",
        "no_risk_gate_override",
        "no_status_json_artifact",
        "no_acceleration_report_edit",
        "no_g_drive_mutation",
    }
)

OWNED_PATHS = [
    "backend/nexus_probabilistic_regime_v2",
    "tools/research/probabilistic_regime_v2",
    "tests/probabilistic_regime_v2",
]

# Timing / hysteresis defaults (ms unless noted).
DEFAULT_BAR_MS = 60_000
DEFAULT_LOOKBACK_BARS = 24
DEFAULT_STALE_AFTER_MS = 180_000
DEFAULT_MIN_DWELL_BARS = 3
DEFAULT_HYSTERESIS_MARGIN = 0.08
DEFAULT_TRANSITION_LOOKBACK = 8

# Calibration interface version — consumers can bind without mutating engine.
CALIBRATION_INTERFACE_VERSION = "regime_prob_calibration_v1"

NON_CLAIMS = (
    "No predictive edge",
    "No profitability claim",
    "No strategy signal / order intent",
    "Descriptive Point-in-Time probabilistic regime measurement only",
    "UNKNOWN/MIXED are formal fail-closed states under stale or conflicting evidence",
)
