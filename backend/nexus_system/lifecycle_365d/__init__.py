"""V11.1 365-day system lifecycle campaign — SYSTEM CORRECTNESS only.

Hard bans: no profitability measurement, no strategy selection, no formal
Walk-forward, no OOS consumption, no edge claim, no exchange write.
"""
from __future__ import annotations

from backend.nexus_system.lifecycle_365d.campaign import (
    PASS_STATUS,
    INVALID_PREFIX,
    SCHEMA,
    FROZEN_SEED,
    run_system_lifecycle_365d_campaign,
    campaign_digest,
)
from backend.nexus_system.lifecycle_365d.config import Lifecycle365Config, load_lifecycle_365_config
from backend.nexus_system.lifecycle_365d.injections import (
    LIFECYCLE_FAULT_CLASSES,
    injection_matrix,
)
from backend.nexus_system.lifecycle_365d.invariants import (
    HARD_BANS,
    REQUIRED_ZERO_INVARIANTS,
    empty_invariant_counts,
)

__all__ = [
    "FROZEN_SEED",
    "HARD_BANS",
    "INVALID_PREFIX",
    "LIFECYCLE_FAULT_CLASSES",
    "PASS_STATUS",
    "REQUIRED_ZERO_INVARIANTS",
    "SCHEMA",
    "Lifecycle365Config",
    "campaign_digest",
    "empty_invariant_counts",
    "injection_matrix",
    "load_lifecycle_365_config",
    "run_system_lifecycle_365d_campaign",
]
