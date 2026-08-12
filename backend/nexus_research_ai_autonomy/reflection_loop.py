"""Async reflection loop + PIT counterfactuals + WAIT/BLOCK horizon eval."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_autonomy.process_classification import classify_completed_trade
from backend.nexus_research_ai_autonomy.constants import ERROR_ONTOLOGY


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class ReflectionRecord:
    reflection_id: str
    decision_id: str
    symbol: str
    process_class: str
    error_classes: list[str]
    what_happened: str
    why: str
    process_notes: dict[str, Any]
    counterfactuals: list[dict[str, Any]] = field(default_factory=list)
    lesson_candidate: dict[str, Any] | None = None
    provenance: str = "RESEARCH_AI_DEMO"
    transport_tag: str = "LOCAL_SIMULATION"  # REAL | LOCAL_SIMULATION
    async_completed: bool = True
    created_at_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HorizonEvaluation:
    decision_id: str
    original_verdict: str  # WAIT | BLOCK | REJECT
    horizon_sec: int
    market_move_pct: float
    classification: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _infer_error_classes(process_evidence: dict[str, Any], process_class: str) -> list[str]:
    errors: list[str] = []
    if process_evidence.get("data_quality_results", {}).get("status") in {"FAIL", "STALE", "INVALID"}:
        errors.append("DATA_ERROR")
    if "REGIME" in str(process_evidence.get("rule_violation_ids") or []).upper() or process_evidence.get("regime_mismatch"):
        errors.append("REGIME_ERROR")
    if process_evidence.get("strategy_mismatch"):
        errors.append("STRATEGY_ERROR")
    if process_evidence.get("timing_error"):
        errors.append("TIMING_ERROR")
    if process_evidence.get("execution_issue"):
        errors.append("EXECUTION_ERROR")
    if str((process_evidence.get("risk_gate_results") or {}).get("status") or "").upper() in {"FAIL", "BLOCKED"}:
        errors.append("RISK_ERROR")
    if process_evidence.get("ai_reasoning_issue"):
        errors.append("AI_REASONING_ERROR")
    if process_class.startswith("GOOD_PROCESS") and not errors:
        errors.append("UNAVOIDABLE_MARKET_OUTCOME")
    # Validate against ontology
    return [e for e in errors if e in ERROR_ONTOLOGY]


def build_pit_counterfactuals(
    *,
    lifecycle: dict[str, Any],
    pit_market_path: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bounded counterfactuals using only point-in-time available info."""
    cfs: list[dict[str, Any]] = []
    entry_px = float(lifecycle.get("entry_price") or 0.0)
    exit_px = float(lifecycle.get("exit_price") or 0.0)
    side = str(lifecycle.get("side") or "").upper()
    if not pit_market_path or entry_px <= 0:
        return [
            {
                "type": "no_trade",
                "hypothetical_pnl_pct": 0.0,
                "note": "would_have_zero_if_abstained",
                "pit_only": True,
            }
        ]

    # no trade
    cfs.append({"type": "no_trade", "hypothetical_pnl_pct": 0.0, "pit_only": True})

    # later entry: use second available PIT price after decision
    if len(pit_market_path) >= 2:
        later = float(pit_market_path[1].get("price") or 0.0)
        if later > 0 and exit_px > 0:
            if side == "LONG":
                hp = (exit_px - later) / later * 100.0
            else:
                hp = (later - exit_px) / later * 100.0
            cfs.append({"type": "later_entry", "hypothetical_pnl_pct": hp, "pit_only": True})

    # earlier exit: mid-path price
    mid = pit_market_path[len(pit_market_path) // 2]
    mid_px = float(mid.get("price") or 0.0)
    if mid_px > 0 and entry_px > 0:
        if side == "LONG":
            hp = (mid_px - entry_px) / entry_px * 100.0
        else:
            hp = (entry_px - mid_px) / entry_px * 100.0
        cfs.append({"type": "earlier_exit", "hypothetical_pnl_pct": hp, "pit_only": True})

    # risk block alternative
    cfs.append(
        {
            "type": "risk_block",
            "hypothetical_pnl_pct": 0.0,
            "note": "if_research_risk_blocked_entry",
            "pit_only": True,
        }
    )
    return cfs


class ReflectionLoop:
    """Run after every completed lifecycle asynchronously (non-blocking API)."""

    def __init__(self) -> None:
        self.reflections: list[ReflectionRecord] = []
        self.horizon_evals: list[HorizonEvaluation] = []
        self._pending: list[dict[str, Any]] = []

    def enqueue_lifecycle(self, lifecycle: dict[str, Any]) -> None:
        self._pending.append(dict(lifecycle))

    def drain_async(self) -> list[ReflectionRecord]:
        """Process pending reflections (call from worker / after cycle)."""
        done: list[ReflectionRecord] = []
        while self._pending:
            life = self._pending.pop(0)
            rec = self.reflect_lifecycle(life)
            done.append(rec)
        return done

    def reflect_lifecycle(self, lifecycle: dict[str, Any]) -> ReflectionRecord:
        pnl = lifecycle.get("pnl_pct")
        process_evidence = dict(lifecycle.get("process_evidence") or {})
        process_class = classify_completed_trade(pnl=pnl if pnl is not None else None, process_evidence=process_evidence)
        errors = _infer_error_classes(process_evidence, process_class)
        cfs = build_pit_counterfactuals(
            lifecycle=lifecycle,
            pit_market_path=list(lifecycle.get("pit_market_path") or []),
        )
        lesson_candidate = None
        if process_class.startswith("BAD_PROCESS") and errors and errors[0] != "UNAVOIDABLE_MARKET_OUTCOME":
            lesson_candidate = {
                "status": "LESSON_CANDIDATE",
                "error_class": errors[0],
                "symbol": lifecycle.get("symbol"),
                "strategy_family": lifecycle.get("strategy_family"),
                "regime": lifecycle.get("regime"),
                "summary": f"{process_class}:{errors[0]}",
                "active": False,
                "from_live_demo": True,
                "firewall_required": True,
            }

        rec = ReflectionRecord(
            reflection_id=f"ref_{int(time.time()*1000)}_{len(self.reflections)}",
            decision_id=str(lifecycle.get("decision_id") or ""),
            symbol=str(lifecycle.get("symbol") or ""),
            process_class=process_class,
            error_classes=errors,
            what_happened=str(lifecycle.get("exit_reason") or "closed"),
            why=str(process_evidence.get("why") or process_class),
            process_notes={
                "regime_diagnosis": process_evidence.get("regime_diagnosis"),
                "strategy_selection": process_evidence.get("strategy_selection"),
                "direction": process_evidence.get("direction"),
                "entry_timing": process_evidence.get("entry_timing"),
                "execution_quality": process_evidence.get("execution_quality"),
                "position_management": process_evidence.get("position_management"),
                "exit": process_evidence.get("exit"),
                "risk_discipline": process_evidence.get("risk_discipline"),
            },
            counterfactuals=cfs,
            lesson_candidate=lesson_candidate,
            provenance=str(lifecycle.get("execution_purpose") or lifecycle.get("provenance") or "RESEARCH_AI_DEMO"),
            transport_tag=str(
                lifecycle.get("transport_tag")
                or (
                    "REAL"
                    if lifecycle.get("transport_mode") == "BYBIT_DEMO_REAL_TRANSPORT"
                    else "LOCAL_SIMULATION"
                )
            ),
        )
        self.reflections.append(rec)
        return rec

    def evaluate_non_trade_horizon(
        self,
        *,
        decision_id: str,
        verdict: str,
        market_move_pct: float,
        horizon_sec: int = 3600,
        ai_wanted_side: str | None = None,
    ) -> HorizonEvaluation:
        v = str(verdict).upper()
        move = float(market_move_pct)
        classification = "uncertain"
        notes = ""
        if v in {"BLOCK", "REJECT"}:
            if ai_wanted_side == "LONG" and move > 1.0:
                classification = "over_conservative_rejection"
                notes = "blocked_but_market_rallied"
            elif ai_wanted_side == "SHORT" and move < -1.0:
                classification = "over_conservative_rejection"
                notes = "blocked_but_market_dropped"
            elif ai_wanted_side == "LONG" and move < -1.0:
                classification = "correct_rejection"
                notes = "blocked_long_then_drop"
            elif ai_wanted_side == "SHORT" and move > 1.0:
                classification = "correct_rejection"
                notes = "blocked_short_then_rally"
            elif abs(move) < 0.3:
                classification = "lucky_rejection"
                notes = "flat_after_block"
            else:
                classification = "uncertain"
        elif v == "WAIT":
            if abs(move) > 2.0:
                classification = "bad_avoided_trade" if (
                    (ai_wanted_side == "LONG" and move > 2.0) or (ai_wanted_side == "SHORT" and move < -2.0)
                ) else "correct_wait_or_uncertain"
                if classification != "bad_avoided_trade":
                    # WAIT while market moved against a latent side bias
                    if (ai_wanted_side == "LONG" and move < -2.0) or (ai_wanted_side == "SHORT" and move > 2.0):
                        classification = "correct_rejection"
                        notes = "wait_avoided_adverse_move"
                    else:
                        notes = "large_move_after_wait"
            else:
                classification = "uncertain"
                notes = "small_move_after_wait"

        ev = HorizonEvaluation(
            decision_id=decision_id,
            original_verdict=v,
            horizon_sec=horizon_sec,
            market_move_pct=move,
            classification=classification,
            notes=notes,
        )
        self.horizon_evals.append(ev)
        return ev
