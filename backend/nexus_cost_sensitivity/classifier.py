"""Research-only labels for cost/execution sensitivity — never qualification claims."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from backend.nexus_cost_sensitivity.constants import (
    ALLOWED_LABELS,
    BANNED_CLAIM_FRAGMENTS,
    FRAGILITY_COST_DESTROY_THRESHOLD,
)

MIN_SAMPLE_TRADES = 16


def _assert_label_legal(label: str) -> str:
    if label not in ALLOWED_LABELS:
        raise AssertionError(f"illegal_cost_sensitivity_label={label}")
    upper = label.upper()
    for frag in BANNED_CLAIM_FRAGMENTS:
        if frag in upper:
            raise AssertionError(f"banned_fragment={frag}_in_{label}")
    return label


def classify_candidate(result: dict[str, Any]) -> str:
    if result.get("data_quality_blocked"):
        return _assert_label_legal("DATA_QUALITY_BLOCKED")

    trade_count = int(result.get("sample_trade_count") or result.get("trade_count") or 0)
    if trade_count < MIN_SAMPLE_TRADES:
        return _assert_label_legal("INSUFFICIENT_SAMPLE")

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
        return _assert_label_legal("COST_SENSITIVITY_OBSERVED")

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
        status = str(c.get("status") or "")
        if status.upper() in {"QUALIFIED", "PROMOTION_READY", "OOS_PASS", "DEMO_READY"}:
            raise AssertionError(f"forbidden_status={status}")
    return 0
