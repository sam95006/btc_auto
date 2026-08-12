"""V15-D Research Meta-Analysis and False Discovery — public surface."""
from __future__ import annotations

from backend.nexus_research_meta_analysis.constants import (
    ALLOWED_LABELS,
    CAMPAIGN_ID,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    SCHEMA,
)
from backend.nexus_research_meta_analysis.engine import (
    adversarial_self_review,
    evaluate_experiment,
    run_meta_analysis,
)
from backend.nexus_research_meta_analysis.fixtures import build_synthetic_experiments
from backend.nexus_research_meta_analysis.hard_bans import (
    HardBanViolation,
    refuse_auto_integrate,
    refuse_exchange_write,
    refuse_formal_walk_forward,
    refuse_lane_status_json,
    refuse_oos_consume,
    refuse_oos_execute,
    refuse_oos_reserve,
    refuse_promising_without_siblings,
    refuse_silent_favorable_selection,
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
    "build_synthetic_experiments",
    "evaluate_experiment",
    "refuse_auto_integrate",
    "refuse_exchange_write",
    "refuse_formal_walk_forward",
    "refuse_lane_status_json",
    "refuse_oos_consume",
    "refuse_oos_execute",
    "refuse_oos_reserve",
    "refuse_promising_without_siblings",
    "refuse_silent_favorable_selection",
    "run_meta_analysis",
]
