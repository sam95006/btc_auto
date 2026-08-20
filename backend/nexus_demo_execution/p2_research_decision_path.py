"""Research decision path: candidate → memory → RepeatMistakeGuard → recommendation.

Never a live execution veto. AUTONOMOUS_BYBIT_DEMO_ARM_READY remains HOLD.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.nexus_demo_execution.p2_run8_learning_closure import RepeatMistakeGuard


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def fee_dominated(candidate: dict[str, Any]) -> bool:
    if candidate.get("expected_gross_pnl") in (None, "", "UNKNOWN"):
        return False
    if candidate.get("round_trip_fee_estimate") in (None, "", "UNKNOWN"):
        return False
    fees = _dec(candidate.get("round_trip_fee_estimate"))
    expected = _dec(candidate.get("expected_gross_pnl"))
    return fees > 0 and expected <= fees


def retrieval_context(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "lesson_type": candidate.get("lesson_type") or ("FEE_DRAG" if fee_dominated(candidate) else None),
        "expected_gross_pnl": candidate.get("expected_gross_pnl"),
        "round_trip_fee_estimate": candidate.get("round_trip_fee_estimate"),
        "market_regime": candidate.get("market_regime") or "UNKNOWN",
        "signal_family": candidate.get("signal_family") or "UNKNOWN",
        "horizon": candidate.get("horizon") or "UNKNOWN",
        "fee_dominated": fee_dominated(candidate),
    }


def research_decision_path(market_input: dict[str, Any], *, memory: Any) -> dict[str, Any]:
    candidate = dict(market_input)
    context = retrieval_context(candidate)
    hits = []
    if hasattr(memory, "query_context"):
        hits = memory.query_context(candidate)
    guard = RepeatMistakeGuard(memory)
    guarded = guard.evaluate(candidate)
    recommendation = "RESEARCH_SKIP" if guarded.get("decision_after_learning") == "SKIP" else "RESEARCH_ALLOW"
    if guarded.get("decision_after_learning") == "ALLOW_WITH_PENALTY":
        recommendation = "RESEARCH_DOWNGRADE"
    return {
        "candidate": candidate,
        "retrieval_context": context,
        "memory_hits": hits,
        "guard": guarded,
        "research_recommendation": recommendation,
        "live_execution_veto": False,
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": "HOLD",
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }
