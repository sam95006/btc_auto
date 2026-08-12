"""V18.2.28 failure reflection + mistake signatures + CandidateLesson firewall."""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any

FAILURE_ROOT_CAUSES = (
    "WRONG_DIRECTION",
    "FALSE_BREAKOUT",
    "ENTRY_TOO_EARLY",
    "ENTRY_TOO_LATE",
    "REGIME_MISMATCH",
    "LOW_EDGE",
    "COST_DOMINATED",
    "HORIZON_MISMATCH",
    "LIQUIDITY_PROBLEM",
    "EXIT_TOO_EARLY",
    "EXIT_TOO_LATE",
    "STOP_PLACEMENT_ERROR",
    "OTHER",
)

COUNTERFACTUAL_TYPES = (
    "NO_TRADE",
    "OPPOSITE_DIRECTION",
    "LATER_ENTRY",
    "EARLIER_EXIT",
    "LONGER_HOLD",
)


@dataclass
class CandidateLesson:
    lesson_id: str
    pattern: str
    failure_type: str
    affected_strategy: str
    evidence_count: int = 1
    counterexample_count: int = 0
    expected_improvement: str = ""
    risk_of_overfitting: str = "HIGH"
    lifecycle: str = "candidate"
    hindsight_derived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MistakeSignature:
    signature: str
    first_seen_ms: int
    occurrence_count: int = 1
    repeat_after_lesson: int = 0
    loss_total: float = 0.0
    candidate_lesson_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FailureReflection:
    reflection_id: str
    symbol: str
    side: str
    process_class: str
    net_realized: float
    entry_quality: str
    direction_quality: str
    timing_quality: str
    regime_fit: str
    strategy_family_fit: str
    liquidity_fit: str
    cost_fit: str
    horizon_fit: str
    exit_quality: str
    root_causes: list[str] = field(default_factory=list)
    counterfactuals: list[dict[str, Any]] = field(default_factory=list)
    candidate_lesson: CandidateLesson | None = None
    mistake_signature: str | None = None
    hindsight_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.candidate_lesson:
            d["candidate_lesson"] = self.candidate_lesson.to_dict()
        return d


def _sig_hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def infer_root_causes(lifecycle: dict[str, Any], exit_quality_class: str) -> list[str]:
    causes: list[str] = []
    net = float((lifecycle.get("exact_pnl_accounting") or {}).get("calculated_net_pnl") or 0)
    fees = float((lifecycle.get("exact_pnl_accounting") or {}).get("total_fees") or 0)
    mfe = float((lifecycle.get("path_excursion") or {}).get("mfe_usdt") or 0)
    regime = str(lifecycle.get("regime_at_entry") or "")
    exit_q = str(exit_quality_class or "")

    if net < 0 and mfe <= 0:
        causes.append("WRONG_DIRECTION")
    if "EARLY" in exit_q.upper():
        causes.append("EXIT_TOO_EARLY")
    if "LATE" in exit_q.upper() or "LOW_CAPTURE" in exit_q.upper():
        causes.append("EXIT_TOO_LATE")
    if regime.upper() in {"RANGE", "CHOP"} and lifecycle.get("strategy_family") == "TREND":
        causes.append("REGIME_MISMATCH")
    if net < 0 and abs(fees) >= abs(net) * 0.5:
        causes.append("COST_DOMINATED")
    if lifecycle.get("activity_score", 1.0) < 0.4:
        causes.append("LOW_EDGE")
    if not causes:
        causes.append("OTHER")
    return [c for c in causes if c in FAILURE_ROOT_CAUSES]


def build_mistake_signature(root_causes: list[str], lifecycle: dict[str, Any]) -> str:
    regime = str(lifecycle.get("regime_at_entry") or "UNKNOWN").upper()
    strat = str(lifecycle.get("strategy_family") or "TREND")
    primary = root_causes[0] if root_causes else "OTHER"
    if primary == "REGIME_MISMATCH" and strat == "TREND":
        return f"TREND_{lifecycle.get('side', 'LONG')}_IN_{regime}"
    if primary == "FALSE_BREAKOUT":
        return "FALSE_BREAKOUT_LOW_ACTIVITY"
    if primary == "ENTRY_TOO_LATE" and lifecycle.get("side") == "SHORT":
        return "LATE_SHORT_AFTER_EXHAUSTION"
    return f"{primary}_{strat}_{regime}"


def build_counterfactuals_hindsight(lifecycle: dict[str, Any]) -> list[dict[str, Any]]:
    """Retrospective only — clearly labeled hindsight."""
    cfs: list[dict[str, Any]] = []
    side = str(lifecycle.get("side") or "LONG").upper()
    net = float((lifecycle.get("exact_pnl_accounting") or {}).get("calculated_net_pnl") or 0)
    cfs.append({"type": "NO_TRADE", "hypothetical_pnl": 0.0, "hindsight_derived": True})
    opp = "SHORT" if side == "LONG" else "LONG"
    cfs.append({"type": "OPPOSITE_DIRECTION", "side": opp, "hindsight_derived": True, "note": "research_only"})
    if net < 0:
        cfs.append({"type": "EARLIER_EXIT", "hindsight_derived": True, "note": "would_reduce_loss_research"})
    return cfs


def create_failure_reflection(
    lifecycle: dict[str, Any],
    *,
    process_class: str,
    exit_quality_class: str,
) -> FailureReflection | None:
    net = float((lifecycle.get("exact_pnl_accounting") or {}).get("calculated_net_pnl") or 0)
    is_loss = net < 0
    is_bad_win = process_class == "BAD_PROCESS_WIN"
    if not is_loss and not is_bad_win:
        return None

    root = infer_root_causes(lifecycle, exit_quality_class)
    sig = build_mistake_signature(root, lifecycle)
    rid = f"refl_{_sig_hash([lifecycle.get('symbol', ''), str(int(time.time()))])}"

    lesson = None
    if "REGIME_MISMATCH" in root:
        lesson = CandidateLesson(
            lesson_id=f"lesson_{rid[:12]}",
            pattern=f"avoid_trend_continuation_in_{lifecycle.get('regime_at_entry', 'RANGE')}",
            failure_type="REGIME_MISMATCH",
            affected_strategy=str(lifecycle.get("strategy_family") or "TREND"),
            expected_improvement="reduce_false_trend_entries_in_range",
            risk_of_overfitting="MEDIUM",
            lifecycle="candidate",
        )

    return FailureReflection(
        reflection_id=rid,
        symbol=str(lifecycle.get("symbol") or ""),
        side=str(lifecycle.get("side") or ""),
        process_class=process_class,
        net_realized=net,
        entry_quality="POOR" if "ENTRY_TOO" in str(root) else "MIXED",
        direction_quality="POOR" if "WRONG_DIRECTION" in root else "MIXED",
        timing_quality="POOR" if any("ENTRY_TOO" in r for r in root) else "MIXED",
        regime_fit="POOR" if "REGIME_MISMATCH" in root else "MIXED",
        strategy_family_fit="POOR" if "REGIME_MISMATCH" in root else "ACCEPTABLE",
        liquidity_fit="POOR" if "LIQUIDITY" in str(root) else "ACCEPTABLE",
        cost_fit="POOR" if "COST_DOMINATED" in root else "ACCEPTABLE",
        horizon_fit="POOR" if "HORIZON" in str(root) else "ACCEPTABLE",
        exit_quality=exit_quality_class or "UNKNOWN",
        root_causes=root,
        counterfactuals=build_counterfactuals_hindsight(lifecycle),
        candidate_lesson=lesson,
        mistake_signature=sig,
        hindsight_fields=["counterfactuals"],
    )


def aggregate_reflection_stats(reflections: list[FailureReflection]) -> dict[str, Any]:
    root_counts: dict[str, int] = {r: 0 for r in FAILURE_ROOT_CAUSES}
    sigs: dict[str, MistakeSignature] = {}
    lessons: list[dict[str, Any]] = []
    for refl in reflections:
        for rc in refl.root_causes:
            root_counts[rc] = root_counts.get(rc, 0) + 1
        if refl.mistake_signature:
            s = sigs.get(refl.mistake_signature)
            if s:
                s.occurrence_count += 1
                s.loss_total += min(0.0, refl.net_realized)
            else:
                sigs[refl.mistake_signature] = MistakeSignature(
                    signature=refl.mistake_signature,
                    first_seen_ms=int(time.time() * 1000),
                    loss_total=min(0.0, refl.net_realized),
                    candidate_lesson_id=refl.candidate_lesson.lesson_id if refl.candidate_lesson else None,
                )
        if refl.candidate_lesson:
            lessons.append(refl.candidate_lesson.to_dict())

    return {
        "reflections": len(reflections),
        "wrong_direction": root_counts.get("WRONG_DIRECTION", 0),
        "false_breakout": root_counts.get("FALSE_BREAKOUT", 0),
        "entry_too_early": root_counts.get("ENTRY_TOO_EARLY", 0),
        "entry_too_late": root_counts.get("ENTRY_TOO_LATE", 0),
        "regime_mismatch": root_counts.get("REGIME_MISMATCH", 0),
        "cost_dominated": root_counts.get("COST_DOMINATED", 0),
        "exit_too_early": root_counts.get("EXIT_TOO_EARLY", 0),
        "exit_too_late": root_counts.get("EXIT_TOO_LATE", 0),
        "candidate_lessons": len(lessons),
        "validated_lessons": 0,
        "activated_lessons": 0,
        "repeated_mistake_signatures": [s.to_dict() for s in sigs.values()],
        "repeat_after_validated_lesson": sum(s.repeat_after_lesson for s in sigs.values()),
        "lesson_candidates": lessons,
    }
