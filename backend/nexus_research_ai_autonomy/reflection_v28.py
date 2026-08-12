"""V18.2.28 reflection — losses + BAD_PROCESS_WIN with mistake signatures.

CandidateLesson via validation firewall; counterfactuals hindsight-labeled.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_autonomy.process_classification import classify_completed_trade
from backend.nexus_research_ai_autonomy.lesson_firewall_bridge import LessonFirewallBridge
from backend.nexus_research_ai_autonomy.reflection_loop import (
    ReflectionLoop,
    ReflectionRecord,
    build_pit_counterfactuals,
    _infer_error_classes,
)

REFLECTION_V28_SCHEMA = "v18_2_28_reflection_v1"


@dataclass
class MistakeSignature:
    signature_id: str
    process_class: str
    error_class: str
    symbol: str
    side: str
    exit_reason: str
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mistake_signature_id(*, process_class: str, error_class: str, symbol: str, side: str, exit_reason: str) -> str:
    raw = json.dumps(
        {
            "process_class": process_class,
            "error_class": error_class,
            "symbol": symbol,
            "side": side,
            "exit_reason": exit_reason,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class ReflectionV28:
    """Reflection for every loss and BAD_PROCESS_WIN."""

    def __init__(self) -> None:
        self.loop = ReflectionLoop()
        self.firewall = LessonFirewallBridge()
        self.mistake_signatures: dict[str, MistakeSignature] = {}
        self.reflections: list[ReflectionRecord] = []
        self.lesson_candidates: list[dict[str, Any]] = []

    def should_reflect(self, lifecycle: dict[str, Any]) -> bool:
        pnl = _lifecycle_net(lifecycle)
        pe = lifecycle.get("process_evidence") or {}
        pc = lifecycle.get("process_class") or classify_completed_trade(
            pnl=pnl, process_evidence=pe
        )
        if pc == "BAD_PROCESS_WIN":
            return True
        if pnl is not None and float(pnl) < 0:
            return True
        return False

    def reflect_lifecycle(self, lifecycle: dict[str, Any]) -> ReflectionRecord | None:
        if not self.should_reflect(lifecycle):
            return None

        pnl = _lifecycle_net(lifecycle)
        pe = dict(lifecycle.get("process_evidence") or {})
        process_class = lifecycle.get("process_class") or classify_completed_trade(
            pnl=pnl, process_evidence=pe
        )
        errors = _infer_error_classes(pe, process_class)

        failure_roots: list[str] = []
        if process_class.startswith("BAD_PROCESS"):
            failure_roots.append("process_noncompliance")
        if pnl is not None and float(pnl) < 0:
            failure_roots.append("negative_realized_pnl")
        exit_q = lifecycle.get("exit_quality") or {}
        if exit_q.get("exit_quality_class") == "EDGE_EXISTED_EXIT_TOO_EARLY":
            failure_roots.append("premature_exit")
        if exit_q.get("exit_quality_class") == "NO_EDGE_AFTER_ENTRY":
            failure_roots.append("no_edge_after_entry")

        cfs = build_pit_counterfactuals(
            lifecycle=lifecycle,
            pit_market_path=list(lifecycle.get("pit_market_path") or []),
        )
        for cf in cfs:
            cf["hindsight_labeled"] = True
            cf["pit_only"] = True

        rec = self.loop.reflect_lifecycle(lifecycle)
        rec.process_notes = {
            **rec.process_notes,
            "failure_root_causes": failure_roots,
            "exit_quality_class": exit_q.get("exit_quality_class"),
            "MFE_capture_ratio": (lifecycle.get("mfe_capture") or {}).get("MFE_capture_ratio"),
        }

        sig_id = _mistake_signature_id(
            process_class=process_class,
            error_class=errors[0] if errors else "UNKNOWN",
            symbol=str(lifecycle.get("symbol") or ""),
            side=str(lifecycle.get("side") or ""),
            exit_reason=str(lifecycle.get("exit_reason") or ""),
        )
        if sig_id in self.mistake_signatures:
            self.mistake_signatures[sig_id].count += 1
        else:
            self.mistake_signatures[sig_id] = MistakeSignature(
                signature_id=sig_id,
                process_class=process_class,
                error_class=errors[0] if errors else "UNKNOWN",
                symbol=str(lifecycle.get("symbol") or ""),
                side=str(lifecycle.get("side") or ""),
                exit_reason=str(lifecycle.get("exit_reason") or ""),
            )

        lesson_candidate = None
        if process_class.startswith("BAD_PROCESS") or (pnl is not None and float(pnl) < 0):
            lesson_candidate = {
                "status": "LESSON_CANDIDATE",
                "lesson_id": f"LC_{sig_id}",
                "error_class": errors[0] if errors else "UNAVOIDABLE_MARKET_OUTCOME",
                "symbol": lifecycle.get("symbol"),
                "strategy_family": lifecycle.get("strategy_family"),
                "side": lifecycle.get("side"),
                "process_class": process_class,
                "failure_root_causes": failure_roots,
                "mistake_signature_id": sig_id,
                "summary": f"{process_class}:{failure_roots[0] if failure_roots else 'loss'}",
                "active": False,
                "from_live_demo": True,
                "firewall_required": True,
                "validation_firewall": True,
            }
            fw = self.firewall.ingest_lesson_candidate(lesson_candidate)
            lesson_candidate["firewall_result"] = fw
            rec.lesson_candidate = lesson_candidate
            if fw.get("accepted"):
                self.lesson_candidates.append(lesson_candidate)

        self.reflections.append(rec)
        return rec

    def drain_pending(self, lifecycles: list[dict[str, Any]]) -> list[ReflectionRecord]:
        done: list[ReflectionRecord] = []
        for life in lifecycles:
            rec = self.reflect_lifecycle(life)
            if rec:
                done.append(rec)
        return done

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REFLECTION_V28_SCHEMA,
            "reflections_n": len(self.reflections),
            "reflections": [r.to_dict() for r in self.reflections],
            "mistake_signatures": [s.to_dict() for s in self.mistake_signatures.values()],
            "lesson_candidates": self.lesson_candidates,
            "active_lessons_from_live_demo": self.firewall.active_lessons_created_from_live_demo,
            "validation_firewall_enforced": True,
        }


def _lifecycle_net(lifecycle: dict[str, Any]) -> float | None:
    ea = lifecycle.get("exact_pnl_accounting") or {}
    if ea.get("calculated_net_pnl") is not None:
        return float(ea["calculated_net_pnl"])
    wr = lifecycle.get("wallet_reconciliation") or {}
    if wr.get("actual_wallet_delta") is not None:
        return float(wr["actual_wallet_delta"])
    pnl_pct = lifecycle.get("pnl_pct")
    if pnl_pct is not None:
        return float(pnl_pct)
    return None
