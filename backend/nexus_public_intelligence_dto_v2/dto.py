"""Staging fixtures and builders for Public Intelligence DTO V2."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.nexus_public_intelligence_dto_v2.constants import SCHEMA_VERSION
from backend.nexus_public_intelligence_dto_v2.models import (
    EvidenceItemDto,
    PublicIntelligenceDtoV2,
    RegimeProbabilitiesDto,
    SimilarCaseSummaryDto,
)
from backend.nexus_public_intelligence_dto_v2.sanitize import (
    assert_allowlisted_only,
    serialize_allowlist,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_fixture_dto(
    *,
    symbol: str = "BTCUSDT",
    decision_id: str = "pub_dec_fixture_001",
    ai_recommendation_state: str = "HOLD",
    decision_lifecycle_status: str = "MONITORING",
    abstention_reason: str | None = None,
) -> PublicIntelligenceDtoV2:
    now = utc_now_iso()
    supporting = (
        EvidenceItemDto(
            evidence_summary="Public momentum alignment across short horizons",
            evidence_polarity="SUPPORTING",
            evidence_freshness="FRESH",
            source_label="PUBLIC_MARKET",
            as_of=now,
        ),
        EvidenceItemDto(
            evidence_summary="Liquidity conditions remain orderly",
            evidence_polarity="SUPPORTING",
            evidence_freshness="FRESH",
            source_label="PUBLIC_MARKET",
            as_of=now,
        ),
    )
    contradicting = (
        EvidenceItemDto(
            evidence_summary="Elevated event-risk window approaching",
            evidence_polarity="CONTRADICTING",
            evidence_freshness="FRESH",
            source_label="PUBLIC_CALENDAR",
            as_of=now,
        ),
    )
    return PublicIntelligenceDtoV2(
        schema_version=SCHEMA_VERSION,
        symbol=symbol,
        decision_id=decision_id,
        regime_probabilities=RegimeProbabilitiesDto(
            strong_bull_probability=0.41,
            strong_bear_probability=0.22,
            volatility_expansion_probability=0.35,
            liquidity_stress_probability=0.18,
            long_crowding_probability=0.27,
            correlation_breakdown_probability=0.12,
            event_risk_probability=0.31,
            regime_transition_probability=0.24,
            regime_confidence=0.62,
            regime_freshness="FRESH",
        ),
        ai_recommendation_state=ai_recommendation_state,
        ai_recommendation_message="Public HOLD — conflicting evidence present",
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        uncertainty=0.48,
        uncertainty_band="MEDIUM",
        abstention_reason=abstention_reason,
        abstention_code="EVENT_RISK_ELEVATED" if abstention_reason else None,
        strategy_expert_label="DEFENSIVE_NO_TRADE",
        lesson_applied_label="LESSON_APPLIED",
        similar_case_summary=SimilarCaseSummaryDto(
            similar_case_summary="3 similar public cases favored wait under elevated event risk",
            similar_case_count=3,
            similar_case_overlap_band="MEDIUM",
        ),
        data_freshness="FRESH",
        freshness_state="FRESH",
        decision_lifecycle_status=decision_lifecycle_status,
        as_of=now,
        retrieved_at=now,
        published_at=now,
        lineage_id=str(uuid4()),
        environment="STAGING",
        availability="AVAILABLE",
        regime_label="MIXED",
        citation_count=3,
        stale_indicator=False,
        unavailable_indicator=False,
        private_core_import_count=0,
        raw_memory_graph=False,
        private_fields_included=False,
    )


def build_abstain_fixture() -> PublicIntelligenceDtoV2:
    return build_fixture_dto(
        decision_id="pub_dec_fixture_abstain_001",
        ai_recommendation_state="ABSTAIN",
        decision_lifecycle_status="ABSTAINED",
        abstention_reason="Uncertainty and contradicting public evidence exceed safe publish band",
    )


def publish_public_intelligence_dto(dto: PublicIntelligenceDtoV2 | None = None) -> dict[str, Any]:
    """Serialize a public-safe intelligence DTO (allow-list enforced)."""
    obj = dto or build_fixture_dto()
    payload = obj.to_public_dict()
    filtered = serialize_allowlist(payload)
    assert_allowlisted_only(filtered)
    if filtered.get("private_core_import_count", 0) != 0:
        raise RuntimeError("private_core_import_count_must_be_0")
    if filtered.get("raw_memory_graph") is not False:
        raise RuntimeError("raw_memory_graph_must_be_false")
    return filtered


REQUIRED_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "schema_version",
    "regime_probabilities",
    "ai_recommendation_state",
    "supporting_evidence",
    "contradicting_evidence",
    "uncertainty",
    "abstention_reason",
    "strategy_expert_label",
    "lesson_applied_label",
    "similar_case_summary",
    "data_freshness",
    "decision_lifecycle_status",
    "private_core_import_count",
)
