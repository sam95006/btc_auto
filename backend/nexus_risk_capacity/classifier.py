"""Research-only labels for risk/capacity review — never qualification/promotion."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from backend.nexus_risk_capacity.constants import (
    ALLOWED_LABELS,
    BANNED_CLAIM_FRAGMENTS,
    FRAGILITY_COST_DESTROY_THRESHOLD,
)

MIN_SAMPLE_TRADES = 16


def _assert_label_legal(label: str) -> str:
    if label not in ALLOWED_LABELS:
        raise AssertionError(f"illegal_risk_capacity_label={label}")
    upper = label.upper()
    for frag in BANNED_CLAIM_FRAGMENTS:
        if frag in upper:
            raise AssertionError(f"banned_fragment={frag}_in_{label}")
    return label


def classify_candidate(result: dict[str, Any]) -> str:
    if result.get("data_quality_blocked") or (
        result.get("data_quality_review") or {}
    ).get("data_quality_blocked"):
        return _assert_label_legal("DATA_QUALITY_BLOCKED")

    trade_count = int(result.get("sample_trade_count") or result.get("trade_count") or 0)
    if trade_count < MIN_SAMPLE_TRADES:
        return _assert_label_legal("INSUFFICIENT_SAMPLE")

    if result.get("_concentration_blocked") or (
        result.get("concentration_review") or {}
    ).get("concentration_blocked"):
        return _assert_label_legal("CONCENTRATION_BLOCKED")

    if result.get("_drawdown_unsafe") or (result.get("drawdown_review") or {}).get(
        "drawdown_assumption_unsafe"
    ):
        return _assert_label_legal("DRAWDOWN_ASSUMPTION_UNSAFE")

    if result.get("_liquidation_unsafe") or (
        result.get("liquidation_distance_review") or {}
    ).get("liquidation_distance_unsafe"):
        return _assert_label_legal("LIQUIDATION_DISTANCE_UNSAFE")

    baseline = result.get("baseline") or {}
    gross = Decimal(str(result.get("_baseline_gross") or baseline.get("gross_pnl") or 0))
    net = Decimal(str(result.get("_baseline_net") or baseline.get("net_pnl") or 0))
    fragility = Decimal(str(result.get("_fragility") or result.get("fragility_score") or 0))
    capacity_limited = bool(
        result.get("_capacity_limited")
        or (result.get("capacity_estimate") or {}).get("capacity_limited")
    )

    if gross > 0 and net <= 0:
        return _assert_label_legal("COST_DESTROYED")

    if fragility >= Decimal(str(FRAGILITY_COST_DESTROY_THRESHOLD)):
        return _assert_label_legal("FRAGILE_TO_EXECUTION")

    if capacity_limited and net > 0:
        return _assert_label_legal("CAPACITY_LIMITED")

    if net > 0:
        return _assert_label_legal("RISK_CAPACITY_OBSERVED")

    return _assert_label_legal("DEVELOPMENT_REVIEW_ONLY")


def label_histogram(candidates: list[dict[str, Any]]) -> dict[str, int]:
    c = Counter(str(x.get("label")) for x in candidates)
    return {k: int(c.get(k, 0)) for k in sorted(ALLOWED_LABELS)}


def enforce_no_qualification(candidates: list[dict[str, Any]]) -> int:
    for c in candidates:
        label = str(c.get("label") or "")
        _assert_label_legal(label)
        if c.get("qualified") is True:
            raise AssertionError("qualified_flag_forbidden")
        if c.get("qualification_ready") is True:
            raise AssertionError("qualification_ready_flag_forbidden")
        if c.get("profitability_claimed") is True:
            raise AssertionError("profitability_claimed_forbidden")
        if c.get("strategy_promoted") is True:
            raise AssertionError("strategy_promoted_forbidden")
        if c.get("strategy_selected") is True:
            raise AssertionError("strategy_selected_forbidden")
        if c.get("ai_override_applied") is True:
            raise AssertionError("ai_override_applied_forbidden")
        status = str(c.get("status") or "")
        if status.upper() in {
            "QUALIFIED",
            "PROMOTION_READY",
            "PROMOTED",
            "OOS_PASS",
            "DEMO_READY",
        }:
            raise AssertionError(f"forbidden_status={status}")
    return 0
