"""Public-safe intelligence DTO dataclasses (V2)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RegimeProbabilitiesDto:
    """Descriptive PIT regime probabilities — no proprietary thresholds."""

    strong_bull_probability: float = 0.0
    strong_bear_probability: float = 0.0
    volatility_expansion_probability: float = 0.0
    liquidity_stress_probability: float = 0.0
    long_crowding_probability: float = 0.0
    correlation_breakdown_probability: float = 0.0
    event_risk_probability: float = 0.0
    regime_transition_probability: float = 0.0
    regime_confidence: float = 0.0
    regime_freshness: str = "UNAVAILABLE"

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceItemDto:
    evidence_summary: str
    evidence_polarity: str  # SUPPORTING | CONTRADICTING | NEUTRAL
    evidence_freshness: str = "UNAVAILABLE"
    source_label: str = "PUBLIC"
    as_of: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimilarCaseSummaryDto:
    """Public similar-case summary — never raw private memory graph."""

    similar_case_summary: str
    similar_case_count: int = 0
    similar_case_overlap_band: str = "UNAVAILABLE"

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PublicIntelligenceDtoV2:
    """Top-level public intelligence DTO V2.

    FORBIDDEN: secrets, internal strategy source, private execution controls,
    proprietary thresholds, raw private memory graph, exchange write.
    """

    schema_version: str
    symbol: str
    decision_id: str
    regime_probabilities: RegimeProbabilitiesDto
    ai_recommendation_state: str
    supporting_evidence: tuple[EvidenceItemDto, ...]
    contradicting_evidence: tuple[EvidenceItemDto, ...]
    uncertainty: float
    uncertainty_band: str
    abstention_reason: str | None
    strategy_expert_label: str
    lesson_applied_label: str
    similar_case_summary: SimilarCaseSummaryDto
    data_freshness: str
    freshness_state: str
    decision_lifecycle_status: str
    as_of: str
    retrieved_at: str
    availability: str = "AVAILABLE"
    environment: str = "STAGING"
    lineage_id: str = ""
    published_at: str = ""
    regime_label: str = "MIXED"
    ai_recommendation_message: str = ""
    abstention_code: str | None = None
    stale_indicator: bool = False
    unavailable_indicator: bool = False
    decision_state: str = "ACTIVE"
    decision_posture: str = "OBSERVE"
    confidence_band: str = "MEDIUM"
    system_availability: str = "AVAILABLE"
    data_class: str = "PUBLIC_SAFE"
    raw_memory_graph: bool = False
    private_fields_included: bool = False
    private_core_import_count: int = 0
    citation_count: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "published_at": self.published_at,
            "availability": self.availability,
            "environment": self.environment,
            "lineage_id": self.lineage_id,
            "data_class": self.data_class,
            "symbol": self.symbol,
            "decision_id": self.decision_id,
            "as_of": self.as_of,
            "retrieved_at": self.retrieved_at,
            "regime_probabilities": self.regime_probabilities.to_public_dict(),
            "regime_label": self.regime_label,
            "ai_recommendation_state": self.ai_recommendation_state,
            "ai_recommendation_message": self.ai_recommendation_message,
            "supporting_evidence": [e.to_public_dict() for e in self.supporting_evidence],
            "contradicting_evidence": [e.to_public_dict() for e in self.contradicting_evidence],
            "uncertainty": self.uncertainty,
            "uncertainty_band": self.uncertainty_band,
            "abstention_reason": self.abstention_reason,
            "abstention_code": self.abstention_code,
            "strategy_expert_label": self.strategy_expert_label,
            "lesson_applied_label": self.lesson_applied_label,
            "similar_case_summary": self.similar_case_summary.to_public_dict(),
            "data_freshness": self.data_freshness,
            "freshness_state": self.freshness_state,
            "stale_indicator": self.stale_indicator,
            "unavailable_indicator": self.unavailable_indicator,
            "decision_lifecycle_status": self.decision_lifecycle_status,
            "decision_state": self.decision_state,
            "decision_posture": self.decision_posture,
            "confidence_band": self.confidence_band,
            "system_availability": self.system_availability,
            "citation_count": self.citation_count,
            "raw_memory_graph": False,
            "private_fields_included": False,
            "private_core_import_count": 0,
        }
