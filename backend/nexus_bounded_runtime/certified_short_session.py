"""Certified one-entry Short Bounded V1 session.

This mode reuses the certified 6H runtime and only narrows authorization,
duration, entry count, and learning-closure terminal behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.nexus_bounded_runtime.bounded_start_auth import (
    SHORT_FOUNDER_PHRASE,
    verify_bounded_start_request,
)
from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession
from backend.nexus_bounded_runtime.runtime_lease import (
    RuntimeLease,
    lease_allows_new_entry,
    validate_runtime_lease,
)
from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.session_policy import BoundedSessionPolicy, policy_short_v1

SHORT_SESSION_ID_PREFIX = "NEXUS-DEMO-SHORT-V1-"
SHORT_MAX_DURATION_SEC = 60 * 60
SHORT_ENTRY_CUTOFF_BUFFER_SEC = 5 * 60
SHORT_LEARNING_CLOSURE_STOP_REASON = "SHORT_FIRST_LEARNING_CLOSURE_COMPLETE"
SHORT_EXPIRY_BLOCK_REASON = "SHORT_EXPIRY_INSUFFICIENT_FOR_MAX_HOLD_AND_CLOSURE"


@dataclass
class CertifiedShortBoundedSession(CertifiedBounded6HSession):
    """Certified Short V1: exactly one possible entry, then durable lesson proof."""

    policy: BoundedSessionPolicy = field(default_factory=policy_short_v1)

    def _verify_start_request(self, start_request: dict[str, Any] | None) -> dict[str, Any]:
        return verify_bounded_start_request(
            start_request,
            expected_founder_phrase=SHORT_FOUNDER_PHRASE,
        )

    def _validate_start_lease(self, lease: RuntimeLease | None) -> dict[str, Any]:
        return validate_runtime_lease(
            lease,
            session_id_prefix=SHORT_SESSION_ID_PREFIX,
            max_duration_sec=SHORT_MAX_DURATION_SEC,
        )

    def _lease_allows_new_entry(self) -> bool:
        return lease_allows_new_entry(
            self._runtime_lease,
            learning_hold=self._learning_closure_hold,
            session_id_prefix=SHORT_SESSION_ID_PREFIX,
            max_duration_sec=SHORT_MAX_DURATION_SEC,
        )

    def _authorization_scope(self) -> str:
        return "DEMO_CERTIFIED_SHORT_V1_SESSION_ONLY"

    def _next_gate_metadata(self) -> dict[str, Any]:
        return {
            "next_machine_gate": "NONE",
            "next_founder_gate": "FOUNDER_REVIEW_SHORT_LEARNING_CLOSURE",
            "next_founder_gate_approved": False,
            "24H_GATE_APPROVED": False,
        }

    def _remaining_lease_seconds(self) -> float:
        if self._runtime_lease is None:
            return 0.0
        expires = datetime.fromisoformat(self._runtime_lease.expires_at.replace("Z", "+00:00"))
        return (expires - datetime.now(timezone.utc)).total_seconds()

    def _mark_short_entry_blocked(self, reason: str) -> None:
        self.session_write_enabled = False
        try:
            self.gate.close_smoke_write_window()
        except Exception:
            pass
        with self._lock:
            if reason == "short_entry_limit_reached":
                self._state["short_entry_limit_reached"] = True
            if reason == SHORT_EXPIRY_BLOCK_REASON:
                self._state["short_entry_window_closed"] = True
                self._state["NEW_ENTRY_BLOCKED_BY_SHORT_EXPIRY"] = True
            self._state["short_new_entry_block_reason"] = reason

    def _short_entry_budget_available(self) -> bool:
        with self._lock:
            entries = int(self._state.get("entries_total") or 0)
            completed = int(self._state.get("trades_completed") or 0)
        if entries >= 1 or completed >= 1:
            self._mark_short_entry_blocked("short_entry_limit_reached")
            return False
        remaining = self._remaining_lease_seconds()
        minimum = self.policy.max_hold_sec + SHORT_ENTRY_CUTOFF_BUFFER_SEC
        with self._lock:
            self._state["short_remaining_lease_seconds"] = max(0, int(remaining))
            self._state["short_entry_cutoff_minimum_seconds"] = minimum
        if remaining < minimum:
            self._mark_short_entry_blocked(SHORT_EXPIRY_BLOCK_REASON)
            return False
        return True

    def _runtime_entry_allowed(self) -> bool:
        return super()._runtime_entry_allowed() and self._short_entry_budget_available()

    def _before_durable_entry_intent(self) -> bool:
        return self._short_entry_budget_available()

    def _after_durable_lesson_written(
        self,
        *,
        lesson: dict[str, Any],
        active: dict[str, Any],
        account_epoch: str,
        exit_reason: str,
    ) -> dict[str, Any]:
        del active, account_epoch, exit_reason
        evidence_hash = str(lesson.get("source_evidence_hash") or "")
        readback = {}
        if evidence_hash and self._certified_lesson_store is not None:
            readback = self._certified_lesson_store.get_by_evidence_hash(evidence_hash) or {}
        ok = bool(
            lesson.get("ok")
            and evidence_hash
            and readback.get("source_evidence_hash") == evidence_hash
            and readback.get("lesson_id") == lesson.get("lesson_id")
        )
        with self._lock:
            self._state["short_lesson_readback_proof"] = redact_secrets(
                {
                    "ok": ok,
                    "lesson_id": lesson.get("lesson_id") if ok else None,
                    "source_evidence_hash": evidence_hash if ok else None,
                }
            )
            self._state["short_lesson_readback_pass"] = ok
        if not ok:
            self._learning_closure_hold = True
            self.session_write_enabled = False
            try:
                self.gate.close_smoke_write_window()
            except Exception:
                pass
            with self._lock:
                self._state["durable_learning_closure_hold"] = True
                self._state["durable_learning_closure_pending"] = True
                self._state["durable_lesson_readback_failed"] = True
                self._state["short_entry_limit_reached"] = True
            return {"ok": False, "reason": "short_lesson_readback_failed"}

        self._learning_closure_hold = True
        self.session_write_enabled = False
        try:
            self.gate.close_smoke_write_window()
        except Exception:
            pass
        with self._lock:
            self._state["SHORT_LEARNING_CLOSURE_COMPLETE"] = True
            self._state["short_learning_closure_complete"] = True
            self._state["short_entry_limit_reached"] = True
            self._state["stop_reason"] = SHORT_LEARNING_CLOSURE_STOP_REASON
        self._stop.set()
        return {"ok": True, "reason": SHORT_LEARNING_CLOSURE_STOP_REASON}

    def status(self) -> dict[str, Any]:
        snap = super().status()
        snap["authorization_scope"] = self._authorization_scope()
        snap["SHORT_BOUNDED_V1"] = True
        snap.setdefault("short_entry_limit_reached", False)
        snap.setdefault("short_entry_window_closed", False)
        snap.setdefault("short_learning_closure_complete", False)
        return snap

    def _recommend(self) -> str:
        with self._lock:
            st = dict(self._state)
        if st.get("durable_lesson_readback_failed") or (
            st.get("durable_learning_closure_hold") and int(st.get("entries_total") or 0) > 0
        ):
            return "DEMO_CERTIFIED_SHORT_V1_FAILED_LEARNING_CLOSURE"
        return super()._recommend()
