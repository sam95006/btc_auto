"""V13-G Closed-Loop Scale V2 — Founder-private integrated closed loop at scale.

Targets: candidate_count>=10000, completed_lifecycle_count>=5000.
Hard bans: no profitability calc, no Demo/exchange, no PR27 merge.
"""
from __future__ import annotations

from backend.nexus_system.closed_loop_scale_v13.campaign import (
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
    run_v13_closed_loop_scale_campaign,
)
from backend.nexus_system.closed_loop_scale_v13.injections import (
    SCALE_FAULT_CLASSES,
    injection_matrix,
)
from backend.nexus_system.closed_loop_scale_v13.invariants import (
    empty_invariant_counts,
    invariants_pass,
)
from backend.nexus_system.closed_loop_scale_v13.probes import (
    run_cancel_replace_probe,
    run_focused_scale_probes,
    run_qualification_blocks_probe,
)
from backend.nexus_system.closed_loop_scale_v13.universe import (
    SYMBOLS,
    VOL_REGIMES,
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
    "VOL_REGIMES",
    "build_scale_candidates",
    "campaign_digest",
    "empty_invariant_counts",
    "injection_matrix",
    "invariants_pass",
    "run_cancel_replace_probe",
    "run_fault_injection_session",
    "run_focused_scale_probes",
    "run_qualification_blocks_probe",
    "run_scaled_closed_loop",
    "run_v13_closed_loop_scale_campaign",
    "universe_summary",
]
