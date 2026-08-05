"""Discovery labels — development-only; never emits qualified/profitability claims."""
from __future__ import annotations

from collections import Counter
from typing import Any

from backend.nexus_strategy_discovery_factory_v3.constants import (
    ALLOWED_LABELS,
    BANNED_LABEL_FRAGMENTS,
    COST_DESTROY_RATIO,
    MIN_SAMPLE_TRADES,
    REGIME_FRAGILITY_SHARE,
)


def _assert_label_legal(label: str) -> str:
    if label not in ALLOWED_LABELS:
        raise AssertionError(f"illegal_discovery_label={label}")
    upper = label.upper()
    # QUALIFIED substring appears inside DEVELOPMENT_PROMISING_NOT_QUALIFIED — that is allowed.
    for frag in BANNED_LABEL_FRAGMENTS:
        if frag == "QUALIFIED":
            if label.endswith("_QUALIFIED") and "NOT_QUALIFIED" not in label:
                raise AssertionError(f"banned_qualified_claim_label={label}")
            continue
        if frag in upper and frag not in {"QUALIFIED"}:
            raise AssertionError(f"banned_fragment={frag}_in_{label}")
    return label


def classify_candidate(result: dict[str, Any]) -> str:
    """Map measured development evidence to an allowed research label."""
    if result.get("data_quality_blocked"):
        return _assert_label_legal("DATA_QUALITY_BLOCKED")
    if result.get("implementation_rejected"):
        return _assert_label_legal("REJECTED")

    trade_count = int(result.get("trade_count") or 0)
    if trade_count < MIN_SAMPLE_TRADES:
        return _assert_label_legal("INSUFFICIENT_SAMPLE")

    gross = float(result.get("gross_pnl") or 0.0)
    net = float(result.get("net_pnl") or 0.0)

    stability = result.get("stability_measures") or {}
    fold_pos = int(stability.get("positive_fold_count") or 0)
    fold_n = int(stability.get("fold_count") or 0)
    sign_flip = bool(stability.get("sign_flip_across_folds"))
    research_signal_only = bool(result.get("research_signal_only"))

    # Explicit signal-only research track takes precedence over cost taxonomy.
    if research_signal_only and trade_count >= MIN_SAMPLE_TRADES:
        return _assert_label_legal("RESEARCH_SIGNAL_ONLY")

    # Cost destruction is the primary measured failure when gross edge exists.
    if gross > 0 and net <= 0:
        _ = COST_DESTROY_RATIO
        return _assert_label_legal("RAW_EDGE_PRESENT_BUT_COST_DESTROYED")

    if net > 0 and fold_n > 0 and fold_pos >= max(2, fold_n // 2) and not sign_flip:
        # Development-promising on synthetic folds — NEVER qualified.
        return _assert_label_legal("DEVELOPMENT_PROMISING_NOT_QUALIFIED")

    regime_breakdown = result.get("regime_breakdown") or {}
    if regime_breakdown and trade_count > 0:
        top = max(int(v) for v in regime_breakdown.values())
        if top / trade_count >= REGIME_FRAGILITY_SHARE:
            return _assert_label_legal("REGIME_FRAGILE")

    if gross > 0 and net > 0:
        return _assert_label_legal("RESEARCH_SIGNAL_ONLY")

    if gross <= 0 and net <= 0:
        if abs(gross) < 1e-9 and trade_count >= MIN_SAMPLE_TRADES:
            return _assert_label_legal("RESEARCH_SIGNAL_ONLY")
        return _assert_label_legal("REJECTED")

    return _assert_label_legal("REJECTED")


def label_histogram(candidates: list[dict[str, Any]]) -> dict[str, int]:
    c = Counter(str(x.get("label")) for x in candidates)
    return {k: int(c.get(k, 0)) for k in sorted(ALLOWED_LABELS)}


def enforce_no_qualification(candidates: list[dict[str, Any]]) -> int:
    """Return qualification_ready_count — must remain 0 for V13-C."""
    for c in candidates:
        label = str(c.get("label") or "")
        _assert_label_legal(label)
        if c.get("qualified") is True:
            raise AssertionError("qualified_flag_forbidden")
        if c.get("qualification_ready") is True:
            raise AssertionError("qualification_ready_flag_forbidden")
        status = str(c.get("status") or "")
        if status.upper() in {"QUALIFIED", "PROMOTION_READY", "OOS_PASS"}:
            raise AssertionError(f"forbidden_status={status}")
    return 0
