"""V14-K Closed-Loop Scale V3 — Founder-private integrated closed loop at scale.

Targets: candidate_count>=50000, completed_lifecycle_count>=25000.
50+ fixture symbols, multi-regime, fault injection.
Hard bans: no profitability calc, no Demo/exchange, no auto-integrate.
"""
from __future__ import annotations

from backend.nexus_scale_v3.campaign import (
    CANONICAL_PATH,
    FROZEN_SEED,
    HARD_BANS,
    INVALID_PREFIX,
    PACKAGE,
    PASS_STATUS,
    REQUIRED_ONTOLOGY,
    REQUIRED_ZERO_INVARIANTS,
    SCHEMA,
    TARGET_CANDIDATES,
    TARGET_COMPLETED_LIFECYCLES,
    campaign_digest,
    run_fault_injection_session,
    run_scaled_closed_loop,
    run_v14_closed_loop_scale_campaign,
)
from backend.nexus_scale_v3.injections import (
    SCALE_FAULT_CLASSES,
    injection_matrix,
)
from backend.nexus_scale_v3.invariants import (
    empty_invariant_counts,
    invariants_pass,
)
from backend.nexus_scale_v3.probes import (
    run_cancel_replace_probe,
    run_checkpoint_rollback_probe,
    run_focused_scale_probes,
    run_qualification_blocks_probe,
)
from backend.nexus_scale_v3.universe import (
    SYMBOLS,
    TARGET_SYMBOL_COUNT,
    VOL_REGIMES,
    build_fixture_instruments,
    build_scale_candidates,
    universe_summary,
)

__all__ = [
    "CANONICAL_PATH",
    "FROZEN_SEED",
    "HARD_BANS",
    "INVALID_PREFIX",
    "PACKAGE",
    "PASS_STATUS",
    "REQUIRED_ONTOLOGY",
    "REQUIRED_ZERO_INVARIANTS",
    "SCALE_FAULT_CLASSES",
    "SCHEMA",
    "SYMBOLS",
    "TARGET_CANDIDATES",
    "TARGET_COMPLETED_LIFECYCLES",
    "TARGET_SYMBOL_COUNT",
    "VOL_REGIMES",
    "build_fixture_instruments",
    "build_scale_candidates",
    "campaign_digest",
    "empty_invariant_counts",
    "injection_matrix",
    "invariants_pass",
    "run_cancel_replace_probe",
    "run_checkpoint_rollback_probe",
    "run_fault_injection_session",
    "run_focused_scale_probes",
    "run_qualification_blocks_probe",
    "run_scaled_closed_loop",
    "run_v14_closed_loop_scale_campaign",
    "universe_summary",
]
