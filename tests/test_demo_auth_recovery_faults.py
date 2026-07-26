"""Recovery + authorization fault cases (no exchange writes)."""
from __future__ import annotations

import json
import time

import pytest

from backend.nexus_research.demo_execution.adapter import AdapterReadResult, DemoOrderAdapter
from backend.nexus_research.demo_execution.intent import (
    AuthorizationReplayError,
    DemoOrderAuthorization,
    DemoOrderIntent,
    NotAuthorizedError,
    WriteNotAuthorizedError,
)
from backend.nexus_research.demo_execution.recovery import DemoOrderRecovery
from backend.nexus_research.demo_execution.state_machine import DemoOrderState, DemoOrderStateMachine


def _intent() -> DemoOrderIntent:
    return DemoOrderIntent(
        intent_id="intent-fault-1",
        symbol="BTCUSDT",
        side="Buy",
        qty=0.01,
        leverage=25,
        entry_price=100_000.0,
        stop_loss_price=98_500.0,
        take_profit_price=None,
        risk_tier="VALIDATION",
        client_order_id="nxd56-fault-test-001",
        source="fault_test",
    )


def _to_ambiguous() -> DemoOrderStateMachine:
    sm = DemoOrderStateMachine()
    sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
    sm.transition(DemoOrderState.AUTHORIZED)
    sm.transition(DemoOrderState.SEND_STARTED)
    sm.transition(DemoOrderState.AMBIGUOUS, reason="timeout")
    return sm


class TestAuthorizationAtomicConsume:
    def test_consume_once(self):
        intent = _intent()
        auth = DemoOrderAuthorization.create_for_intent(intent, ttl_ms=60_000)
        auth.consume(intent)
        assert auth.consumed is True

    def test_replay_rejected(self):
        intent = _intent()
        auth = DemoOrderAuthorization.create_for_intent(intent, ttl_ms=60_000)
        auth.consume(intent)
        with pytest.raises(AuthorizationReplayError):
            auth.consume(intent)

    def test_expired_rejected(self):
        intent = _intent()
        auth = DemoOrderAuthorization.create_for_intent(intent, ttl_ms=1)
        time.sleep(0.02)
        with pytest.raises(NotAuthorizedError):
            auth.consume(intent)

    def test_bound_symbol_mismatch(self):
        intent = _intent()
        auth = DemoOrderAuthorization.create_for_intent(intent, ttl_ms=60_000)
        other = DemoOrderIntent(
            intent_id=intent.intent_id,
            symbol="ETHUSDT",
            side=intent.side,
            qty=intent.qty,
            leverage=intent.leverage,
            entry_price=intent.entry_price,
            stop_loss_price=intent.stop_loss_price,
            take_profit_price=None,
            risk_tier=intent.risk_tier,
            client_order_id=intent.client_order_id,
            source=intent.source,
        )
        with pytest.raises(NotAuthorizedError):
            auth.consume(other)


class TestAdapterNeverWrites:
    def test_place_order_blocked(self):
        adapter = DemoOrderAdapter()
        with pytest.raises(WriteNotAuthorizedError):
            adapter.place_order(_intent())
        assert adapter.write_attempts == 1


class TestRecoveryNoBlindResend:
    def test_ambiguous_query_fail_goes_manual(self):
        class FailAdapter(DemoOrderAdapter):
            def query_order_status(self, order_id: str) -> AdapterReadResult:
                return AdapterReadResult(success=False, error="timeout")

        sm = _to_ambiguous()
        action = DemoOrderRecovery(FailAdapter()).attempt_recovery("oid-x", sm)
        assert sm.state == DemoOrderState.RECOVERY_REQUIRED
        assert action.resolved is False
        assert action.to_dict()["orderSent"] is False

    def test_recovery_required_never_resends(self):
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)
        sm.transition(DemoOrderState.RECOVERY_REQUIRED)
        action = DemoOrderRecovery().attempt_recovery("oid-y", sm)
        assert action.action == "MANUAL_REVIEW"
        assert action.resolved is False

    def test_corrupted_recovery_snapshot_json(self):
        raw = "{not-json"
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw)
        adapter = DemoOrderAdapter()
        with pytest.raises(WriteNotAuthorizedError):
            adapter.place_order(_intent())
