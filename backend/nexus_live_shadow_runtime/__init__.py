"""V18.1 Phase A — Private Live Shadow Runtime Conductor (+ V18.2 24h campaign).

Single writer authority integrating existing V18 modules:
  Official Read-only Adapters → Incremental Ingest → Bronze → Silver → PIT →
  Eligible Universe → Data Trust → Gold Features → Regime → Strategy Router →
  Uncertainty → Risk Review → Shadow Decision → Shadow Ledger →
  Public-safe Projection

Never places exchange orders. Never invents a parallel pipeline.
V18.2 Phase C extends this package with Shadow 24h Qualification Campaign.
"""
from __future__ import annotations

from backend.nexus_live_shadow_runtime.campaign import (
    CampaignConfig,
    Shadow24hQualificationCampaign,
    launch_detached,
    make_campaign_id,
)
from backend.nexus_live_shadow_runtime.campaign_checkpoint import (
    CHECKPOINT_FIELDS,
    CompactCheckpointWriter,
    build_compact_checkpoint,
    validate_checkpoint_schema,
)
from backend.nexus_live_shadow_runtime.conductor import (
    ConductorConfig,
    LiveShadowRuntimeConductor,
    run_bounded_smoke,
)
from backend.nexus_live_shadow_runtime.constants import (
    DATA_CLASSES,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PACKAGE,
    RUNTIME_STATES,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_live_shadow_runtime.metrics import RuntimeMetrics
from backend.nexus_live_shadow_runtime.projection import (
    PublicSafeProjectionWriter,
    filter_public_safe,
)
from backend.nexus_live_shadow_runtime.state_machine import (
    InvalidRuntimeTransitionError,
    RuntimeStateMachine,
)

__all__ = [
    "CHECKPOINT_FIELDS",
    "CampaignConfig",
    "CompactCheckpointWriter",
    "ConductorConfig",
    "DATA_CLASSES",
    "HARD_BANS",
    "InvalidRuntimeTransitionError",
    "LANE",
    "LANE_NAME",
    "LiveShadowRuntimeConductor",
    "OWNED_PATHS",
    "PACKAGE",
    "PublicSafeProjectionWriter",
    "RUNTIME_STATES",
    "RuntimeMetrics",
    "RuntimeStateMachine",
    "SCHEMA",
    "SCHEMA_VERSION",
    "Shadow24hQualificationCampaign",
    "build_compact_checkpoint",
    "filter_public_safe",
    "launch_detached",
    "make_campaign_id",
    "run_bounded_smoke",
    "validate_checkpoint_schema",
]
