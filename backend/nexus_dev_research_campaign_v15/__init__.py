"""V15-C Real Development Research Campaign — public surface."""
from __future__ import annotations

from backend.nexus_dev_research_campaign_v15.adversarial import run_adversarial_review
from backend.nexus_dev_research_campaign_v15.artifacts import write_immutable_artifacts
from backend.nexus_dev_research_campaign_v15.campaign import run_campaign
from backend.nexus_dev_research_campaign_v15.constants import (
    ALLOWED_LABELS,
    CAMPAIGN_ID,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    SCHEMA,
)
from backend.nexus_dev_research_campaign_v15.hard_bans import (
    HardBanViolation,
    refuse_auto_integrate,
    refuse_exchange_write,
    refuse_formal_walk_forward,
    refuse_oos_consume,
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
    "refuse_auto_integrate",
    "refuse_exchange_write",
    "refuse_formal_walk_forward",
    "refuse_oos_consume",
    "run_adversarial_review",
    "run_campaign",
    "write_immutable_artifacts",
]
