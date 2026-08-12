"""V16-C Probabilistic Regime Engine V2.

Multi-dimensional probabilistic regimes (not crude bull/bear).
Point-in-time; hysteresis / min dwell; UNKNOWN/MIXED formal; stale fail-closed.

Hard bans: no PR26/27 merge, no Demo/Shadow/exchange/mainnet, no formal WF/OOS,
no profitability/edge claims, no strategy promotion, no leverage/risk-gate mutation,
no status JSON artifact, no acceleration report edit, no G-drive mutation.
"""
from __future__ import annotations

from backend.nexus_probabilistic_regime_v2.adversarial import (
    run_adversarial_review,
    run_independent_break_attempts,
)
from backend.nexus_probabilistic_regime_v2.calibration import (
    apply_calibration,
    calibration_contract,
)
from backend.nexus_probabilistic_regime_v2.constants import (
    HARD_BANS,
    LANE,
    LANE_NAME,
    NON_CLAIMS,
    OUTPUT_KEYS,
    REGIME_DIMENSIONS,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_probabilistic_regime_v2.engine import (
    ProbabilisticRegimeEngineV2,
    evaluate_regime,
    run_engine_campaign,
)
from backend.nexus_probabilistic_regime_v2.fixtures import build_synthetic_bars

__all__ = [
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "NON_CLAIMS",
    "OUTPUT_KEYS",
    "REGIME_DIMENSIONS",
    "SCHEMA",
    "SCHEMA_VERSION",
    "ProbabilisticRegimeEngineV2",
    "apply_calibration",
    "build_synthetic_bars",
    "calibration_contract",
    "evaluate_regime",
    "run_adversarial_review",
    "run_engine_campaign",
    "run_independent_break_attempts",
]
