"""UX-A-compatible public-safe DTO shapes for Member Web Intelligence.

Defines compatible field names locally so UX-B works even if UX-A is not merged.
Does not import UX-A package (optional peer).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RegimeProbabilitiesDto:
    strong_bull_probability: float | None = None
    strong_bear_probability: float | None = None
    volatility_expansion_probability: float | None = None
    liquidity_stress_probability: float | None = None
    long_crowding_probability: float | None = None
    correlation_breakdown_probability: float | None = None
    event_risk_probability: float | None = None
    regime_transition_probability: float | None = None
    regime_confidence: float | None = None
    regime_freshness: str = "UNAVAILABLE"
    available: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        if not self.available:
            # Unavailable probabilities are null — never fabricated zeros.
            return {
                "available": False,
                "regime_freshness": "UNAVAILABLE",
                "strong_bull_probability": None,
                "strong_bear_probability": None,
                "volatility_expansion_probability": None,
                "liquidity_stress_probability": None,
                "long_crowding_probability": None,
                "correlation_breakdown_probability": None,
                "event_risk_probability": None,
                "regime_transition_probability": None,
                "regime_confidence": None,
            }
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
    similar_case_summary: str
    similar_case_count: int | None = None
    similar_case_overlap_band: str = "UNAVAILABLE"
    win_rate: float | None = None
    available: bool = False
    guarantee_claimed: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        if not self.available:
            return {
                "similar_case_summary": self.similar_case_summary or "UNAVAILABLE",
                "similar_case_count": None,
                "similar_case_overlap_band": "UNAVAILABLE",
                "win_rate": None,
                "available": False,
                "guarantee_claimed": False,
                "display_count": "UNAVAILABLE",
            }
        return {
            "similar_case_summary": self.similar_case_summary,
            "similar_case_count": self.similar_case_count,
            "similar_case_overlap_band": self.similar_case_overlap_band,
            "win_rate": self.win_rate,  # may be None — never a fake 60% guarantee
            "available": True,
            "guarantee_claimed": False,
            "display_count": (
                "UNAVAILABLE"
                if self.similar_case_count is None
                else str(self.similar_case_count)
            ),
        }


def map_uxa_lifecycle_to_member(uxa_status: str) -> str:
    """Map UX-A decision_lifecycle_status into member experience states."""
    mapping = {
        "OBSERVING": "OBSERVING",
        "EVIDENCE_REVIEW": "RISK_REVIEW",
        "DECIDING": "AI_ANALYZING",
        "MONITORING": "MANAGING",
        "OUTCOME_REVIEW": "EXITED",
        "CLOSED": "EXITED",
        "ABSTAINED": "ABSTAINED",
        "UNAVAILABLE": "UNAVAILABLE",
    }
    return mapping.get((uxa_status or "").upper(), "UNAVAILABLE")


def map_member_posture_to_uxa(posture: str) -> str:
    mapping = {
        "LONG": "RECOMMEND",
        "SHORT": "RECOMMEND",
        "WAIT": "WAIT",
        "ABSTAIN": "ABSTAIN",
    }
    return mapping.get((posture or "").upper(), "UNAVAILABLE")


def intelligence_block_from_experience(
    *,
    schema_version: str,
    symbol: str,
    decision_id: str,
    regime: RegimeProbabilitiesDto,
    regime_label: str,
    posture: str,
    why_suggested: list[str],
    supporting: list[EvidenceItemDto],
    contradicting: list[EvidenceItemDto],
    uncertainty_band: str,
    abstention_reason: str | None,
    strategy_expert_label: str,
    lesson_applied_label: str,
    similar: SimilarCaseSummaryDto,
    data_freshness: str,
    uxa_lifecycle: str,
    as_of: str,
    retrieved_at: str,
) -> dict[str, Any]:
    """Build a UX-A-compatible nested intelligence object."""
    return {
        "schema_version": schema_version,
        "symbol": symbol,
        "decision_id": decision_id,
        "regime_probabilities": regime.to_public_dict(),
        "regime_label": regime_label,
        "ai_recommendation_state": map_member_posture_to_uxa(posture),
        "ai_recommendation_message": "; ".join(why_suggested) if why_suggested else "",
        "supporting_evidence": [e.to_public_dict() for e in supporting],
        "contradicting_evidence": [e.to_public_dict() for e in contradicting],
        "uncertainty": None if uncertainty_band == "UNAVAILABLE" else 0.5,
        "uncertainty_band": uncertainty_band,
        "abstention_reason": abstention_reason,
        "abstention_code": "ABSTAIN" if abstention_reason else None,
        "strategy_expert_label": strategy_expert_label,
        "lesson_applied_label": lesson_applied_label,
        "similar_case_summary": similar.to_public_dict(),
        "data_freshness": data_freshness,
        "freshness_state": data_freshness,
        "decision_lifecycle_status": uxa_lifecycle,
        "as_of": as_of,
        "retrieved_at": retrieved_at,
        "stale_indicator": data_freshness == "STALE",
        "unavailable_indicator": data_freshness == "UNAVAILABLE",
        "raw_memory_graph": False,
        "private_fields_included": False,
        "private_core_import_count": 0,
        "data_class": "PUBLIC_SAFE",
        "environment": "STAGING",
        "availability": "UNAVAILABLE" if data_freshness == "UNAVAILABLE" else "AVAILABLE",
    }
