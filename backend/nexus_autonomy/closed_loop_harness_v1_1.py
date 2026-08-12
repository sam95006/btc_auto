"""NEXUS Autonomous Closed-Loop Harness V1.1

Taxonomy + global idempotency corrections.
CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING — no exchange writes.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.nexus_autonomy.process_classification import (
    CANONICAL_CLASSES,
    classify_completed_trade,
    control_fixture_process_evidence,
)

STATES = (
    "OBSERVED",
    "CANDIDATE_CREATED",
    "EVIDENCE_READY",
    "AI_REVIEW_PENDING",
    "AI_REVIEW_COMPLETE",
    "RISK_REVIEW_PENDING",
    "RISK_BLOCKED",
    "ORDER_INTENT_CREATED",
    "SIMULATED_OPEN",
    "SIMULATED_MANAGING",
    "SIMULATED_EXITED",
    "REFLECTION_PENDING",
    "REFLECTION_COMPLETE",
    "LESSON_PENDING",
    "LESSON_STORED",
    "CLOSED",
)

ALLOWED = {
    ("OBSERVED", "CANDIDATE_CREATED"),
    ("CANDIDATE_CREATED", "EVIDENCE_READY"),
    ("EVIDENCE_READY", "AI_REVIEW_PENDING"),
    ("AI_REVIEW_PENDING", "AI_REVIEW_COMPLETE"),
    ("AI_REVIEW_COMPLETE", "RISK_REVIEW_PENDING"),
    ("RISK_REVIEW_PENDING", "RISK_BLOCKED"),
    ("RISK_REVIEW_PENDING", "ORDER_INTENT_CREATED"),
    ("ORDER_INTENT_CREATED", "SIMULATED_OPEN"),
    ("SIMULATED_OPEN", "SIMULATED_MANAGING"),
    ("SIMULATED_MANAGING", "SIMULATED_EXITED"),
    ("SIMULATED_EXITED", "REFLECTION_PENDING"),
    ("REFLECTION_PENDING", "REFLECTION_COMPLETE"),
    ("REFLECTION_COMPLETE", "LESSON_PENDING"),
    ("LESSON_PENDING", "LESSON_STORED"),
    ("LESSON_STORED", "CLOSED"),
    ("REFLECTION_COMPLETE", "CLOSED"),
    ("RISK_BLOCKED", "CLOSED"),
    # Duplicate/orphan abort path before order states.
    ("OBSERVED", "CLOSED"),
    ("CANDIDATE_CREATED", "CLOSED"),
    ("EVIDENCE_READY", "CLOSED"),
    ("AI_REVIEW_PENDING", "CLOSED"),
    ("AI_REVIEW_COMPLETE", "CLOSED"),
    ("RISK_REVIEW_PENDING", "CLOSED"),
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class Lifecycle:
    lifecycle_id: str
    state: str = "OBSERVED"
    transitions: list[dict[str, Any]] = field(default_factory=list)
    intent_keys: set[str] = field(default_factory=set)
    labels: list[str] = field(default_factory=list)
    orphaned: bool = False

    def transition(self, next_state: str, *, reason: str, evidence: dict[str, Any], idempotency_key: str) -> None:
        if (self.state, next_state) not in ALLOWED:
            raise ValueError(f"invalid_transition {self.state}->{next_state}")
        ev = {
            "event_id": _sha({"from": self.state, "to": next_state, "key": idempotency_key})[:16],
            "previous_state": self.state,
            "next_state": next_state,
            "timestamp": _utc(),
            "reason": reason,
            "evidence_hash": _sha(evidence),
            "idempotency_key": idempotency_key,
        }
        self.transitions.append(ev)
        self.state = next_state


class DeterministicRisk:
    @staticmethod
    def evaluate(candidate: dict[str, Any], *, ai_request: dict[str, Any] | None = None) -> dict[str, Any]:
        if candidate.get("stale_data"):
            return {"allowed": False, "reason": "STALE_DATA_BLOCK"}
        if candidate.get("cost_destroyed"):
            return {"allowed": False, "reason": "COST_DESTROYED_BLOCK"}
        if candidate.get("provider_unavailable"):
            return {"allowed": False, "reason": "PROVIDER_UNAVAILABLE_FAIL_CLOSED"}
        if candidate.get("wallet_ambiguous"):
            return {"allowed": False, "reason": "WALLET_STATE_AMBIGUOUS_BLOCK"}
        if candidate.get("ledger_corrupt"):
            return {"allowed": False, "reason": "LEDGER_CORRUPTION_FAIL_CLOSED"}
        if candidate.get("partial_restore_ambiguous"):
            return {"allowed": False, "reason": "PARTIAL_STATE_RESTORE_BLOCKED"}
        if ai_request:
            forbidden = {"stop_widening", "risk_increase", "leverage_increase"}
            acts = set(ai_request.get("requested_actions") or [])
            if acts & forbidden:
                return {
                    "allowed": False,
                    "reason": "HARD_RISK_OVERRIDE_REJECTED",
                    "rejected_actions": sorted(acts & forbidden),
                    "order_or_policy_mutation": False,
                }
        if candidate.get("lesson_block"):
            return {"allowed": False, "reason": "REPEATED_BAD_PROCESS_SIGNATURE_BLOCK"}
        if candidate.get("adverse_first_same_bar"):
            return {"allowed": False, "reason": "SAME_BAR_STOP_TARGET_ADVERSE_FIRST"}
        return {"allowed": True, "reason": "PASS"}


class ClosedLoopHarnessV11:
    """V1.1 harness with global intent registry and evidence-based classification."""

    def __init__(self) -> None:
        self.exchange_write_attempt_count = 0
        self.demo_order_count = 0
        self.lifecycles: dict[str, Lifecycle] = {}
        self.global_intent_owners: dict[str, str] = {}
        self.audit_events: list[dict[str, Any]] = []
        self.lessons: dict[str, dict[str, Any]] = {}
        self.label = "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"
        self.real_learning_claimed = False
        self._lock = threading.Lock()

    def _lc(self, lid: str) -> Lifecycle:
        if lid not in self.lifecycles:
            self.lifecycles[lid] = Lifecycle(lifecycle_id=lid)
        return self.lifecycles[lid]

    def orphan_lifecycle_count(self) -> int:
        terminal = {"CLOSED", "RISK_BLOCKED"}
        return sum(
            1
            for lc in self.lifecycles.values()
            if lc.state not in terminal and lc.state != "OBSERVED" and (lc.orphaned or lc.state != "CLOSED")
            and lc.state
            in {
                "RISK_REVIEW_PENDING",
                "ORDER_INTENT_CREATED",
                "CANDIDATE_CREATED",
                "EVIDENCE_READY",
                "AI_REVIEW_PENDING",
                "AI_REVIEW_COMPLETE",
                "SIMULATED_OPEN",
                "SIMULATED_MANAGING",
            }
        )

    def _close_duplicate_lifecycle(
        self,
        lc: Lifecycle,
        *,
        intent_key: str,
        source_candidate_id: str,
        owner_lifecycle_id: str,
    ) -> dict[str, Any]:
        if lc.state != "CLOSED":
            lc.transition(
                "CLOSED",
                reason="duplicate_intent_abort",
                evidence={
                    "intent_key": intent_key,
                    "source_candidate_id": source_candidate_id,
                    "owner_lifecycle_id": owner_lifecycle_id,
                },
                idempotency_key=f"{lc.lifecycle_id}:dup_closed",
            )
        lc.orphaned = False
        evt = {
            "event_type": "DUPLICATE_INTENT_IGNORED",
            "timestamp": _utc(),
            "intent_key": intent_key,
            "source_candidate_id": source_candidate_id,
            "canonical_lifecycle_id": owner_lifecycle_id,
            "closed_duplicate_lifecycle_id": lc.lifecycle_id,
        }
        self.audit_events.append(evt)
        return {
            "status": "DUPLICATE_IGNORED",
            "lifecycle_id": owner_lifecycle_id,
            "duplicate_source_candidate_id": source_candidate_id,
            "closed_duplicate_lifecycle_id": lc.lifecycle_id,
            "state": self.lifecycles[owner_lifecycle_id].state,
            "audit_event": evt,
        }

    def run_happy_path(self, candidate: dict[str, Any], *, pnl: float | None) -> dict[str, Any]:
        lid = candidate["candidate_id"]
        intent_key = candidate.get("idempotency_key") or lid

        with self._lock:
            # Reserve / check global intent BEFORE advancing into order-processing states.
            owner = self.global_intent_owners.get(intent_key)
            if owner is not None:
                lc = self._lc(lid)
                if owner == lid and intent_key in lc.intent_keys:
                    return {
                        "status": "DUPLICATE_IGNORED",
                        "lifecycle_id": owner,
                        "state": lc.state,
                        "duplicate_source_candidate_id": lid,
                    }
                # Different candidate (or re-entry) with same intent — never leave orphan.
                if lid not in self.lifecycles:
                    self.lifecycles[lid] = Lifecycle(lifecycle_id=lid)
                return self._close_duplicate_lifecycle(
                    self.lifecycles[lid],
                    intent_key=intent_key,
                    source_candidate_id=lid,
                    owner_lifecycle_id=owner,
                )

            # Claim intent ownership early (before RISK / ORDER states).
            self.global_intent_owners[intent_key] = lid
            lc = self._lc(lid)
            lc.intent_keys.add(intent_key)

        # Advance only after reservation.
        while lc.state != "RISK_REVIEW_PENDING":
            nxt = {
                "OBSERVED": "CANDIDATE_CREATED",
                "CANDIDATE_CREATED": "EVIDENCE_READY",
                "EVIDENCE_READY": "AI_REVIEW_PENDING",
                "AI_REVIEW_PENDING": "AI_REVIEW_COMPLETE",
                "AI_REVIEW_COMPLETE": "RISK_REVIEW_PENDING",
            }.get(lc.state)
            if nxt is None:
                raise ValueError(f"cannot_advance_from {lc.state}")
            lc.transition(nxt, reason="advance", evidence=candidate, idempotency_key=f"{lid}:{nxt}")

        risk = DeterministicRisk.evaluate(candidate, ai_request=candidate.get("ai_request"))
        if not risk["allowed"]:
            lc.transition("RISK_BLOCKED", reason=risk["reason"], evidence=risk, idempotency_key=f"{lid}:block")
            lc.transition("CLOSED", reason="blocked_closed", evidence=risk, idempotency_key=f"{lid}:closed")
            return {"status": "BLOCKED", "risk": risk, "state": lc.state, "lifecycle_id": lid}

        for st, reason in [
            ("ORDER_INTENT_CREATED", "intent"),
            ("SIMULATED_OPEN", "open"),
            ("SIMULATED_MANAGING", "manage"),
            ("SIMULATED_EXITED", "exit"),
            ("REFLECTION_PENDING", "reflect_pending"),
            ("REFLECTION_COMPLETE", "reflect_done"),
        ]:
            lc.transition(st, reason=reason, evidence={"pnl": pnl}, idempotency_key=f"{lid}:{st}")

        process_evidence = candidate.get("process_evidence")
        if process_evidence is None:
            if candidate.get("undetermined_process"):
                process_evidence = control_fixture_process_evidence(undetermined=True)
            elif candidate.get("bad_process") is True:
                # Legacy fixture flag still maps through explicit evidence injector.
                process_evidence = control_fixture_process_evidence(bad=True)
            else:
                process_evidence = control_fixture_process_evidence(bad=False)

        classification = classify_completed_trade(pnl=pnl, process_evidence=process_evidence)

        if classification in {"BAD_PROCESS_WIN", "BAD_PROCESS_LOSS"}:
            lesson_id = f"LES_{lid}"
            self.lessons[lesson_id] = {
                "lesson_id": lesson_id,
                "signature": candidate.get("error_signature") or "SIG_DEFAULT",
                "effect": "TEMPORARY_COMPONENT_CONTEXT_BLOCK",
                "scope": "TARGETED_NOT_GLOBAL",
            }
            lc.transition(
                "LESSON_PENDING",
                reason="lesson",
                evidence={"classification": classification},
                idempotency_key=f"{lid}:lp",
            )
            lc.transition(
                "LESSON_STORED",
                reason="stored",
                evidence={"lesson_id": lesson_id},
                idempotency_key=f"{lid}:ls",
            )
        lc.transition("CLOSED", reason="done", evidence={"classification": classification}, idempotency_key=f"{lid}:closed")
        return {
            "status": "COMPLETE",
            "classification": classification,
            "process_evidence": process_evidence,
            "state": lc.state,
            "lifecycle_id": lid,
            "label": self.label,
        }

    def scenario_matrix(self) -> dict[str, Any]:
        results: dict[str, Any] = {}

        r = self.run_happy_path(
            {"candidate_id": "A1", "idempotency_key": "A1", "process_evidence": control_fixture_process_evidence(bad=False)},
            pnl=-1.0,
        )
        later = self.run_happy_path(
            {"candidate_id": "A2", "idempotency_key": "A2", "process_evidence": control_fixture_process_evidence(bad=False)},
            pnl=1.0,
        )
        results["VALID_PROCESS_LOSS"] = {
            "status": "PASS"
            if r.get("classification") == "GOOD_PROCESS_LOSS" and later.get("status") == "COMPLETE"
            else "FAIL",
            "detail": {"first": r, "later_not_suppressed": later.get("status") == "COMPLETE"},
        }

        r = self.run_happy_path({"candidate_id": "B1", "stale_data": True, "idempotency_key": "B1"}, pnl=0)
        results["STALE_DATA_BLOCK"] = {"status": "PASS" if r.get("status") == "BLOCKED" else "FAIL", "detail": r}

        r = self.run_happy_path({"candidate_id": "C1", "cost_destroyed": True, "idempotency_key": "C1"}, pnl=0)
        results["COST_DESTROYED_BLOCK"] = {"status": "PASS" if r.get("status") == "BLOCKED" else "FAIL", "detail": r}

        r1 = self.run_happy_path({"candidate_id": "D1", "idempotency_key": "DUP1"}, pnl=0.5)
        r2 = self.run_happy_path({"candidate_id": "D1", "idempotency_key": "DUP1"}, pnl=0.5)
        results["DUPLICATE_INTENT_IDEMPOTENCY"] = {
            "status": "PASS" if r1.get("status") == "COMPLETE" and r2.get("status") == "DUPLICATE_IGNORED" else "FAIL",
            "detail": {"first": r1, "second": r2},
        }

        r = self.run_happy_path({"candidate_id": "E1", "provider_unavailable": True, "idempotency_key": "E1"}, pnl=0)
        results["PROVIDER_UNAVAILABLE_FAIL_CLOSED"] = {
            "status": "PASS" if r.get("status") == "BLOCKED" else "FAIL",
            "detail": r,
        }

        r = self.run_happy_path(
            {
                "candidate_id": "F1",
                "error_signature": "SIG_X",
                "idempotency_key": "F1",
                "process_evidence": control_fixture_process_evidence(bad=True),
            },
            pnl=-1,
        )
        r2 = self.run_happy_path(
            {"candidate_id": "F2", "error_signature": "SIG_X", "lesson_block": True, "idempotency_key": "F2"},
            pnl=1,
        )
        results["REPEATED_BAD_PROCESS_SIGNATURE"] = {
            "status": "PASS"
            if r.get("classification") == "BAD_PROCESS_LOSS" and r2.get("status") == "BLOCKED" and self.lessons
            else "FAIL",
            "detail": {"source": r, "later": r2},
            "label": self.label,
        }

        r = self.run_happy_path(
            {
                "candidate_id": "G1",
                "idempotency_key": "G1",
                "ai_request": {"requested_actions": ["leverage_increase", "stop_widening"]},
            },
            pnl=0,
        )
        results["HARD_RISK_OVERRIDE"] = {
            "status": "PASS"
            if r.get("status") == "BLOCKED" and r.get("risk", {}).get("order_or_policy_mutation") is False
            else "FAIL",
            "detail": r,
        }

        snap = {
            "global_intent_owners": dict(self.global_intent_owners),
            "lifecycles": {k: {"state": v.state, "intent_keys": list(v.intent_keys)} for k, v in self.lifecycles.items()},
        }
        h2 = ClosedLoopHarnessV11()
        h2.global_intent_owners = dict(snap["global_intent_owners"])
        for k, meta in snap["lifecycles"].items():
            lc = Lifecycle(lifecycle_id=k, state=meta["state"])
            lc.intent_keys = set(meta["intent_keys"])
            h2.lifecycles[k] = lc
        pending = h2.run_happy_path({"candidate_id": "H_NEW", "idempotency_key": "H_NEW"}, pnl=0.2)
        dup = h2.run_happy_path({"candidate_id": "H_DUP", "idempotency_key": "H_NEW"}, pnl=0.2)
        results["RESTART_RECOVERY"] = {
            "status": "PASS"
            if pending.get("status") == "COMPLETE" and dup.get("status") == "DUPLICATE_IGNORED"
            else "FAIL",
            "detail": {"restored_complete": pending, "dup": dup},
        }

        # --- V1.1 additions ---
        r = self.run_happy_path(
            {
                "candidate_id": "BPW1",
                "idempotency_key": "BPW1",
                "process_evidence": control_fixture_process_evidence(bad=True),
            },
            pnl=2.0,
        )
        results["BAD_PROCESS_WIN_CLASSIFICATION"] = {
            "status": "PASS" if r.get("classification") == "BAD_PROCESS_WIN" else "FAIL",
            "detail": r,
        }

        r = self.run_happy_path(
            {"candidate_id": "UND1", "idempotency_key": "UND1", "undetermined_process": True},
            pnl=1.0,
        )
        results["UNDETERMINED_MISSING_EVIDENCE"] = {
            "status": "PASS" if r.get("classification") == "UNDETERMINED" else "FAIL",
            "detail": r,
        }

        r1 = self.run_happy_path({"candidate_id": "X1", "idempotency_key": "SHARED_X"}, pnl=1.0)
        r2 = self.run_happy_path({"candidate_id": "X2", "idempotency_key": "SHARED_X"}, pnl=1.0)
        results["CROSS_CANDIDATE_DUPLICATE_INTENT"] = {
            "status": "PASS"
            if r1.get("status") == "COMPLETE"
            and r2.get("status") == "DUPLICATE_IGNORED"
            and r2.get("lifecycle_id") == "X1"
            and self.lifecycles["X2"].state == "CLOSED"
            and self.orphan_lifecycle_count() == 0
            else "FAIL",
            "detail": {"first": r1, "second": r2, "orphan_lifecycle_count": self.orphan_lifecycle_count()},
        }

        r = self.run_happy_path({"candidate_id": "LC1", "idempotency_key": "LC1", "ledger_corrupt": True}, pnl=0)
        results["LEDGER_CORRUPTION_FAIL_CLOSED"] = {
            "status": "PASS" if r.get("status") == "BLOCKED" else "FAIL",
            "detail": r,
        }

        r = self.run_happy_path(
            {"candidate_id": "PS1", "idempotency_key": "PS1", "partial_restore_ambiguous": True},
            pnl=0,
        )
        results["PARTIAL_STATE_RESTORE"] = {
            "status": "PASS" if r.get("status") == "BLOCKED" else "FAIL",
            "detail": r,
        }

        r = self.run_happy_path(
            {"candidate_id": "SB1", "idempotency_key": "SB1", "adverse_first_same_bar": True},
            pnl=0,
        )
        results["SAME_BAR_STOP_TARGET_ADVERSE_FIRST"] = {
            "status": "PASS" if r.get("status") == "BLOCKED" else "FAIL",
            "detail": r,
        }

        # Lesson targeted: blocked signature only; other candidate still proceeds.
        _ = self.run_happy_path(
            {
                "candidate_id": "LT1",
                "idempotency_key": "LT1",
                "error_signature": "SIG_TARGET",
                "process_evidence": control_fixture_process_evidence(bad=True),
            },
            pnl=-1,
        )
        blocked = self.run_happy_path(
            {
                "candidate_id": "LT2",
                "idempotency_key": "LT2",
                "error_signature": "SIG_TARGET",
                "lesson_block": True,
            },
            pnl=1,
        )
        other = self.run_happy_path(
            {
                "candidate_id": "LT3",
                "idempotency_key": "LT3",
                "error_signature": "SIG_OTHER",
                "process_evidence": control_fixture_process_evidence(bad=False),
            },
            pnl=1,
        )
        results["LESSON_TARGETED_NOT_GLOBAL"] = {
            "status": "PASS"
            if blocked.get("status") == "BLOCKED" and other.get("status") == "COMPLETE"
            else "FAIL",
            "detail": {"blocked": blocked, "other": other},
        }

        r = self.run_happy_path({"candidate_id": "W1", "idempotency_key": "W1", "wallet_ambiguous": True}, pnl=0)
        results["WALLET_STATE_AMBIGUOUS_BLOCK"] = {
            "status": "PASS" if r.get("status") == "BLOCKED" else "FAIL",
            "detail": r,
        }

        return results


# Back-compat alias used by older imports/tests.
ClosedLoopHarness = ClosedLoopHarnessV11


def run_harness() -> dict[str, Any]:
    h = ClosedLoopHarnessV11()
    matrix = h.scenario_matrix()
    fails = [k for k, v in matrix.items() if v.get("status") != "PASS"]
    recommendation = (
        "NEXUS_AUTONOMOUS_HARNESS_V1_1_PASS" if not fails else "NEXUS_AUTONOMOUS_HARNESS_V1_1_FAIL"
    )
    return {
        "schema": "scenario_matrix_result_v1_1",
        "recommendation": recommendation,
        "label": h.label,
        "real_learning_claimed": False,
        "canonical_classes": list(CANONICAL_CLASSES),
        "canonical_classification_count": len(CANONICAL_CLASSES),
        "scenario_count": len(matrix),
        "scenario_pass_count": len(matrix) - len(fails),
        "scenario_failure_count": len(fails),
        "scenarios": matrix,
        "exchange_write_attempt_count": h.exchange_write_attempt_count,
        "demo_order_count": h.demo_order_count,
        "orphan_lifecycle_count": h.orphan_lifecycle_count(),
        "state_machine_status": "PASS" if not fails else "FAIL",
        "BAD_PROCESS_WIN_test_status": matrix.get("BAD_PROCESS_WIN_CLASSIFICATION", {}).get("status"),
        "UNDETERMINED_test_status": matrix.get("UNDETERMINED_MISSING_EVIDENCE", {}).get("status"),
        "cross_candidate_idempotency_status": matrix.get("CROSS_CANDIDATE_DUPLICATE_INTENT", {}).get("status"),
        "valid_process_loss_status": matrix.get("VALID_PROCESS_LOSS", {}).get("status"),
        "stale_data_block_status": matrix.get("STALE_DATA_BLOCK", {}).get("status"),
        "cost_destroyed_block_status": matrix.get("COST_DESTROYED_BLOCK", {}).get("status"),
        "duplicate_intent_idempotency_status": matrix.get("DUPLICATE_INTENT_IDEMPOTENCY", {}).get("status"),
        "provider_unavailable_fail_closed_status": matrix.get("PROVIDER_UNAVAILABLE_FAIL_CLOSED", {}).get("status"),
        "repeated_bad_process_fixture_status": matrix.get("REPEATED_BAD_PROCESS_SIGNATURE", {}).get("status"),
        "hard_risk_override_status": matrix.get("HARD_RISK_OVERRIDE", {}).get("status"),
        "restart_recovery_status": matrix.get("RESTART_RECOVERY", {}).get("status"),
        "created_at": _utc(),
    }
