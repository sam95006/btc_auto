"""Safety gates for V16-F Lesson Validation Firewall."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_validation_firewall.bans import (
    active_block_reasons,
    refuse_ai_self_promote,
    refuse_cherry_pick,
    refuse_production_mutation,
    refuse_real_lesson_active,
)
from backend.nexus_lesson_validation_firewall.constants import (
    EVIDENCE_CLASS_REAL,
    FORWARD_TRANSITIONS,
    PROMOTION_STATES,
    SOT_FORMAL_WF,
    SOT_LESSON_PREVENTION,
    SOT_OOS,
    SOT_V2_3_COMPLETE,
    SOT_V2_3_TERMINAL,
)


def evaluate_sot_blockers() -> dict[str, Any]:
    return {
        "v23_complete": SOT_V2_3_COMPLETE,
        "v23_terminal": SOT_V2_3_TERMINAL,
        "formal_wf": SOT_FORMAL_WF,
        "oos": SOT_OOS,
        "lesson_prevention": SOT_LESSON_PREVENTION,
        "active_blocked": True,
        "block_reasons": active_block_reasons(),
    }


def evaluate_active_gate(lesson: dict[str, Any]) -> dict[str, Any]:
    """ACTIVE is never granted for real lessons; fixture ACTIVE also blocked this window."""
    lesson_id = str(lesson.get("lesson_id") or "")
    evidence_class = str(lesson.get("evidence_class") or "")
    refusal = refuse_real_lesson_active(lesson_id)
    return {
        **refusal,
        "evidence_class": evidence_class,
        "real_lesson": bool(lesson.get("real_lesson")) or evidence_class == EVIDENCE_CLASS_REAL,
        "gate": "ACTIVE_PROMOTION",
        "window_policy": "NEVER_MARK_REAL_OR_FIXTURE_ACTIVE_IN_V16F_WINDOW",
    }


def evaluate_ai_actor_gate(actor: str | None, *, requested_state: str | None = None) -> dict[str, Any]:
    a = str(actor or "").strip().lower()
    ai_like = a in {"ai", "ai_agent", "agent", "model", "llm", "cursor_agent", "auto"}
    if ai_like or a.startswith("ai_") or a.endswith("_ai"):
        refusal = refuse_ai_self_promote(actor)
        return {
            **refusal,
            "gate": "AI_ACTOR",
            "requested_state": requested_state,
        }
    return {
        "allowed": True,
        "gate": "AI_ACTOR",
        "actor": actor,
        "ai_self_promoted": False,
        "requested_state": requested_state,
        "note": "non_ai_actor_still_subject_to_other_gates",
    }


def evaluate_cherry_pick_gate(lesson: dict[str, Any]) -> dict[str, Any]:
    evidence = list(lesson.get("evidence") or [])
    polarities = {str(e.get("polarity") or "").lower() for e in evidence}
    favorable_only = polarities == {"favorable"} or (
        "favorable" in polarities
        and "unfavorable" not in polarities
        and "contradictory" not in polarities
        and bool(lesson.get("cherry_pick_attempt"))
    )
    has_unfavorable = "unfavorable" in polarities or "contradictory" in polarities
    if favorable_only or (evidence and not has_unfavorable):
        refusal = refuse_cherry_pick(str(lesson.get("lesson_id") or ""))
        return {
            **refusal,
            "gate": "CHERRY_PICK",
            "polarities": sorted(polarities),
            "evidence_count": len(evidence),
        }
    return {
        "allowed": True,
        "gate": "CHERRY_PICK",
        "cherry_picked": False,
        "polarities": sorted(polarities),
        "evidence_count": len(evidence),
        "includes_unfavorable_or_contradictory": True,
    }


def evaluate_transition_legality(from_state: str, to_state: str) -> dict[str, Any]:
    if from_state not in PROMOTION_STATES or to_state not in PROMOTION_STATES:
        return {
            "allowed": False,
            "reason": "UNKNOWN_STATE",
            "from_state": from_state,
            "to_state": to_state,
            "gate": "TRANSITION_LEGALITY",
        }
    legal = to_state in FORWARD_TRANSITIONS.get(from_state, frozenset())
    if not legal:
        return {
            "allowed": False,
            "reason": "ILLEGAL_OR_SKIPPED_TRANSITION",
            "from_state": from_state,
            "to_state": to_state,
            "gate": "TRANSITION_LEGALITY",
            "legal_targets": sorted(FORWARD_TRANSITIONS.get(from_state, frozenset())),
        }
    return {
        "allowed": True,
        "reason": None,
        "from_state": from_state,
        "to_state": to_state,
        "gate": "TRANSITION_LEGALITY",
    }


def evaluate_production_mutation_gate(mutation: dict[str, Any] | None) -> dict[str, Any]:
    if not mutation:
        return {
            "allowed": True,
            "gate": "PRODUCTION_MUTATION",
            "production_mutated": False,
            "note": "no_mutation_requested",
        }
    target = str(mutation.get("target") or mutation.get("field") or "unknown")
    refusal = refuse_production_mutation(target)
    return {**refusal, "gate": "PRODUCTION_MUTATION", "mutation": mutation}


def evaluate_expiry_revalidation(lesson: dict[str, Any], *, now_epoch: int) -> dict[str, Any]:
    expires = int(lesson.get("expires_at_epoch") or 0)
    expired = expires > 0 and now_epoch >= expires
    if expired:
        return {
            "allowed": False,
            "gate": "EXPIRY_REVALIDATION",
            "expired": True,
            "requires_revalidation": True,
            "expires_at_epoch": expires,
            "now_epoch": now_epoch,
            "reason": "LESSON_EXPIRED_REQUIRES_REVALIDATION",
        }
    return {
        "allowed": True,
        "gate": "EXPIRY_REVALIDATION",
        "expired": False,
        "requires_revalidation": False,
        "expires_at_epoch": expires,
        "now_epoch": now_epoch,
    }


def evaluate_contradictory_evidence(lesson: dict[str, Any]) -> dict[str, Any]:
    evidence = list(lesson.get("evidence") or [])
    contradictory = [e for e in evidence if str(e.get("polarity") or "").lower() == "contradictory"]
    ignored = bool(lesson.get("ignore_contradictory_evidence"))
    if contradictory and ignored:
        return {
            "allowed": False,
            "gate": "CONTRADICTORY_EVIDENCE",
            "contradictory_count": len(contradictory),
            "reason": "NO_CONTRADICTORY_EVIDENCE_IGNORE",
            "handled": False,
            "promotion_held": True,
        }
    return {
        "allowed": True,
        "gate": "CONTRADICTORY_EVIDENCE",
        "contradictory_count": len(contradictory),
        "handled": True,
        "action": "RECORD_AND_CONTINUE_PENDING" if contradictory else "NONE",
        # ACTIVE remains blocked by SoT gates; contradictions do not unlock ACTIVE.
        "promotion_held": False,
        "active_still_blocked": True,
    }
