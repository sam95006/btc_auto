"""Tests for demo order execution foundation (Track 5-6).

Covers:
  - Authorization replay rejection
  - State machine transitions (all 17 states)
  - Timeout → AMBIGUOUS
  - Adapter write impossible
  - Candidate order_sent=False
  - Preflight gate checks
  - Ledger / audit trail integrity
  - Close controller
  - Recovery
"""
from __future__ import annotations

import time

import pytest

from backend.nexus_research.demo_execution.adapter import DemoOrderAdapter
from backend.nexus_research.demo_execution.candidate import (
    build_first_controlled_candidate,
)
from backend.nexus_research.demo_execution.close_controller import (
    CloseRequest,
    DemoCloseController,
)
from backend.nexus_research.demo_execution.intent import (
    AuthorizationReplayError,
    DemoOrderAuthorization,
    DemoOrderIntent,
    NotAuthorizedError,
    WriteNotAuthorizedError,
)
from backend.nexus_research.demo_execution.ledger import (
    DemoExecutionLedger,
    DemoOrderAuditTrail,
)
from backend.nexus_research.demo_execution.monitor import (
    DemoOrderMonitor,
    TimeoutPolicy,
)
from backend.nexus_research.demo_execution.preflight import DemoOrderPreflight
from backend.nexus_research.demo_execution.reconciler import DemoOrderReconciler
from backend.nexus_research.demo_execution.recovery import DemoOrderRecovery
from backend.nexus_research.demo_execution.state_machine import (
    BLOCKED_STATES,
    TERMINAL_STATES,
    DemoOrderState,
    DemoOrderStateMachine,
)


def _make_intent(**overrides) -> DemoOrderIntent:
    defaults = dict(
        intent_id="test-intent-001",
        symbol="BTCUSDT",
        side="Buy",
        qty=0.001,
        leverage=25,
        entry_price=105_000.0,
        stop_loss_price=103_425.0,
        take_profit_price=None,
        risk_tier="VALIDATION",
        client_order_id="nxd56-test-001",
        source="test",
    )
    defaults.update(overrides)
    return DemoOrderIntent(**defaults)


# ── Intent tests ──────────────────────────────────────────────────────────────

class TestDemoOrderIntent:
    def test_order_sent_always_false(self):
        intent = _make_intent()
        assert intent.order_sent is False

    def test_binding_key_deterministic(self):
        i1 = _make_intent()
        i2 = _make_intent()
        assert i1.binding_key() == i2.binding_key()

    def test_binding_key_changes_with_params(self):
        i1 = _make_intent(qty=0.001)
        i2 = _make_intent(qty=0.002)
        assert i1.binding_key() != i2.binding_key()

    def test_to_dict_order_sent_false(self):
        d = _make_intent().to_dict()
        assert d["orderSent"] is False


# ── Authorization tests ───────────────────────────────────────────────────────

class TestDemoOrderAuthorization:
    def test_create_and_consume(self):
        intent = _make_intent()
        auth = DemoOrderAuthorization.create_for_intent(intent)
        assert auth.consumed is False
        auth.consume(intent)
        assert auth.consumed is True
        assert auth.consumed_at_ms is not None

    def test_replay_rejection(self):
        intent = _make_intent()
        auth = DemoOrderAuthorization.create_for_intent(intent)
        auth.consume(intent)
        with pytest.raises(AuthorizationReplayError):
            auth.consume(intent)

    def test_expired_authorization_rejected(self):
        intent = _make_intent()
        auth = DemoOrderAuthorization.create_for_intent(intent, ttl_ms=0)
        time.sleep(0.01)
        with pytest.raises(NotAuthorizedError, match="expired"):
            auth.consume(intent)

    def test_binding_mismatch_rejected(self):
        intent_a = _make_intent(qty=0.001)
        intent_b = _make_intent(qty=0.999)
        auth = DemoOrderAuthorization.create_for_intent(intent_a)
        with pytest.raises(NotAuthorizedError, match="binding mismatch"):
            auth.consume(intent_b)

    def test_to_dict_order_sent_false(self):
        intent = _make_intent()
        auth = DemoOrderAuthorization.create_for_intent(intent)
        d = auth.to_dict()
        assert d["orderSent"] is False


# ── State machine tests ──────────────────────────────────────────────────────

class TestDemoOrderStateMachine:
    def test_initial_state_is_draft(self):
        sm = DemoOrderStateMachine()
        assert sm.state == DemoOrderState.DRAFT

    def test_happy_path_to_ready(self):
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION, reason="preflight passed")
        assert sm.state == DemoOrderState.READY_FOR_AUTHORIZATION

    def test_illegal_transition_raises(self):
        sm = DemoOrderStateMachine()
        with pytest.raises(ValueError, match="illegal_transition"):
            sm.transition(DemoOrderState.FILLED)

    def test_all_17_states_in_enum(self):
        assert len(DemoOrderState) == 17

    def test_terminal_states(self):
        expected = {"PREFLIGHT_BLOCKED", "REJECTED", "CANCELLED", "CLOSED", "RECONCILED"}
        assert {s.value for s in TERMINAL_STATES} == expected

    def test_blocked_states(self):
        expected = {"AMBIGUOUS", "RECOVERY_REQUIRED"}
        assert {s.value for s in BLOCKED_STATES} == expected

    def test_can_send_always_false(self):
        sm = DemoOrderStateMachine()
        assert sm.can_send is False
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        assert sm.can_send is False

    def test_order_sent_always_false(self):
        sm = DemoOrderStateMachine()
        assert sm.order_sent is False

    def test_full_lifecycle_draft_to_reconciled(self):
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION, reason="preflight ok")
        sm.transition(DemoOrderState.AUTHORIZED, reason="auth consumed")
        sm.transition(DemoOrderState.SEND_STARTED, reason="adapter called")
        sm.transition(DemoOrderState.ACKNOWLEDGED, reason="exchange ack")
        sm.transition(DemoOrderState.FILLED, reason="fill")
        sm.transition(DemoOrderState.CLOSE_AUTHORIZED, reason="close auth")
        sm.transition(DemoOrderState.CLOSE_STARTED, reason="close started")
        sm.transition(DemoOrderState.CLOSED, reason="closed")
        sm.transition(DemoOrderState.RECONCILED, reason="reconciled")
        assert sm.state == DemoOrderState.RECONCILED
        assert sm.is_terminal
        assert len(sm.history) == 9

    def test_ambiguous_from_send_started(self):
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)
        sm.transition(DemoOrderState.AMBIGUOUS, reason="timeout")
        assert sm.is_blocked
        assert sm.state == DemoOrderState.AMBIGUOUS

    def test_to_dict_order_sent_false(self):
        sm = DemoOrderStateMachine()
        d = sm.to_dict()
        assert d["orderSent"] is False
        assert d["canSend"] is False


# ── Timeout → AMBIGUOUS tests ────────────────────────────────────────────────

class TestTimeoutToAmbiguous:
    def test_timeout_transitions_to_ambiguous(self):
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)

        policy = TimeoutPolicy(timeout_ms=0)
        monitor = DemoOrderMonitor(timeout_policy=policy)
        monitor.start_monitoring("order-001")
        time.sleep(0.01)

        event = monitor.check_timeout("order-001", sm)
        assert event is not None
        assert event.event_type == "TIMEOUT"
        assert sm.state == DemoOrderState.AMBIGUOUS

    def test_ambiguous_blocks_new_orders(self):
        monitor = DemoOrderMonitor()
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)

        policy = TimeoutPolicy(timeout_ms=0)
        monitor = DemoOrderMonitor(timeout_policy=policy)
        monitor.start_monitoring("order-001")
        time.sleep(0.01)
        monitor.check_timeout("order-001", sm)

        assert monitor.has_ambiguous_orders()

    def test_no_blind_resend_in_policy(self):
        policy = TimeoutPolicy()
        assert policy.blind_resend_allowed is False
        assert policy.query_before_resend is True
        d = policy.to_dict()
        assert d["blindResendAllowed"] is False


# ── Adapter write impossible tests ────────────────────────────────────────────

class TestAdapterWriteImpossible:
    def test_place_order_raises(self):
        adapter = DemoOrderAdapter()
        intent = _make_intent()
        with pytest.raises(WriteNotAuthorizedError):
            adapter.place_order(intent)
        assert adapter.write_attempts == 1

    def test_amend_order_raises(self):
        adapter = DemoOrderAdapter()
        with pytest.raises(WriteNotAuthorizedError):
            adapter.amend_order("test-order")

    def test_cancel_order_raises(self):
        adapter = DemoOrderAdapter()
        with pytest.raises(WriteNotAuthorizedError):
            adapter.cancel_order("test-order")

    def test_set_leverage_raises(self):
        adapter = DemoOrderAdapter()
        with pytest.raises(WriteNotAuthorizedError):
            adapter.set_leverage("BTCUSDT", 25)

    def test_close_position_raises(self):
        adapter = DemoOrderAdapter()
        with pytest.raises(WriteNotAuthorizedError):
            adapter.close_position("BTCUSDT", "Buy", 0.001)

    def test_transfer_raises(self):
        adapter = DemoOrderAdapter()
        with pytest.raises(WriteNotAuthorizedError):
            adapter.transfer()

    def test_withdraw_raises(self):
        adapter = DemoOrderAdapter()
        with pytest.raises(WriteNotAuthorizedError):
            adapter.withdraw()

    def test_query_order_allowed(self):
        adapter = DemoOrderAdapter()
        result = adapter.query_order_status("test-order")
        assert result.success
        assert result.data["orderSent"] is False

    def test_write_allowed_always_false(self):
        adapter = DemoOrderAdapter()
        assert adapter.write_allowed is False

    def test_summary_order_sent_false(self):
        adapter = DemoOrderAdapter()
        d = adapter.summary()
        assert d["orderSent"] is False
        assert d["writeAllowed"] is False


# ── Preflight tests ───────────────────────────────────────────────────────────

class TestPreflight:
    def test_all_gates_pass(self):
        intent = _make_intent()
        preflight = DemoOrderPreflight()
        result = preflight.check(intent)
        assert result.all_passed is True
        assert result.order_sent is False

    def test_ambiguous_blocks_preflight(self):
        intent = _make_intent()
        preflight = DemoOrderPreflight(ambiguous_orders_exist=True)
        result = preflight.check(intent)
        assert result.all_passed is False
        blocked = [g for g in result.gates if g.name == "no_ambiguous_orders"]
        assert len(blocked) == 1
        assert blocked[0].passed is False

    def test_invalid_symbol_blocked(self):
        intent = _make_intent(symbol="INVALIDUSDT")
        preflight = DemoOrderPreflight()
        result = preflight.check(intent)
        assert result.all_passed is False


# ── Candidate order_sent=False tests ──────────────────────────────────────────

class TestFirstControlledCandidate:
    def test_candidate_order_sent_false(self):
        candidate = build_first_controlled_candidate()
        assert candidate.order_sent is False

    def test_candidate_intent_order_sent_false(self):
        candidate = build_first_controlled_candidate()
        assert candidate.intent.order_sent is False

    def test_candidate_to_dict_order_sent_false(self):
        candidate = build_first_controlled_candidate()
        d = candidate.to_dict()
        assert d["orderSent"] is False

    def test_candidate_risk_tier_validation(self):
        candidate = build_first_controlled_candidate()
        assert candidate.intent.risk_tier == "VALIDATION"

    def test_candidate_symbol_btcusdt(self):
        candidate = build_first_controlled_candidate()
        assert candidate.intent.symbol == "BTCUSDT"

    def test_candidate_has_stop_plan(self):
        candidate = build_first_controlled_candidate()
        assert candidate.stop_plan.stop_loss_price > 0
        assert candidate.stop_plan.stop_distance_pct > 0

    def test_candidate_has_close_plan(self):
        candidate = build_first_controlled_candidate()
        assert candidate.close_plan.close_strategy == "STOP_LOSS_OR_MANUAL"

    def test_candidate_client_order_id_idempotent(self):
        c1 = build_first_controlled_candidate()
        c2 = build_first_controlled_candidate()
        assert c1.intent.client_order_id == c2.intent.client_order_id

    def test_candidate_gate_summary(self):
        candidate = build_first_controlled_candidate()
        assert "order_sent" in candidate.gate_summary
        assert candidate.gate_summary["order_sent"] is False

    def test_candidate_ready_for_manual_authorization(self):
        candidate = build_first_controlled_candidate()
        assert isinstance(candidate.ready_for_manual_authorization, bool)


# ── Ledger and audit trail tests ──────────────────────────────────────────────

class TestLedger:
    def test_append_and_retrieve(self):
        ledger = DemoExecutionLedger()
        entry = ledger.append("order-001", "INTENT_CREATED", "DRAFT", {"foo": "bar"})
        assert entry.entry_id == "LE-000001"
        assert entry.order_sent is False
        assert len(ledger.entries) == 1

    def test_entries_for_order(self):
        ledger = DemoExecutionLedger()
        ledger.append("order-001", "INTENT_CREATED", "DRAFT")
        ledger.append("order-002", "INTENT_CREATED", "DRAFT")
        ledger.append("order-001", "PREFLIGHT", "READY_FOR_AUTHORIZATION")
        assert len(ledger.entries_for_order("order-001")) == 2

    def test_secret_sanitization(self):
        ledger = DemoExecutionLedger()
        entry = ledger.append("order-001", "TEST", "DRAFT", {"api_key": "SHOULD_BE_REDACTED"})
        assert entry.data["api_key"] == "***REDACTED***"


class TestAuditTrail:
    def test_hash_chain_integrity(self):
        trail = DemoOrderAuditTrail()
        trail.record("INTENT_CREATED", "order-001", {"symbol": "BTCUSDT"})
        trail.record("PREFLIGHT", "order-001", {"passed": True})
        trail.record("AUTHORIZED", "order-001", {"consumed": True})
        assert trail.verify_chain() is True

    def test_secret_safe(self):
        trail = DemoOrderAuditTrail()
        rec = trail.record("TEST", "order-001", {"apiSecret": "DANGER"})
        assert rec.detail["apiSecret"] == "***REDACTED***"

    def test_to_dict_order_sent_false(self):
        trail = DemoOrderAuditTrail()
        trail.record("TEST", "order-001")
        d = trail.to_dict()
        assert d["orderSent"] is False


# ── Reconciler tests ──────────────────────────────────────────────────────────

class TestReconciler:
    def test_match_when_consistent(self):
        reconciler = DemoOrderReconciler()
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)
        sm.transition(DemoOrderState.ACKNOWLEDGED)
        sm.transition(DemoOrderState.FILLED)

        result = reconciler.reconcile(
            "order-001", sm,
            exchange_state="FILLED",
            exchange_qty=0.001,
            internal_qty=0.001,
        )
        assert result.ok is True
        assert result.order_sent is False

    def test_mismatch_on_state_divergence(self):
        reconciler = DemoOrderReconciler()
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)
        sm.transition(DemoOrderState.ACKNOWLEDGED)
        sm.transition(DemoOrderState.FILLED)

        result = reconciler.reconcile(
            "order-001", sm,
            exchange_state="CANCELLED",
        )
        assert result.ok is False
        assert result.status == "MISMATCH"


# ── Recovery tests ────────────────────────────────────────────────────────────

class TestRecovery:
    def test_recovery_requires_manual_review(self):
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)
        sm.transition(DemoOrderState.RECOVERY_REQUIRED)

        recovery = DemoOrderRecovery()
        action = recovery.attempt_recovery("order-001", sm)
        assert action.action == "MANUAL_REVIEW"
        assert action.resolved is False

    def test_recovery_ambiguous_queries_first(self):
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)
        sm.transition(DemoOrderState.AMBIGUOUS)

        recovery = DemoOrderRecovery()
        action = recovery.attempt_recovery("order-001", sm)
        assert action.action == "QUERY_EXCHANGE"
        assert action.resolved is False

    def test_recovery_summary_no_resend(self):
        recovery = DemoOrderRecovery()
        d = recovery.summary()
        assert d["blindResendCount"] == 0
        assert d["orderSent"] is False


# ── Close controller tests ────────────────────────────────────────────────────

class TestCloseController:
    def test_close_blocked_by_adapter(self):
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)
        sm.transition(DemoOrderState.ACKNOWLEDGED)
        sm.transition(DemoOrderState.FILLED)

        controller = DemoCloseController()
        request = CloseRequest(
            order_id="order-001",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.001,
            reason="STOP_LOSS",
        )

        auth_result = controller.authorize_close(sm, request)
        assert auth_result.success is True
        assert sm.state == DemoOrderState.CLOSE_AUTHORIZED

        close_result = controller.attempt_close(sm, request)
        assert close_result.success is False
        assert sm.state == DemoOrderState.AMBIGUOUS
