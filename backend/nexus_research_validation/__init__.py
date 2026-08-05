"""V14-D Robustness and Multiple-Testing Lab — public surface."""
from __future__ import annotations

from backend.nexus_research_validation.constants import (
    ALLOWED_LABELS,
    CAMPAIGN_ID,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    SCHEMA,
)
from backend.nexus_research_validation.fixtures import build_synthetic_candidates
from backend.nexus_research_validation.hard_bans import (
    HardBanViolation,
    refuse_auto_integrate,
    refuse_exchange_write,
    refuse_formal_walk_forward,
    refuse_oos_consume,
)
from backend.nexus_research_validation.lab import (
    adversarial_self_review,
    evaluate_candidate,
    run_robustness_lab,
)

__all__ = [
    "ALLOWED_LABELS",
    "CAMPAIGN_ID",
    "HARD_BANS",
    "HardBanViolation",
    "LANE",
    "LANE_NAME",
    "PACKAGE",
    "SCHEMA",
    "adversarial_self_review",
    "build_synthetic_candidates",
    "evaluate_candidate",
    "refuse_auto_integrate",
    "refuse_exchange_write",
    "refuse_formal_walk_forward",
    "refuse_oos_consume",
    "run_robustness_lab",
]
