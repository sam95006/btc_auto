"""Structured lesson-candidate similarity for P2 RepeatMistakeGuard qualification."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.nexus_demo_execution.p2_run8_learning_closure import _fee_drag_lesson_matches

SIMILARITY_THRESHOLD = 0.75

_FEATURE_WEIGHTS: dict[str, float] = {
    "symbol_match": 0.30,
    "side_match": 0.15,
    "fee_drag_pattern": 0.30,
    "mistake_type_match": 0.15,
    "signal_family_match": 0.10,
}


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fee_dominated(candidate: dict[str, Any]) -> bool:
    fees = candidate.get("round_trip_fee_estimate")
    expected = candidate.get("expected_gross_pnl")
    if expected in (None, "", "UNKNOWN") or fees in (None, "", "UNKNOWN"):
        return False
    fee_value = _dec(fees)
    return fee_value > 0 and _dec(expected) <= fee_value


def score_candidate_against_lesson(candidate: dict[str, Any], lesson: dict[str, Any]) -> dict[str, Any]:
    """Deterministic structured similarity — no LLM prose."""
    lesson_symbol = _text(lesson.get("symbol"))
    candidate_symbol = _text(candidate.get("symbol"))
    lesson_side = _text(lesson.get("side"))
    candidate_side = _text(candidate.get("side"))
    primary = _text(lesson.get("primary_mistake"))
    candidate_type = _text(candidate.get("lesson_type") or ("FEE_DRAG" if _fee_dominated(candidate) else ""))

    symbol_match = bool(
        lesson_symbol and candidate_symbol and lesson_symbol.upper() == candidate_symbol.upper()
    )
    side_match = bool(lesson_side and candidate_side and lesson_side.lower() == candidate_side.lower())
    fee_drag_pattern = primary == "FEE_DRAG" and _fee_dominated(candidate)
    mistake_type_match = bool(primary and candidate_type and primary == candidate_type)
    signal_family_match = _text(candidate.get("signal_family")) == _text(
        (lesson.get("payload") or {}).get("signal_family") or "UNKNOWN"
    ) and _text(candidate.get("signal_family")) != "UNKNOWN"

    components = {
        "symbol_match": 1.0 if symbol_match else 0.0,
        "side_match": 1.0 if side_match else 0.0,
        "fee_drag_pattern": 1.0 if fee_drag_pattern else 0.0,
        "mistake_type_match": 1.0 if mistake_type_match else 0.0,
        "signal_family_match": 1.0 if signal_family_match else 0.0,
    }
    score = round(sum(components[key] * _FEATURE_WEIGHTS[key] for key in _FEATURE_WEIGHTS), 4)
    guard_match = _fee_drag_lesson_matches(candidate, lesson)
    matched = bool(guard_match and score >= SIMILARITY_THRESHOLD)
    return {
        "similarity_score": score,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "similarity_components": components,
        "guard_match": guard_match,
        "matched": matched,
        "matched_lesson_id": lesson.get("lesson_id") if matched else None,
        "matched_source_evidence_hash": lesson.get("source_evidence_hash") if matched else None,
    }


def build_similar_candidate_from_lesson(lesson: dict[str, Any]) -> dict[str, Any]:
    payload = lesson.get("payload") or {}
    reflection = payload.get("reflection") or {}
    fee_total = reflection.get("fee_total") or "0.07071042"
    return {
        "symbol": lesson.get("symbol"),
        "side": lesson.get("side"),
        "lesson_type": lesson.get("primary_mistake") or "FEE_DRAG",
        "expected_gross_pnl": "0",
        "round_trip_fee_estimate": str(fee_total),
        "confidence": 0.62,
        "signal_family": "P1_QUALIFICATION_ROUND_TRIP",
        "market_regime": "STAGING_SIDEWAYS",
        "horizon": "INTRADAY",
    }


def build_dissimilar_control_candidate(lesson: dict[str, Any]) -> dict[str, Any]:
    similar = build_similar_candidate_from_lesson(lesson)
    return {
        **similar,
        "symbol": "ETHUSDT",
        "lesson_type": "FEE_DRAG",
        "signal_family": "UNRELATED_CONTROL",
        "market_regime": "STAGING_TREND",
    }
