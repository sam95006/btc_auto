"""NEXUS General Multi-Strategy Research Engine V1 public exports."""
from __future__ import annotations

from backend.nexus_strategy_engine.components import COMPONENT_IDS, component_registry
from backend.nexus_strategy_engine.constants import (
    ENGINE_STAGE,
    EVIDENCE_SCHEMA_VERSION,
    MAX_DEVELOPMENT_HYPOTHESES,
    STRATEGY_SPEC_SCHEMA_VERSION,
)
from backend.nexus_strategy_engine.development_research import (
    recommend_future_candidates,
    run_hypothesis_development,
)
from backend.nexus_strategy_engine.evidence_v2 import (
    deterministic_process_baseline,
    evidence_v2_schema,
)
from backend.nexus_strategy_engine.hypotheses import default_hypothesis_drafts, preregister_hypotheses
from backend.nexus_strategy_engine.lesson_seal import seal_integration_lessons
from backend.nexus_strategy_engine.observability import build_observability_status, observability_contract
from backend.nexus_strategy_engine.reflection_calibration import (
    build_calibration_packets,
    run_reflection_calibration,
)
from backend.nexus_strategy_engine.strategy_spec import (
    compute_semantic_checksum,
    compute_strategy_checksum,
    freeze_spec,
    strategy_spec_schema,
    validate_spec,
)

__all__ = [
    "COMPONENT_IDS",
    "ENGINE_STAGE",
    "EVIDENCE_SCHEMA_VERSION",
    "MAX_DEVELOPMENT_HYPOTHESES",
    "STRATEGY_SPEC_SCHEMA_VERSION",
    "build_calibration_packets",
    "build_observability_status",
    "component_registry",
    "compute_semantic_checksum",
    "compute_strategy_checksum",
    "default_hypothesis_drafts",
    "deterministic_process_baseline",
    "evidence_v2_schema",
    "freeze_spec",
    "observability_contract",
    "preregister_hypotheses",
    "recommend_future_candidates",
    "run_hypothesis_development",
    "run_reflection_calibration",
    "seal_integration_lessons",
    "strategy_spec_schema",
    "validate_spec",
]
