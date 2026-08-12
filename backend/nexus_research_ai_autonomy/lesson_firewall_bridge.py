"""Lesson Firewall bridge — LESSON_CANDIDATE only; never ACTIVE from live demo PnL."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_validation_firewall.firewall import LessonValidationFirewall
from backend.nexus_lesson_validation_firewall.states import LessonPromotionStateMachine


class LessonFirewallBridge:
    """Reflection may create LESSON_CANDIDATE; ACTIVE requires full firewall path."""

    def __init__(self) -> None:
        self.candidates: list[dict[str, Any]] = []
        self.active_lessons_created_from_live_demo = 0
        self.firewall = LessonValidationFirewall()

    def ingest_lesson_candidate(self, candidate: dict[str, Any] | None) -> dict[str, Any]:
        if not candidate:
            return {"accepted": False, "reason": "empty"}
        status = str(candidate.get("status") or "LESSON_CANDIDATE").upper()
        if status != "LESSON_CANDIDATE":
            return {"accepted": False, "reason": "only_lesson_candidate_allowed"}
        # Hard ban: never activate from live demo directly
        lesson = {
            "lesson_id": candidate.get("lesson_id") or f"LC_{len(self.candidates)+1:04d}",
            "state": "CANDIDATE",
            "status": "CANDIDATE",
            "evidence_class": "RESEARCH_AI_DEMO",
            "payload": dict(candidate),
            "from_live_demo": True,
        }
        sm = LessonPromotionStateMachine(lesson)
        # Attempt illegal ACTIVE skip — must fail
        active_attempt = sm.attempt_transition("ACTIVE", actor="live_demo_reflection")
        if active_attempt.get("allowed"):
            # Should be impossible; if it happens, still refuse counting
            return {"accepted": False, "reason": "firewall_failed_open_refused"}
        self.candidates.append(
            {
                **lesson,
                "active_blocked": True,
                "active_attempt": {
                    "allowed": bool(active_attempt.get("allowed")),
                    "to_state": active_attempt.get("to_state"),
                },
            }
        )
        return {
            "accepted": True,
            "lesson_id": lesson["lesson_id"],
            "state": "CANDIDATE",
            "active_lessons_created_from_live_demo": self.active_lessons_created_from_live_demo,
        }

    def promote_via_full_firewall_only(self, *, firewall_path_passed: bool) -> dict[str, Any]:
        """ACTIVE only if independent full firewall validation path passed."""
        if not firewall_path_passed:
            return {
                "promoted": False,
                "active_lessons_created_from_live_demo": self.active_lessons_created_from_live_demo,
                "reason": "full_firewall_path_not_passed",
            }
        # Even when passed, this research window still defaults to 0 unless explicitly set by Founder path.
        # We do not auto-increment from live demo here.
        return {
            "promoted": False,
            "active_lessons_created_from_live_demo": self.active_lessons_created_from_live_demo,
            "reason": "research_window_keeps_active_at_zero_without_separate_founder_activation",
        }
