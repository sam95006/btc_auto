"""V14-F Regime and Cross-Asset Lab — descriptive PIT regimes + lead-lag.

Hard bans: no predictive edge claims, no demo/shadow/exchange write,
no formal WF/OOS, no strategy promotion, no auto-integrate, no PR27 merge.
"""
from __future__ import annotations

from backend.nexus_regime_lab.catalog import regime_catalog, require_regime
from backend.nexus_regime_lab.constants import (
    HARD_BANS,
    LANE,
    LANE_NAME,
    NON_CLAIMS,
    REGIME_IDS,
    SCHEMA,
)
from backend.nexus_regime_lab.fixtures import build_synthetic_bars
from backend.nexus_regime_lab.forensic_ro import (
    ForensicWriteAttemptError,
    forensic_campaign_probe,
    refuse_write,
)
from backend.nexus_regime_lab.lead_lag import lead_lag_from_capture, lead_lag_matrix, lead_lag_pair
from backend.nexus_regime_lab.regimes import (
    classify_all_regimes,
    classify_bundle_from_capture,
)
from backend.nexus_regime_lab.replay import (
    fingerprint_bundle,
    fingerprint_lead_lag,
    prove_lead_lag_no_negative_receive_leak,
    prove_pit_excludes_future,
    run_classification_once,
    verify_deterministic_replay,
)

__all__ = [
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "NON_CLAIMS",
    "REGIME_IDS",
    "SCHEMA",
    "ForensicWriteAttemptError",
    "build_synthetic_bars",
    "classify_all_regimes",
    "classify_bundle_from_capture",
    "fingerprint_bundle",
    "fingerprint_lead_lag",
    "forensic_campaign_probe",
    "lead_lag_from_capture",
    "lead_lag_matrix",
    "lead_lag_pair",
    "prove_lead_lag_no_negative_receive_leak",
    "prove_pit_excludes_future",
    "refuse_write",
    "regime_catalog",
    "require_regime",
    "run_classification_once",
    "verify_deterministic_replay",
]
