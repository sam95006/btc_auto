"""Field registry for Public Intelligence DTO V2 (Member UI bindings)."""
from __future__ import annotations

from dataclasses import dataclass

from backend.nexus_public_intelligence_dto_v2.constants import ALLOWED_PUBLIC_FIELDS, SCHEMA


@dataclass(frozen=True)
class PublicDtoField:
    dto_name: str
    field_path: str
    leaf_field: str


PUBLIC_INTELLIGENCE_V2_FIELDS: tuple[PublicDtoField, ...] = (
    PublicDtoField("PublicIntelligenceDtoV2", "regime_probabilities", "regime_probabilities"),
    PublicDtoField("PublicIntelligenceDtoV2", "ai_recommendation_state", "ai_recommendation_state"),
    PublicDtoField("PublicIntelligenceDtoV2", "supporting_evidence", "supporting_evidence"),
    PublicDtoField("PublicIntelligenceDtoV2", "contradicting_evidence", "contradicting_evidence"),
    PublicDtoField("PublicIntelligenceDtoV2", "uncertainty", "uncertainty"),
    PublicDtoField("PublicIntelligenceDtoV2", "abstention_reason", "abstention_reason"),
    PublicDtoField("PublicIntelligenceDtoV2", "strategy_expert_label", "strategy_expert_label"),
    PublicDtoField("PublicIntelligenceDtoV2", "lesson_applied_label", "lesson_applied_label"),
    PublicDtoField("PublicIntelligenceDtoV2", "similar_case_summary", "similar_case_summary"),
    PublicDtoField("PublicIntelligenceDtoV2", "data_freshness", "data_freshness"),
    PublicDtoField("PublicIntelligenceDtoV2", "decision_lifecycle_status", "decision_lifecycle_status"),
    PublicDtoField("PublicIntelligenceDtoV2", "uncertainty_band", "uncertainty_band"),
    PublicDtoField("PublicIntelligenceDtoV2", "freshness_state", "freshness_state"),
    PublicDtoField("PublicIntelligenceDtoV2", "private_core_import_count", "private_core_import_count"),
)


def leaf_fields() -> frozenset[str]:
    return frozenset(f.leaf_field for f in PUBLIC_INTELLIGENCE_V2_FIELDS)


def assert_registry_allowlisted() -> None:
    unknown = leaf_fields() - ALLOWED_PUBLIC_FIELDS
    if unknown:
        raise AssertionError(f"DTO leaves not in ALLOWED_PUBLIC_FIELDS: {sorted(unknown)}")


def schema_version() -> str:
    return SCHEMA
