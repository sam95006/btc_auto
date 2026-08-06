"""Learning bridge: Shadow Decision → Ontology / CF / Memory / Lesson Compiler.

Emits Lesson CANDIDATE refs only — never ACTIVE.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_counterfactual_replay_v16.ledger_guard import assert_outcome_not_real_performance
from backend.nexus_decision_memory_graph.graph import DecisionMemoryGraph
from backend.nexus_lesson_compiler.compiler import LessonCompileError, compile_reflection
from backend.nexus_lesson_compiler.constants import LESSON_STATUS_CANDIDATE
from backend.nexus_lesson_compiler.contracts import ReflectionFixture
from backend.nexus_shadow_decision_ledger.constants import (
    BRIDGE_SCHEMA,
    FORBIDDEN_LESSON_STATUSES,
    HARD_BANS,
)
from backend.nexus_shadow_decision_ledger.contracts import ShadowDecisionRecord
from backend.nexus_shadow_decision_ledger.ledger import ShadowDecisionLedger, ShadowLedgerError
from backend.nexus_trade_error_ontology_v1.classifier import classify_trade_error
from backend.nexus_trade_error_ontology_v1.constants import PROCESS_CLASSES


class LearningBridgeError(RuntimeError):
    """Fail-closed learning bridge error."""


class ShadowLearningBridge:
    """Attach ontology / counterfactual / memory / lesson-candidate artifacts."""

    def __init__(
        self,
        ledger: ShadowDecisionLedger,
        *,
        memory: DecisionMemoryGraph | None = None,
    ) -> None:
        self.ledger = ledger
        self.memory = memory or DecisionMemoryGraph()
        self.active_lesson_count = 0
        self.candidate_lesson_count = 0

    def classify_process(self, shadow_decision_id: str, packet: dict[str, Any] | None = None) -> dict[str, Any]:
        rec = self.ledger.get(shadow_decision_id)
        if rec.sealed:
            raise ShadowLedgerError("no_rewrite_sealed_record")
        base = {
            "decision_id": rec.shadow_decision_id,
            "symbol": (rec.candidate or {}).get("symbol") or (rec.market_snapshot or {}).get("symbol"),
            "net_pnl": (rec.subsequent_outcome or {}).get("net_pnl"),
            "entry_price": (rec.final_shadow_decision or {}).get("entry_price"),
            "stop_price": (rec.final_shadow_decision or {}).get("stop_price"),
            "target_price": (rec.final_shadow_decision or {}).get("target_price"),
            "cost_gate_status": (rec.costs or {}).get("cost_gate_status", "UNKNOWN"),
            "data_quality_status": (rec.market_snapshot or {}).get("data_quality_status", "UNKNOWN"),
            "risk_gate_status": (rec.deterministic_risk or {}).get("status", "UNKNOWN"),
            "shadow_only": True,
            "actual_ordered": False,
        }
        if packet:
            base.update(packet)
        classification = classify_trade_error(base)
        process_class = str(
            classification.get("process_class")
            or classification.get("process_classification")
            or "INSUFFICIENT_EVIDENCE"
        )
        if process_class not in PROCESS_CLASSES:
            process_class = "INSUFFICIENT_EVIDENCE"
        classification = dict(classification)
        classification["process_class"] = process_class
        classification["process_classification"] = process_class
        self.ledger.update_fields(
            shadow_decision_id,
            process_classification=classification,
        )
        return classification

    def attach_counterfactual_ref(
        self,
        shadow_decision_id: str,
        *,
        counterfactual_id: str,
        outcome: dict[str, Any] | None = None,
    ) -> list[str]:
        rec = self.ledger.get(shadow_decision_id)
        if rec.sealed:
            raise ShadowLedgerError("no_rewrite_sealed_record")
        cf_outcome = dict(outcome or {})
        cf_outcome.setdefault("is_counterfactual", True)
        cf_outcome.setdefault("is_real_performance", False)
        assert_outcome_not_real_performance(cf_outcome)
        refs = list(rec.counterfactual_refs)
        if counterfactual_id not in refs:
            refs.append(counterfactual_id)
        self.ledger.update_fields(shadow_decision_id, counterfactual_refs=refs)
        return refs

    def seal_memory_nodes(self, shadow_decision_id: str, *, as_of_ms: int) -> dict[str, Any]:
        rec = self.ledger.get(shadow_decision_id)
        decision_node = self.memory.seal_node(
            kind="DECISION",
            as_of_ms=as_of_ms,
            payload={
                "shadow_decision_id": rec.shadow_decision_id,
                "lifecycle_state": rec.lifecycle_state,
                "actual_ordered": False,
                "actual_filled": False,
                "exchange_order_id": None,
                "virtual_research_position": rec.virtual_research_position,
                "final_shadow_decision": rec.final_shadow_decision,
            },
        )
        outcome_node = None
        if rec.subsequent_outcome is not None:
            outcome_payload = dict(rec.subsequent_outcome)
            outcome_payload["is_real_performance"] = False
            outcome_payload["shadow_research_outcome"] = True
            outcome_node = self.memory.seal_node(
                kind="OUTCOME",
                as_of_ms=as_of_ms,
                payload=outcome_payload,
                parent_lineage_hashes=[decision_node["lineage_hash"]],
            )
            self.memory.seal_edge(
                kind="RESULTED_IN",
                from_id=decision_node["node_id"],
                to_id=outcome_node["node_id"],
                as_of_ms=as_of_ms,
            )
        lesson_nodes = []
        for lesson_id in rec.lesson_candidate_refs:
            ln = self.memory.seal_node(
                kind="LESSON",
                as_of_ms=as_of_ms,
                payload={
                    "lesson_id": lesson_id,
                    "status": LESSON_STATUS_CANDIDATE,
                    "active": False,
                },
                parent_lineage_hashes=[decision_node["lineage_hash"]],
            )
            self.memory.seal_edge(
                kind="PRODUCED_LESSON",
                from_id=decision_node["node_id"],
                to_id=ln["node_id"],
                as_of_ms=as_of_ms,
            )
            lesson_nodes.append(ln["node_id"])
        return {
            "schema": BRIDGE_SCHEMA,
            "decision_node_id": decision_node["node_id"],
            "outcome_node_id": None if outcome_node is None else outcome_node["node_id"],
            "lesson_node_ids": lesson_nodes,
        }

    def compile_lesson_candidate(
        self,
        shadow_decision_id: str,
        *,
        reflection: ReflectionFixture,
        forced_status: str | None = None,
    ) -> dict[str, Any]:
        """Compile a new Lesson as CANDIDATE only and attach its ref."""
        status = (forced_status or LESSON_STATUS_CANDIDATE).strip().upper()
        if status != LESSON_STATUS_CANDIDATE or status in FORBIDDEN_LESSON_STATUSES:
            self.active_lesson_count += 0  # never promote
            raise LearningBridgeError(f"lesson_must_be_candidate:{status}")
        try:
            rule = compile_reflection(reflection, forced_status=LESSON_STATUS_CANDIDATE)
        except LessonCompileError as exc:
            raise LearningBridgeError(f"lesson_compile_failed:{exc}") from exc
        if rule.status != LESSON_STATUS_CANDIDATE:
            raise LearningBridgeError(f"compiler_emitted_non_candidate:{rule.status}")
        if rule.status == "ACTIVE":
            raise LearningBridgeError("no_active_lessons")

        rec = self.ledger.get(shadow_decision_id)
        refs = list(rec.lesson_candidate_refs)
        if rule.lesson_id not in refs:
            refs.append(rule.lesson_id)
        self.ledger.update_fields(shadow_decision_id, lesson_candidate_refs=refs)
        self.candidate_lesson_count += 1
        # Ledger active count must remain 0.
        self.ledger.active_lesson_count = 0
        self.active_lesson_count = 0
        return {
            "lesson_id": rule.lesson_id,
            "status": rule.status,
            "active": False,
            "hard_bans": list(HARD_BANS),
        }

    def refuse_active_lesson(self, shadow_decision_id: str, reflection: ReflectionFixture) -> None:
        try:
            self.compile_lesson_candidate(
                shadow_decision_id,
                reflection=reflection,
                forced_status="ACTIVE",
            )
        except LearningBridgeError:
            return
        raise LearningBridgeError("expected_active_lesson_refusal")
