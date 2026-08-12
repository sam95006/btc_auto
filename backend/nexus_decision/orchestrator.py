"""Founder-private Decision Lifecycle Orchestrator V11.

Stages: Observe → Understand → Challenge → Decide → Record → Monitor → Review → Calibrate → Improve

Hard bans enforced in-process:
  - no exchange writes / no strategy parameter mutation
  - fail-closed on invalid transitions / evidence loss / ambiguous state
  - Intent/Position IDs only via DecisionExecutionBridge (canonical adapter)
  - RiskLimits / FORBIDDEN_ACTIONS via nexus_execution.risk_gates (no opaque bypass)
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.nexus_decision.checkpoint import DecisionCheckpointStore
from backend.nexus_decision.decision_object import DecisionObject, DecisionObjectError, SCHEMA_VERSION
from backend.nexus_decision.evidence import (
    EvidenceValidationError,
    detect_evidence_loss,
    evidence_binding_hash,
    validate_evidence_completeness,
)
from backend.nexus_decision.execution_bridge import (
    BRIDGE_MODULE,
    DecisionExecutionBridge,
    DecisionExecutionBridgeError,
)
from backend.nexus_decision.ledger_link import DecisionLedgerLink
from backend.nexus_decision.state_machine import (
    CANONICAL_STATES,
    DecisionStateMachine,
    InvalidTransitionError,
)
from backend.nexus_execution.cost_model import COST_MODEL_VERSION
from backend.nexus_execution.risk_gates import FORBIDDEN_ACTIONS

ORCHESTRATOR_SCHEMA = "NEXUS_DECISION_LIFECYCLE_ORCHESTRATOR_V11"

# Strategy keys that must never be mutated through this orchestrator.
FORBIDDEN_STRATEGY_KEYS = frozenset(
    {
        "stop_loss",
        "take_profit",
        "leverage",
        "position_size",
        "risk_budget",
        "entry_threshold",
        "exit_threshold",
        "strategy_params",
        "parameter_mutation",
    }
)


class DecisionLifecycleError(RuntimeError):
    """Operational failure on the Decision Lifecycle Orchestrator. Fail-closed."""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class DecisionLifecycleOrchestrator:
    """In-process orchestrator for one or many Decision Objects under a private root."""

    STAGES: tuple[str, ...] = (
        "observe",
        "understand",
        "challenge",
        "decide",
        "record",
        "monitor",
        "review",
        "calibrate",
        "improve",
    )

    def __init__(
        self,
        root: Path | str,
        *,
        bridge: DecisionExecutionBridge | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._decisions: dict[str, DecisionObject] = {}
        self._machines: dict[str, DecisionStateMachine] = {}
        self._idempotency_index: dict[str, str] = {}  # key -> decision_id
        self._checkpoints = DecisionCheckpointStore(self.root / "checkpoints")
        self._ledger = DecisionLedgerLink(self.root / "ledger")
        self._bridge = bridge or DecisionExecutionBridge(self.root / "execution_bridge")
        self._order_attempt_count = 0
        self._strategy_mutation_attempt_count = 0
        self._exchange_write_attempt_count = 0

    @property
    def bridge(self) -> DecisionExecutionBridge:
        return self._bridge

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def attempt_place_order(self, *_args: Any, **_kwargs: Any) -> None:
        with self._lock:
            self._order_attempt_count += 1
            raise DecisionLifecycleError("orders_forbidden:DecisionLifecycleOrchestrator")

    def attempt_exchange_write(self, endpoint: str = "") -> None:
        with self._lock:
            self._exchange_write_attempt_count += 1
            raise DecisionLifecycleError(f"exchange_write_forbidden:{endpoint or 'unknown'}")

    def attempt_strategy_parameter_mutation(self, params: dict[str, Any]) -> None:
        with self._lock:
            self._strategy_mutation_attempt_count += 1
            banned = FORBIDDEN_STRATEGY_KEYS.intersection(params.keys())
            raise DecisionLifecycleError(
                f"strategy_parameter_mutation_forbidden:keys={sorted(banned or params.keys())}"
            )

    # ------------------------------------------------------------------
    # Observe (create)
    # ------------------------------------------------------------------

    def observe(
        self,
        *,
        candidate_id: str,
        market_context_id: str,
        point_in_time_timestamp: str,
        evidence_ids: list[str],
        evidence_hashes: list[str],
        data_freshness: dict[str, Any],
        data_completeness: dict[str, Any],
        idempotency_key: str,
        decision_id: str | None = None,
        evidence_blobs: dict[str, str | bytes] | None = None,
        max_age_seconds: float = 300.0,
    ) -> dict[str, Any]:
        with self._lock:
            if not idempotency_key:
                raise DecisionLifecycleError("idempotency_key_required")
            if idempotency_key in self._idempotency_index:
                existing_id = self._idempotency_index[idempotency_key]
                return {
                    "status": "DUPLICATE_IGNORED",
                    "decision": self._decisions[existing_id].to_dict(),
                    "duplicate": True,
                }
            try:
                validate_evidence_completeness(
                    evidence_ids=evidence_ids,
                    evidence_hashes=evidence_hashes,
                    data_freshness=data_freshness,
                    data_completeness=data_completeness,
                    evidence_blobs=evidence_blobs,
                    max_age_seconds=max_age_seconds,
                )
            except EvidenceValidationError as exc:
                raise DecisionLifecycleError(f"observe_evidence_rejected:{exc}") from exc

            did = decision_id or f"dec_{uuid.uuid4().hex[:16]}"
            try:
                obj = DecisionObject.create(
                    decision_id=did,
                    candidate_id=candidate_id,
                    market_context_id=market_context_id,
                    point_in_time_timestamp=point_in_time_timestamp,
                    evidence_ids=evidence_ids,
                    evidence_hashes=evidence_hashes,
                    data_freshness=data_freshness,
                    data_completeness=data_completeness,
                    idempotency_key=idempotency_key,
                    decision_status="OBSERVED",
                )
            except DecisionObjectError as exc:
                raise DecisionLifecycleError(f"observe_object_invalid:{exc}") from exc

            sm = DecisionStateMachine(initial="OBSERVED")
            obj.evidence_binding_hash = evidence_binding_hash(obj.evidence_ids, obj.evidence_hashes)
            self._decisions[did] = obj
            self._machines[did] = sm
            self._idempotency_index[idempotency_key] = did
            evt = self._ledger.append(
                decision_id=did,
                event_type="DECISION_OBSERVED",
                payload={
                    "decision_id": did,
                    "candidate_id": candidate_id,
                    "status": "OBSERVED",
                    "evidence_count": len(evidence_ids),
                },
                idempotency_key=f"{idempotency_key}:observe",
            )
            obj.ledger_event_ids.append(evt["event_id"])
            self._checkpoint_unlocked(did)
            return {"status": "OBSERVED", "decision": obj.to_dict(), "duplicate": False}

    # ------------------------------------------------------------------
    # Stage advances
    # ------------------------------------------------------------------

    def understand(
        self,
        decision_id: str,
        *,
        AI_reasoner_outputs: list[dict[str, Any]],
        idempotency_key: str,
        reason: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            obj, sm = self._require(decision_id)
            if not AI_reasoner_outputs:
                return self._block(decision_id, reason="understand_missing_reasoner_outputs", key=idempotency_key)
            self._assert_evidence_intact(obj)
            try:
                rec = sm.transition(
                    "UNDERSTANDING",
                    stage="understand",
                    reason=reason or "understand",
                    idempotency_key=idempotency_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            obj.AI_reasoner_outputs = list(AI_reasoner_outputs)
            obj.decision_status = "UNDERSTANDING"
            obj.transition_history.append(rec.to_dict())
            obj.touch()
            self._link(obj, "DECISION_UNDERSTANDING", idempotency_key, {"reasoner_count": len(AI_reasoner_outputs)})
            self._checkpoint_unlocked(decision_id)
            return {"status": "UNDERSTANDING", "decision": obj.to_dict()}

    def challenge(
        self,
        decision_id: str,
        *,
        independent_critic_output: dict[str, Any],
        idempotency_key: str,
        reason: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            obj, sm = self._require(decision_id)
            if not independent_critic_output:
                return self._block(decision_id, reason="challenge_missing_critic", key=idempotency_key)
            if independent_critic_output.get("ambiguous") is True:
                return self._block(
                    decision_id,
                    reason="challenge_critic_ambiguous",
                    key=idempotency_key,
                )
            self._assert_evidence_intact(obj)
            try:
                rec = sm.transition(
                    "CHALLENGED",
                    stage="challenge",
                    reason=reason or "challenge",
                    idempotency_key=idempotency_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            obj.independent_critic_output = dict(independent_critic_output)
            obj.decision_status = "CHALLENGED"
            obj.transition_history.append(rec.to_dict())
            obj.touch()
            self._link(obj, "DECISION_CHALLENGED", idempotency_key, {"critic": True})
            self._checkpoint_unlocked(decision_id)
            return {"status": "CHALLENGED", "decision": obj.to_dict()}

    def decide(
        self,
        decision_id: str,
        *,
        deterministic_risk_result: dict[str, Any] | None = None,
        execution_intent: dict[str, Any] | None = None,
        cost_model_version: str | None = None,
        mark_price: Any = 100,
        idempotency_key: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Decide stage: RISK_REVIEWED then APPROVED_SIMULATED / REJECTED / BLOCKED.

        Risk authority is ``backend.nexus_execution.risk_gates`` via the bridge.
        Opaque ``deterministic_risk_result`` alone cannot approve (AUTH_DECISION_RISK_BYPASS).
        Intent IDs are minted only by the canonical execution adapter (not Decision).
        """
        with self._lock:
            obj, sm = self._require(decision_id)
            self._assert_evidence_intact(obj)

            # Idempotent replay after restart: same decide key returns existing approval.
            if sm.state == "APPROVED_SIMULATED" and f"{idempotency_key}:outcome" in {
                r.get("idempotency_key") for r in sm.history()
            }:
                return {"status": "APPROVED_SIMULATED", "decision": obj.to_dict(), "duplicate": True}

            risk_key = f"{idempotency_key}:risk"
            approve_key = f"{idempotency_key}:outcome"

            intent_req = dict(execution_intent or {})
            intent_req.setdefault(
                "idempotency_key",
                f"decintent:{decision_id}:{obj.candidate_id}",
            )
            intent_req.setdefault("symbol", "BTCUSDT")
            intent_req.setdefault("side", "BUY")
            intent_req.setdefault("order_type", "MARKET")
            intent_req.setdefault("qty", Decimal("0.1"))
            intent_req.setdefault("leverage", int(self._bridge.risk_limits.leverage))
            intent_req.setdefault("margin_mode", "ISOLATED")
            if intent_req.get("requested_actions") is None:
                intent_req["requested_actions"] = tuple(
                    (deterministic_risk_result or {}).get("requested_actions") or ()
                )

            # Canonical risk gate — opaque allowed=True cannot bypass FORBIDDEN_ACTIONS.
            try:
                gate = self._bridge.evaluate_risk(intent_req)
            except DecisionExecutionBridgeError as exc:
                raise DecisionLifecycleError(str(exc)) from exc

            advisory = dict(deterministic_risk_result or {})
            # Merge gate result as authoritative deterministic_risk_result evidence.
            authoritative_risk = {
                **advisory,
                "allowed": bool(gate["allowed"]) and advisory.get("allowed", True) is not False,
                "reason": gate.get("reason"),
                "detail": gate.get("detail"),
                "authority": gate.get("authority"),
                "forbidden_actions_catalog": list(FORBIDDEN_ACTIONS),
                "cost_model_version": COST_MODEL_VERSION,
            }
            # Explicit advisory reject still wins.
            if advisory.get("allowed") is False:
                authoritative_risk["allowed"] = False
                authoritative_risk["reasons"] = list(
                    advisory.get("reasons") or [gate.get("reason") or "RISK_REJECTED"]
                )
            if advisory.get("ambiguous") is True:
                authoritative_risk["ambiguous"] = True
            if not gate["allowed"]:
                authoritative_risk["allowed"] = False
                authoritative_risk["reasons"] = list(
                    advisory.get("reasons") or [gate.get("reason") or "RISK_GATE_REJECTED"]
                )

            try:
                rec1 = sm.transition(
                    "RISK_REVIEWED",
                    stage="decide",
                    reason=reason or "risk_reviewed",
                    idempotency_key=risk_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            obj.deterministic_risk_result = authoritative_risk
            obj.decision_status = "RISK_REVIEWED"
            obj.transition_history.append(rec1.to_dict())
            obj.touch()
            self._link(
                obj,
                "DECISION_RISK_REVIEWED",
                risk_key,
                {"risk": authoritative_risk.get("allowed"), "authority": gate.get("authority")},
            )

            if authoritative_risk.get("ambiguous"):
                out = self._block(decision_id, reason="decide_risk_ambiguous", key=approve_key)
                self._checkpoint_unlocked(decision_id)
                return out
            if not authoritative_risk.get("allowed"):
                reject_reasons = list(
                    authoritative_risk.get("reasons") or ["RISK_REJECTED"]
                )
                try:
                    rec2 = sm.transition(
                        "REJECTED",
                        stage="decide",
                        reason=reason or "rejected",
                        idempotency_key=approve_key,
                    )
                except InvalidTransitionError as exc:
                    raise DecisionLifecycleError(str(exc)) from exc
                obj.decision_status = "REJECTED"
                obj.rejection_reasons = reject_reasons
                obj.transition_history.append(rec2.to_dict())
                obj.touch()
                self._link(obj, "DECISION_REJECTED", approve_key, {"reasons": reject_reasons})
                self._checkpoint_unlocked(decision_id)
                return {"status": "REJECTED", "decision": obj.to_dict()}

            # ADV_DECISION_APPROVED_TWICE: candidate-level uniqueness.
            other = self._bridge.approved_decision_for_candidate(obj.candidate_id)
            if other and other != decision_id:
                raise DecisionLifecycleError(
                    f"candidate_already_approved:{obj.candidate_id}:owner={other}"
                )

            try:
                binding = self._bridge.approve_intent(
                    decision_id=decision_id,
                    candidate_id=obj.candidate_id,
                    intent_req=intent_req,
                    cost_model_version=cost_model_version or COST_MODEL_VERSION,
                    mark_price=mark_price,
                )
            except DecisionExecutionBridgeError as exc:
                raise DecisionLifecycleError(str(exc)) from exc

            try:
                rec2 = sm.transition(
                    "APPROVED_SIMULATED",
                    stage="decide",
                    reason=reason or "approved_simulated",
                    idempotency_key=approve_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            obj.decision_status = "APPROVED_SIMULATED"
            # Authoritative Intent identity = OrderIntent.idempotency_key (execution-owned).
            obj.intent_id = binding.intent_idempotency_key
            obj.cost_model_version = binding.cost_model_version
            obj.linkage_authority = BRIDGE_MODULE
            obj.transition_history.append(rec2.to_dict())
            obj.touch()
            self._link(
                obj,
                "DECISION_APPROVED_SIMULATED",
                approve_key,
                {
                    "intent_id": obj.intent_id,
                    "order_id": binding.order_id,
                    "cost_model_version": obj.cost_model_version,
                    "linkage_authority": BRIDGE_MODULE,
                    "orders_placed": False,
                    "exchange_write": False,
                },
            )
            self._checkpoint_unlocked(decision_id)
            return {"status": "APPROVED_SIMULATED", "decision": obj.to_dict()}

    def record(self, decision_id: str, *, idempotency_key: str, reason: str = "") -> dict[str, Any]:
        """Record stage: bind Position via bridge; advance to MONITORING."""
        with self._lock:
            obj, sm = self._require(decision_id)
            self._assert_evidence_intact(obj)
            if sm.state == "REJECTED":
                evt = self._ledger.append(
                    decision_id=decision_id,
                    event_type="DECISION_RECORDED_REJECTED",
                    payload={"decision_id": decision_id, "status": "REJECTED"},
                    idempotency_key=idempotency_key,
                )
                if not evt.get("duplicate"):
                    obj.ledger_event_ids.append(evt["event_id"])
                obj.touch()
                self._checkpoint_unlocked(decision_id)
                return {"status": "RECORDED_REJECTED", "decision": obj.to_dict()}

            if sm.state != "APPROVED_SIMULATED":
                # Fail closed before any bridge side-effects (invalid skip-ahead).
                try:
                    sm.transition(
                        "MONITORING",
                        stage="record",
                        reason=reason or "record_to_monitor",
                        idempotency_key=idempotency_key,
                    )
                except InvalidTransitionError as exc:
                    raise DecisionLifecycleError(str(exc)) from exc
                raise DecisionLifecycleError(f"unexpected_record_state:{sm.state}")

            # ADV_PARTIAL_FILL_DURING_DECISION_TRANSITION
            try:
                # Restart-safe: rehydrate OrderIntent ownership into the live simulator.
                self._bridge.rehydrate_execution_intent(decision_id)
                self._bridge.assert_no_partial_fill_during_transition(decision_id)
                binding = self._bridge.ensure_position_after_simulated_fill(decision_id)
            except DecisionExecutionBridgeError as exc:
                return self._block(
                    decision_id,
                    reason=str(exc),
                    key=f"{idempotency_key}:partial_or_fill_block",
                )

            try:
                rec = sm.transition(
                    "MONITORING",
                    stage="record",
                    reason=reason or "record_to_monitor",
                    idempotency_key=idempotency_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            # Position ID only from PositionRecord via bridge — never decorative.
            obj.position_id = binding.position_id
            obj.intent_id = binding.intent_idempotency_key
            obj.linkage_authority = BRIDGE_MODULE
            obj.decision_status = "MONITORING"
            obj.transition_history.append(rec.to_dict())
            obj.touch()
            self._link(
                obj,
                "DECISION_RECORDED_MONITORING",
                idempotency_key,
                {
                    "position_id": obj.position_id,
                    "intent_id": obj.intent_id,
                    "linkage_authority": BRIDGE_MODULE,
                },
            )
            self._checkpoint_unlocked(decision_id)
            return {"status": "MONITORING", "decision": obj.to_dict()}

    def monitor(
        self,
        decision_id: str,
        *,
        idempotency_key: str,
        exit: bool = False,
        reason: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            obj, sm = self._require(decision_id)
            self._assert_evidence_intact(obj)
            try:
                self._bridge.sync_decision_with_execution(decision_id, sm.state)
            except DecisionExecutionBridgeError as exc:
                return self._block(decision_id, reason=str(exc), key=f"{idempotency_key}:sync")

            if not exit:
                self._link(obj, "DECISION_MONITOR_HEARTBEAT", idempotency_key, {"heartbeat": True})
                obj.touch()
                self._checkpoint_unlocked(decision_id)
                return {"status": "MONITORING", "decision": obj.to_dict(), "heartbeat": True}

            try:
                self._bridge.mark_exit_evidence(decision_id)
            except DecisionExecutionBridgeError as exc:
                return self._block(decision_id, reason=str(exc), key=f"{idempotency_key}:exit")

            try:
                rec = sm.transition(
                    "EXITED",
                    stage="monitor",
                    reason=reason or "exit",
                    idempotency_key=idempotency_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            obj.exit_id = obj.exit_id or f"exit_{uuid.uuid4().hex[:12]}"
            obj.decision_status = "EXITED"
            obj.transition_history.append(rec.to_dict())
            obj.touch()
            self._link(
                obj,
                "DECISION_EXITED",
                idempotency_key,
                {"exit_id": obj.exit_id, "exit_evidence": True},
            )
            self._checkpoint_unlocked(decision_id)
            return {"status": "EXITED", "decision": obj.to_dict()}

    def review(
        self,
        decision_id: str,
        *,
        reflection_id: str | None = None,
        idempotency_key: str,
        reason: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            obj, sm = self._require(decision_id)
            self._assert_evidence_intact(obj)
            # VOCAB_MONITORING_SKIP_EXIT: cannot review from MONITORING.
            if sm.state == "MONITORING":
                raise DecisionLifecycleError(
                    "invalid_transition:MONITORING->UNDER_REVIEW:exit_evidence_required"
                )
            try:
                rec = sm.transition(
                    "UNDER_REVIEW",
                    stage="review",
                    reason=reason or "review",
                    idempotency_key=idempotency_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            obj.reflection_id = reflection_id or obj.reflection_id or f"refl_{uuid.uuid4().hex[:12]}"
            obj.decision_status = "UNDER_REVIEW"
            obj.transition_history.append(rec.to_dict())
            obj.touch()
            self._link(obj, "DECISION_UNDER_REVIEW", idempotency_key, {"reflection_id": obj.reflection_id})
            self._checkpoint_unlocked(decision_id)
            return {"status": "UNDER_REVIEW", "decision": obj.to_dict()}

    def calibrate(
        self,
        decision_id: str,
        *,
        lesson_ids: list[str] | None = None,
        idempotency_key: str,
        reason: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            obj, sm = self._require(decision_id)
            self._assert_evidence_intact(obj)
            try:
                rec = sm.transition(
                    "CALIBRATED",
                    stage="calibrate",
                    reason=reason or "calibrate",
                    idempotency_key=idempotency_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            if lesson_ids:
                for lid in lesson_ids:
                    if lid not in obj.lesson_ids:
                        obj.lesson_ids.append(lid)
            obj.decision_status = "CALIBRATED"
            obj.transition_history.append(rec.to_dict())
            obj.touch()
            self._link(obj, "DECISION_CALIBRATED", idempotency_key, {"lesson_ids": list(obj.lesson_ids)})
            self._checkpoint_unlocked(decision_id)
            return {"status": "CALIBRATED", "decision": obj.to_dict()}

    def improve(
        self,
        decision_id: str,
        *,
        idempotency_key: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Improve stage: close the lifecycle. Does not mutate strategy parameters."""
        with self._lock:
            obj, sm = self._require(decision_id)
            self._assert_evidence_intact(obj)
            # ADV_DECISION_CLOSED_POSITION_OPEN — refuse CLOSED while position open.
            try:
                # Probe as if CLOSED to catch forbidden pairs before transition.
                self._bridge.sync_decision_with_execution(decision_id, "CLOSED")
            except DecisionExecutionBridgeError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            # If we had a position binding, exit evidence is mandatory (unless REJECTED path).
            binding = self._bridge.binding_for(decision_id)
            if binding and binding.position_id and sm.state not in {"REJECTED", "BLOCKED_AMBIGUOUS"}:
                if not binding.exit_evidence and sm.state not in {"EXITED", "UNDER_REVIEW", "CALIBRATED"}:
                    raise DecisionLifecycleError("exit_evidence_required_before_close")
            try:
                rec = sm.transition(
                    "CLOSED",
                    stage="improve",
                    reason=reason or "improve_close",
                    idempotency_key=idempotency_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            obj.decision_status = "CLOSED"
            obj.transition_history.append(rec.to_dict())
            obj.touch()
            self._link(
                obj,
                "DECISION_CLOSED",
                idempotency_key,
                {"strategy_params_mutated": False, "orders_placed": False},
            )
            self._checkpoint_unlocked(decision_id)
            return {"status": "CLOSED", "decision": obj.to_dict()}

    def reject(
        self,
        decision_id: str,
        *,
        reasons: list[str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        with self._lock:
            obj, sm = self._require(decision_id)
            try:
                rec = sm.transition(
                    "REJECTED",
                    stage="reject",
                    reason=";".join(reasons) or "reject",
                    idempotency_key=idempotency_key,
                )
            except InvalidTransitionError as exc:
                raise DecisionLifecycleError(str(exc)) from exc
            obj.decision_status = "REJECTED"
            obj.rejection_reasons = list(reasons)
            obj.transition_history.append(rec.to_dict())
            obj.touch()
            self._link(obj, "DECISION_REJECTED", idempotency_key, {"reasons": reasons})
            self._checkpoint_unlocked(decision_id)
            return {"status": "REJECTED", "decision": obj.to_dict()}

    def block_ambiguous(self, decision_id: str, *, reason: str, idempotency_key: str) -> dict[str, Any]:
        with self._lock:
            return self._block(decision_id, reason=reason, key=idempotency_key)

    # ------------------------------------------------------------------
    # Checkpoint / recover
    # ------------------------------------------------------------------

    def checkpoint(self, decision_id: str) -> dict[str, Any]:
        with self._lock:
            return self._checkpoint_unlocked(decision_id)

    def recover(self, decision_id: str) -> dict[str, Any]:
        """Restart recovery from latest checkpoint. Ambiguous recovery blocks."""
        with self._lock:
            payload = self._checkpoints.load_latest(decision_id)
            if payload is None:
                raise DecisionLifecycleError(f"recover_no_checkpoint:{decision_id}")
            if not self._checkpoints.verify_latest(decision_id):
                # Hash mismatch — block ambiguous rather than silent guess.
                if decision_id in self._decisions:
                    return self._block(
                        decision_id,
                        reason="recover_checkpoint_hash_mismatch",
                        key=f"recover_block_{decision_id}_{_utc()}",
                    )
                raise DecisionLifecycleError(f"recover_checkpoint_corrupt:{decision_id}")
            try:
                decision_payload = payload.get("decision") or payload
                obj = DecisionObject.from_dict(decision_payload)
            except DecisionObjectError as exc:
                raise DecisionLifecycleError(f"recover_object_invalid:{exc}") from exc

            # Evidence loss check vs checkpoint snapshot.
            losses = detect_evidence_loss(
                expected_ids=list(decision_payload.get("evidence_ids") or []),
                expected_hashes=list(decision_payload.get("evidence_hashes") or []),
                actual_ids=list(obj.evidence_ids),
                actual_hashes=list(obj.evidence_hashes),
            )
            if losses:
                raise DecisionLifecycleError(f"recover_evidence_loss:{losses}")
            if obj.evidence_binding_hash:
                bound = evidence_binding_hash(obj.evidence_ids, obj.evidence_hashes)
                if bound != obj.evidence_binding_hash:
                    raise DecisionLifecycleError("recover_evidence_loss:binding_hash_mismatch")

            sm = DecisionStateMachine(initial="OBSERVED")
            sm.restore(obj.decision_status, obj.transition_history)
            self._decisions[decision_id] = obj
            self._machines[decision_id] = sm
            self._idempotency_index[obj.idempotency_key] = decision_id
            # Restart-safe: rehydrate Decision↔Intent ownership from durable bridge state.
            self._bridge.restore_from_disk()
            self._link(
                obj,
                "DECISION_RECOVERED",
                f"recover:{decision_id}:{obj.checkpoint_seq}",
                {"recovered_status": obj.decision_status, "checkpoint_seq": obj.checkpoint_seq},
            )
            return {
                "status": "RECOVERED",
                "recovery_status": "RECOVERED",
                "decision": obj.to_dict(),
                "state": sm.state,
            }

    def get(self, decision_id: str) -> dict[str, Any]:
        with self._lock:
            obj, sm = self._require(decision_id)
            return {
                "schema": ORCHESTRATOR_SCHEMA,
                "decision": obj.to_dict(),
                "state": sm.state,
                "is_terminal": sm.is_terminal,
                "order_attempt_count": self._order_attempt_count,
                "strategy_mutation_attempt_count": self._strategy_mutation_attempt_count,
                "exchange_write_attempt_count": self._exchange_write_attempt_count,
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema": ORCHESTRATOR_SCHEMA,
                "created_at": _utc(),
                "decision_count": len(self._decisions),
                "canonical_states": list(CANONICAL_STATES),
                "stages": list(self.STAGES),
                "schema_version": SCHEMA_VERSION,
                "order_attempt_count": self._order_attempt_count,
                "strategy_mutation_attempt_count": self._strategy_mutation_attempt_count,
                "exchange_write_attempt_count": self._exchange_write_attempt_count,
                "ledger_sequence": self._ledger.sequence_number,
                "founder_private": True,
                "orders_permitted": False,
                "strategy_mutation_permitted": False,
                "public_api_exposed": False,
                "cost_model_version": COST_MODEL_VERSION,
                "linkage_authority": BRIDGE_MODULE,
                "bridge": self._bridge.report(),
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require(self, decision_id: str) -> tuple[DecisionObject, DecisionStateMachine]:
        if decision_id not in self._decisions or decision_id not in self._machines:
            raise DecisionLifecycleError(f"unknown_decision:{decision_id}")
        return self._decisions[decision_id], self._machines[decision_id]

    def _assert_evidence_intact(self, obj: DecisionObject) -> None:
        try:
            validate_evidence_completeness(
                evidence_ids=obj.evidence_ids,
                evidence_hashes=obj.evidence_hashes,
                data_freshness=obj.data_freshness,
                data_completeness=obj.data_completeness,
                require_complete=True,
            )
        except EvidenceValidationError as exc:
            raise DecisionLifecycleError(f"evidence_integrity_failed:{exc}") from exc
        if len(obj.evidence_ids) != len(obj.evidence_hashes):
            raise DecisionLifecycleError("evidence_loss:ids_hashes_desync")
        if obj.evidence_binding_hash:
            current = evidence_binding_hash(obj.evidence_ids, obj.evidence_hashes)
            if current != obj.evidence_binding_hash:
                raise DecisionLifecycleError("evidence_loss:binding_hash_mismatch")
    def _link(
        self,
        obj: DecisionObject,
        event_type: str,
        idempotency_key: str,
        payload_extra: dict[str, Any],
    ) -> None:
        evt = self._ledger.append(
            decision_id=obj.decision_id,
            event_type=event_type,
            payload={"decision_id": obj.decision_id, "status": obj.decision_status, **payload_extra},
            idempotency_key=idempotency_key,
        )
        if not evt.get("duplicate") and evt.get("event_id"):
            obj.ledger_event_ids.append(str(evt["event_id"]))

    def _block(self, decision_id: str, *, reason: str, key: str) -> dict[str, Any]:
        obj, sm = self._require(decision_id)
        if sm.state == "BLOCKED_AMBIGUOUS":
            return {"status": "BLOCKED_AMBIGUOUS", "decision": obj.to_dict(), "blocked_reason": obj.blocked_reason}
        if sm.state == "CLOSED":
            raise DecisionLifecycleError("cannot_block_closed_decision")
        try:
            rec = sm.transition(
                "BLOCKED_AMBIGUOUS",
                stage="block",
                reason=reason,
                idempotency_key=key,
            )
        except InvalidTransitionError as exc:
            raise DecisionLifecycleError(str(exc)) from exc
        obj.decision_status = "BLOCKED_AMBIGUOUS"
        obj.blocked_reason = reason
        obj.rejection_reasons.append(reason)
        obj.transition_history.append(rec.to_dict())
        obj.touch()
        self._link(obj, "DECISION_BLOCKED_AMBIGUOUS", key, {"reason": reason})
        self._checkpoint_unlocked(decision_id)
        return {"status": "BLOCKED_AMBIGUOUS", "decision": obj.to_dict(), "blocked_reason": reason}

    def _checkpoint_unlocked(self, decision_id: str) -> dict[str, Any]:
        obj, sm = self._require(decision_id)
        payload = {
            "schema": ORCHESTRATOR_SCHEMA,
            "decision": obj.to_dict(),
            "state": sm.state,
            "transition_history": sm.history(),
        }
        meta = self._checkpoints.save(decision_id, payload)
        obj.checkpoint_seq = int(meta["seq"])
        return {
            "schema": ORCHESTRATOR_SCHEMA,
            "command": "checkpoint",
            "created_at": _utc(),
            "checkpoint": meta,
            "state": sm.state,
        }

    def state_machine(self, decision_id: str) -> DecisionStateMachine:
        with self._lock:
            _, sm = self._require(decision_id)
            return sm

    @property
    def order_attempt_count(self) -> int:
        return self._order_attempt_count

    @property
    def strategy_mutation_attempt_count(self) -> int:
        return self._strategy_mutation_attempt_count

    @property
    def exchange_write_attempt_count(self) -> int:
        return self._exchange_write_attempt_count
