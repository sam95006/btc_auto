"""Lesson promotion state machine — V16-F firewall (fail-closed on ACTIVE)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_lesson_validation_firewall.bans import refuse_stage_skip
from backend.nexus_lesson_validation_firewall.constants import (
    EVIDENCE_CLASS_REAL,
    PROMOTION_STATES,
)
from backend.nexus_lesson_validation_firewall.gates import (
    evaluate_active_gate,
    evaluate_ai_actor_gate,
    evaluate_cherry_pick_gate,
    evaluate_contradictory_evidence,
    evaluate_expiry_revalidation,
    evaluate_production_mutation_gate,
    evaluate_sot_blockers,
    evaluate_transition_legality,
)
from backend.nexus_lesson_validation_firewall.guards import (
    assert_no_regression_or_block,
    compare_baseline_vs_patched,
    evaluate_catastrophic_forgetting_guard,
)
from backend.nexus_lesson_validation_firewall.record import ImmutablePromotionRecordStore


class LessonPromotionStateMachine:
    """Pipeline mechanics with hard ACTIVE block for this window."""

    def __init__(
        self,
        lesson: dict[str, Any],
        *,
        record_store: ImmutablePromotionRecordStore | None = None,
        now_epoch: int = 1_700_000_000,
    ) -> None:
        self.lesson = deepcopy(lesson)
        self.state = str(lesson.get("state") or "CANDIDATE")
        if self.state not in PROMOTION_STATES:
            self.state = "CANDIDATE"
        self.history: list[dict[str, Any]] = []
        self.record_store = record_store or ImmutablePromotionRecordStore()
        self.now_epoch = now_epoch
        self.real_lesson_active = False

    def _record_event(self, event: str, detail: dict[str, Any]) -> None:
        self.history.append({"event": event, "detail": deepcopy(detail), "state": self.state})

    def attempt_transition(
        self,
        to_state: str,
        *,
        actor: str = "founder_operator",
        mutation: dict[str, Any] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        from_state = self.state
        legality = evaluate_transition_legality(from_state, to_state)
        if not legality.get("allowed"):
            skip = refuse_stage_skip(from_state, to_state)
            result = {
                "allowed": False,
                "from_state": from_state,
                "to_state": to_state,
                "state": self.state,
                "legality": legality,
                "skip_refusal": skip,
                "real_lesson_active": False,
            }
            self._record_event("transition_rejected_illegal", result)
            return result

        ai_gate = evaluate_ai_actor_gate(actor, requested_state=to_state)
        if not ai_gate.get("allowed"):
            result = {
                "allowed": False,
                "from_state": from_state,
                "to_state": to_state,
                "state": self.state,
                "ai_gate": ai_gate,
                "real_lesson_active": False,
            }
            self._record_event("transition_rejected_ai_self_promote", result)
            return result

        cherry = evaluate_cherry_pick_gate(self.lesson)
        if not cherry.get("allowed"):
            result = {
                "allowed": False,
                "from_state": from_state,
                "to_state": to_state,
                "state": self.state,
                "cherry_pick_gate": cherry,
                "real_lesson_active": False,
            }
            self._record_event("transition_rejected_cherry_pick", result)
            return result

        expiry = evaluate_expiry_revalidation(self.lesson, now_epoch=self.now_epoch)
        if not expiry.get("allowed"):
            result = {
                "allowed": False,
                "from_state": from_state,
                "to_state": to_state,
                "state": self.state,
                "expiry_gate": expiry,
                "real_lesson_active": False,
            }
            self._record_event("transition_rejected_expired", result)
            return result

        contradict = evaluate_contradictory_evidence(self.lesson)
        # Ignoring contradictory evidence fails closed (RETIRED still allowed).
        if not contradict.get("allowed") and to_state != "RETIRED":
            result = {
                "allowed": False,
                "from_state": from_state,
                "to_state": to_state,
                "state": self.state,
                "contradictory_gate": contradict,
                "real_lesson_active": False,
            }
            self._record_event("transition_rejected_contradiction_ignored", result)
            return result

        regression = assert_no_regression_or_block(compare_baseline_vs_patched(self.lesson))
        if not regression.get("allowed") and to_state not in {"RETIRED", "DEGRADED"}:
            result = {
                "allowed": False,
                "from_state": from_state,
                "to_state": to_state,
                "state": self.state,
                "regression_gate": regression,
                "real_lesson_active": False,
            }
            self._record_event("transition_rejected_regression", result)
            return result

        forgetting = evaluate_catastrophic_forgetting_guard(self.lesson)
        if not forgetting.get("allowed"):
            result = {
                "allowed": False,
                "from_state": from_state,
                "to_state": to_state,
                "state": self.state,
                "forgetting_gate": forgetting,
                "real_lesson_active": False,
            }
            self._record_event("transition_rejected_forgetting", result)
            return result

        prod = evaluate_production_mutation_gate(mutation)
        if not prod.get("allowed"):
            result = {
                "allowed": False,
                "from_state": from_state,
                "to_state": to_state,
                "state": self.state,
                "production_gate": prod,
                "real_lesson_active": False,
            }
            self._record_event("transition_rejected_production_mutation", result)
            return result

        # Hard ACTIVE block for this window (real and fixture).
        if to_state == "ACTIVE":
            active_gate = evaluate_active_gate(self.lesson)
            sot = evaluate_sot_blockers()
            result = {
                "allowed": False,
                "from_state": from_state,
                "to_state": to_state,
                "state": self.state,
                "active_gate": active_gate,
                "sot_blockers": sot,
                "force_ignored": bool(force),
                "real_lesson_active": False,
                "reason": active_gate.get("reason"),
            }
            self._record_event("transition_rejected_active_blocked", result)
            sealed = self.record_store.append(
                {
                    "record_id": f"rec_{self.lesson.get('lesson_id')}_{from_state}_ACTIVE_BLOCKED",
                    "lesson_id": self.lesson.get("lesson_id"),
                    "from_state": from_state,
                    "to_state": "ACTIVE",
                    "outcome": "BLOCKED",
                    "actor": actor,
                    "reasons": sot.get("block_reasons"),
                }
            )
            result["promotion_record"] = sealed
            return result

        # Apply legal non-ACTIVE transition.
        self.state = to_state
        self.lesson["state"] = to_state
        if to_state == "ACTIVE":  # pragma: no cover — unreachable
            self.real_lesson_active = False

        sealed = self.record_store.append(
            {
                "record_id": f"rec_{self.lesson.get('lesson_id')}_{from_state}_{to_state}",
                "lesson_id": self.lesson.get("lesson_id"),
                "from_state": from_state,
                "to_state": to_state,
                "outcome": "APPLIED",
                "actor": actor,
                "evidence_class": self.lesson.get("evidence_class"),
                "real_lesson_active": False,
            }
        )
        result = {
            "allowed": True,
            "from_state": from_state,
            "to_state": to_state,
            "state": self.state,
            "real_lesson_active": False,
            "promotion_record": sealed,
            "ai_gate": ai_gate,
            "cherry_pick_gate": cherry,
            "expiry_gate": expiry,
            "contradictory_gate": contradict,
            "regression_gate": regression,
            "forgetting_gate": forgetting,
            "production_gate": prod,
        }
        self._record_event("transition_applied", result)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "lesson_id": self.lesson.get("lesson_id"),
            "state": self.state,
            "real_lesson": bool(self.lesson.get("real_lesson"))
            or self.lesson.get("evidence_class") == EVIDENCE_CLASS_REAL,
            "real_lesson_active": self.real_lesson_active,
            "evidence_class": self.lesson.get("evidence_class"),
            "history_count": len(self.history),
            "history": list(self.history),
            "record_store": self.record_store.to_dict(),
            "sot_blockers": evaluate_sot_blockers(),
        }
