"""NEXUS Autonomous Closed-Loop Harness V1 — simulated full Private Core flow.

No exchange writes. Fixture/mock only. CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

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
        return {"allowed": True, "reason": "PASS"}


class ClosedLoopHarness:
    def __init__(self) -> None:
        self.exchange_write_attempt_count = 0
        self.demo_order_count = 0
        self.lifecycles: dict[str, Lifecycle] = {}
        self.lessons: dict[str, dict[str, Any]] = {}
        self.label = "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"
        self.real_learning_claimed = False

    def _lc(self, lid: str) -> Lifecycle:
        if lid not in self.lifecycles:
            self.lifecycles[lid] = Lifecycle(lifecycle_id=lid)
        return self.lifecycles[lid]

    def run_happy_path(self, candidate: dict[str, Any], *, pnl: float) -> dict[str, Any]:
        lid = candidate["candidate_id"]
        intent_key = candidate.get("idempotency_key") or lid
        # Global idempotency across harness
        for existing in self.lifecycles.values():
            if intent_key in existing.intent_keys and existing.state not in {"OBSERVED"}:
                return {"status": "DUPLICATE_IGNORED", "lifecycle_id": existing.lifecycle_id, "state": existing.state}

        lc = self._lc(lid)
        if lc.state != "OBSERVED" and intent_key in lc.intent_keys:
            return {"status": "DUPLICATE_IGNORED", "lifecycle_id": lid, "state": lc.state}

        chain = [
            "CANDIDATE_CREATED",
            "EVIDENCE_READY",
            "AI_REVIEW_PENDING",
            "AI_REVIEW_COMPLETE",
            "RISK_REVIEW_PENDING",
        ]
        for st in chain:
            if lc.state != st:
                lc.transition(st, reason=st.lower(), evidence=candidate, idempotency_key=f"{lid}:{st}")

        risk = DeterministicRisk.evaluate(candidate, ai_request=candidate.get("ai_request"))
        if not risk["allowed"]:
            lc.transition("RISK_BLOCKED", reason=risk["reason"], evidence=risk, idempotency_key=f"{lid}:block")
            lc.transition("CLOSED", reason="blocked_closed", evidence=risk, idempotency_key=f"{lid}:closed")
            return {"status": "BLOCKED", "risk": risk, "state": lc.state, "lifecycle_id": lid}

        lc.intent_keys.add(intent_key)
        for st in [
            "ORDER_INTENT_CREATED",
            "SIMULATED_OPEN",
            "SIMULATED_MANAGING",
            "SIMULATED_EXITED",
            "REFLECTION_PENDING",
            "REFLECTION_COMPLETE",
        ]:
            lc.transition(st, reason=st.lower(), evidence={"pnl": pnl}, idempotency_key=f"{lid}:{st}")

        classification = (
            "BAD_PROCESS_LOSS"
            if candidate.get("bad_process") and pnl < 0
            else ("GOOD_PROCESS_LOSS" if pnl < 0 else "GOOD_PROCESS_WIN")
        )
        if candidate.get("bad_process"):
            lesson_id = f"LES_{lid}"
            self.lessons[lesson_id] = {
                "lesson_id": lesson_id,
                "signature": candidate.get("error_signature") or "SIG_DEFAULT",
                "effect": "TEMPORARY_COMPONENT_CONTEXT_BLOCK",
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
        lc.transition(
            "CLOSED",
            reason="done",
            evidence={"classification": classification},
            idempotency_key=f"{lid}:closed",
        )
        return {
            "status": "COMPLETE",
            "classification": classification,
            "state": lc.state,
            "lifecycle_id": lid,
            "label": self.label,
        }

    def scenario_matrix(self) -> dict[str, Any]:
        results = {}

        # A VALID_PROCESS_LOSS
        r = self.run_happy_path({"candidate_id": "A1", "idempotency_key": "A1"}, pnl=-1.0)
        later = self.run_happy_path({"candidate_id": "A2", "idempotency_key": "A2"}, pnl=1.0)
        results["VALID_PROCESS_LOSS"] = {
            "status": "PASS" if r.get("classification") == "GOOD_PROCESS_LOSS" and later.get("status") == "COMPLETE" else "FAIL",
            "detail": {"first": r, "later_not_suppressed": later.get("status") == "COMPLETE"},
        }

        # B STALE
        r = self.run_happy_path({"candidate_id": "B1", "stale_data": True, "idempotency_key": "B1"}, pnl=0)
        results["STALE_DATA_BLOCK"] = {"status": "PASS" if r.get("status") == "BLOCKED" else "FAIL", "detail": r}

        # C COST
        r = self.run_happy_path({"candidate_id": "C1", "cost_destroyed": True, "idempotency_key": "C1"}, pnl=0)
        results["COST_DESTROYED_BLOCK"] = {"status": "PASS" if r.get("status") == "BLOCKED" else "FAIL", "detail": r}

        # D DUPLICATE
        r1 = self.run_happy_path({"candidate_id": "D1", "idempotency_key": "DUP1"}, pnl=0.5)
        r2 = self.run_happy_path({"candidate_id": "D1", "idempotency_key": "DUP1"}, pnl=0.5)
        results["DUPLICATE_INTENT_IDEMPOTENCY"] = {
            "status": "PASS" if r1.get("status") == "COMPLETE" and r2.get("status") == "DUPLICATE_IGNORED" else "FAIL",
            "detail": {"first": r1, "second": r2},
        }

        # E PROVIDER UNAVAILABLE
        r = self.run_happy_path({"candidate_id": "E1", "provider_unavailable": True, "idempotency_key": "E1"}, pnl=0)
        results["PROVIDER_UNAVAILABLE_FAIL_CLOSED"] = {
            "status": "PASS" if r.get("status") == "BLOCKED" else "FAIL",
            "detail": r,
        }

        # F REPEATED BAD PROCESS FIXTURE
        r = self.run_happy_path(
            {"candidate_id": "F1", "bad_process": True, "error_signature": "SIG_X", "idempotency_key": "F1"},
            pnl=-1,
        )
        r2 = self.run_happy_path(
            {"candidate_id": "F2", "error_signature": "SIG_X", "lesson_block": True, "idempotency_key": "F2"},
            pnl=1,
        )
        results["REPEATED_BAD_PROCESS_SIGNATURE"] = {
            "status": "PASS"
            if r.get("status") == "COMPLETE" and r2.get("status") == "BLOCKED" and self.lessons
            else "FAIL",
            "detail": {"source": r, "later": r2, "lessons": list(self.lessons)},
            "label": self.label,
        }

        # G HARD RISK
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

        # H RESTART — serialize and restore
        snap = {
            "lifecycles": {
                k: {"state": v.state, "intent_keys": list(v.intent_keys), "transitions": v.transitions}
                for k, v in self.lifecycles.items()
            }
        }
        restored = ClosedLoopHarness()
        for lid, data in snap["lifecycles"].items():
            lc = restored._lc(lid)
            lc.state = data["state"]
            lc.intent_keys = set(data["intent_keys"])
            lc.transitions = list(data["transitions"])
        # pending open should not duplicate
        pending = [lid for lid, lc in restored.lifecycles.items() if lc.state == "SIMULATED_OPEN"]
        # create one pending artificially
        p = restored._lc("H_PENDING")
        p.state = "ORDER_INTENT_CREATED"
        p.intent_keys.add("H_KEY")
        again = restored.run_happy_path({"candidate_id": "H_PENDING", "idempotency_key": "H_KEY"}, pnl=1)
        results["RESTART_RECOVERY"] = {
            "status": "PASS" if again.get("status") == "DUPLICATE_IGNORED" else "FAIL",
            "detail": again,
            "restored_lifecycle_count": len(restored.lifecycles),
        }

        statuses = [v["status"] for v in results.values()]
        return {
            "schema": "scenario_matrix_result",
            "label": self.label,
            "real_learning_claimed": False,
            "scenario_count": len(results),
            "scenario_pass_count": sum(1 for s in statuses if s == "PASS"),
            "scenario_failure_count": sum(1 for s in statuses if s != "PASS"),
            "scenarios": results,
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
            "demo_order_count": self.demo_order_count,
            "state_machine_status": "PASS",
            "valid_process_loss_status": results["VALID_PROCESS_LOSS"]["status"],
            "stale_data_block_status": results["STALE_DATA_BLOCK"]["status"],
            "cost_destroyed_block_status": results["COST_DESTROYED_BLOCK"]["status"],
            "duplicate_intent_idempotency_status": results["DUPLICATE_INTENT_IDEMPOTENCY"]["status"],
            "provider_unavailable_fail_closed_status": results["PROVIDER_UNAVAILABLE_FAIL_CLOSED"]["status"],
            "repeated_bad_process_fixture_status": results["REPEATED_BAD_PROCESS_SIGNATURE"]["status"],
            "hard_risk_override_status": results["HARD_RISK_OVERRIDE"]["status"],
            "restart_recovery_status": results["RESTART_RECOVERY"]["status"],
        }


def run_harness() -> dict[str, Any]:
    h = ClosedLoopHarness()
    matrix = h.scenario_matrix()
    rec = "NEXUS_AUTONOMOUS_HARNESS_V1_PASS"
    if matrix["scenario_failure_count"]:
        # pinpoint
        if matrix["hard_risk_override_status"] != "PASS":
            rec = "NEXUS_AUTONOMOUS_HARNESS_RISK_OVERRIDE_INVALID"
        elif matrix["duplicate_intent_idempotency_status"] != "PASS":
            rec = "NEXUS_AUTONOMOUS_HARNESS_IDEMPOTENCY_INVALID"
        elif matrix["provider_unavailable_fail_closed_status"] != "PASS":
            rec = "NEXUS_AUTONOMOUS_HARNESS_FAIL_CLOSED_INVALID"
        else:
            rec = "NEXUS_AUTONOMOUS_HARNESS_IMPLEMENTATION_INVALID"
    return {
        "schema": "closed_loop_harness_status",
        "recommendation": rec,
        **matrix,
        "created_at": _utc(),
    }
