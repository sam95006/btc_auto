"""Synthetic fixtures for V17-F Data Trust Engine V2."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def _base(**overrides: Any) -> dict[str, Any]:
    payload = {
        "case_id": "BASE_TRUSTED",
        "symbol": "BTCUSDT",
        "source_id": "bybit_public_kline",
        "freshness": 0.95,
        "completeness": 0.97,
        "cross_source_agreement": 0.92,
        "schema_validity": 1.0,
        "timestamp_integrity": 1.0,
        "revision_uncertainty": 0.05,
        "license_status": "APPROVED_PUBLIC",
        "market_coverage": 0.90,
        "microstructure_availability": 0.88,
        "anomaly_rate": 0.02,
        "ai_confidence": 0.80,
        "availability": True,
        "notes": "healthy_baseline",
    }
    payload.update(overrides)
    return payload


def fixture_catalog() -> list[dict[str, Any]]:
    """Deterministic catalog covering founder-required behaviors."""
    return [
        _base(case_id="TRUSTED_HEALTHY"),
        _base(
            case_id="USABLE_WITH_LIMITS_FRESHNESS",
            freshness=0.72,
            notes="freshness_limits_band",
        ),
        _base(
            case_id="DEGRADED_SCHEMA",
            schema_validity=0.60,
            ai_confidence=0.99,
            notes="degraded_despite_ai_99",
        ),
        _base(
            case_id="DEGRADED_MULTI_CHANNEL",
            freshness=0.55,
            completeness=0.60,
            anomaly_rate=0.40,
            market_coverage=0.25,
            ai_confidence=0.99,
            notes="severe_degraded_abstain",
        ),
        _base(
            case_id="STALE_FRESHNESS",
            freshness=0.20,
            ai_confidence=0.99,
            notes="stale_blocks",
        ),
        _base(
            case_id="CONFLICTED_SOURCES",
            cross_source_agreement=0.30,
            ai_confidence=0.99,
            notes="cross_source_conflict",
        ),
        _base(
            case_id="LICENSE_BLOCKED_REVIEW",
            license_status="LICENSE_REVIEW_REQUIRED",
            ai_confidence=0.99,
            notes="license_review_blocks",
        ),
        _base(
            case_id="LICENSE_BLOCKED_UNKNOWN",
            license_status="UNKNOWN",
            ai_confidence=0.99,
            notes="license_unknown_blocks",
        ),
        _base(
            case_id="UNAVAILABLE_COMPLETENESS",
            completeness=0.05,
            ai_confidence=0.99,
            notes="near_empty_unavailable",
        ),
        _base(
            case_id="UNAVAILABLE_FLAG",
            availability=False,
            ai_confidence=0.99,
            notes="availability_false",
        ),
        _base(
            case_id="DOMINANCE_DEGRADED_AI99",
            timestamp_integrity=0.50,
            ai_confidence=0.99,
            notes="trust_dominates_ai_confidence",
        ),
    ]


def expected_trust_status(case: dict[str, Any]) -> str | None:
    """Optional expected status hints for catalog cases (None = engine-decided)."""
    hints = {
        "TRUSTED_HEALTHY": "TRUSTED",
        "USABLE_WITH_LIMITS_FRESHNESS": "USABLE_WITH_LIMITS",
        "DEGRADED_SCHEMA": "DEGRADED",
        "DEGRADED_MULTI_CHANNEL": "DEGRADED",
        "STALE_FRESHNESS": "STALE",
        "CONFLICTED_SOURCES": "CONFLICTED",
        "LICENSE_BLOCKED_REVIEW": "LICENSE_BLOCKED",
        "LICENSE_BLOCKED_UNKNOWN": "LICENSE_BLOCKED",
        "UNAVAILABLE_COMPLETENESS": "UNAVAILABLE",
        "UNAVAILABLE_FLAG": "UNAVAILABLE",
        "DOMINANCE_DEGRADED_AI99": "DEGRADED",
    }
    return hints.get(str(case.get("case_id")))


def clone_case(case: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    out = deepcopy(case)
    out.update(overrides)
    return out
