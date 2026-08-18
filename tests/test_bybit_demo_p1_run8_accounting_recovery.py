"""Offline Run #8 accounting recovery — no live Bybit writes."""
from __future__ import annotations

import json

import pytest

from backend.nexus_demo_execution.durable_order_ledger import ALLOWED_TRANSITIONS
from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID
from backend.nexus_demo_execution.p1_exchange_accounting import match_closed_pnl_by_close_order_id
from backend.nexus_demo_execution.p1_run8_accounting_recovery import (
    PNL_PROVENANCE,
    ReadOnlyExchangeClient,
    identify_latest_p1_lifecycle,
    recover_run8_accounting,
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 1_000.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))
        self.t += float(seconds)


class FakeLedger:
    def __init__(self) -> None:
        self.intents: dict[str, dict] = {}
        self.accounting_writes = 0
        self.transitions: list[tuple[str, str]] = []

    def list_campaign_intents(self, campaign_id: str) -> list[dict]:
        return [dict(row) for row in self.intents.values() if row.get("campaign_id") == campaign_id]

    def get_intent(self, order_intent_id: str) -> dict | None:
        row = self.intents.get(order_intent_id)
        return dict(row) if row else None

    def transition(self, order_intent_id: str, state: str, *, source: str, exchange: dict | None = None) -> None:
        record = self.intents[order_intent_id]
        previous = record["state"]
        if state != previous and state not in ALLOWED_TRANSITIONS.get(previous, set()):
            raise ValueError(f"invalid_transition:{previous}->{state}")
        record["state"] = state
        self.transitions.append((order_intent_id, state))

    def record_accounting(self, order_intent_id: str, **kwargs) -> None:
        self.accounting_writes += 1
        record = self.intents[order_intent_id]
        for key, value in kwargs.items():
            if value is not None:
                record[key] = value


class FakeClient:
    def __init__(self) -> None:
        self.write_call_count = 0
        self.create_order_calls = 0
        self.orders: dict[str, dict] = {}
        self.positions: list[dict] = []
        self.open_orders: list[dict] = []
        self.executions: list[dict] = []
        self.closed_pnl_pages: list[list[dict]] = []
        self.closed_pnl_calls = 0

    def find_order(self, *, symbol: str, order_id: str = "", order_link_id: str = "") -> dict | None:
        if order_id and order_id in self.orders:
            return dict(self.orders[order_id])
        for row in self.orders.values():
            if order_link_id and row.get("orderLinkId") == order_link_id:
                return dict(row)
        return None

    def list_positions(self, symbol: str | None = None) -> list[dict]:
        return [dict(row) for row in self.positions if abs(float(row.get("size") or 0)) > 0]

    def list_open_orders(self, symbol: str | None = None) -> list[dict]:
        return [dict(row) for row in self.open_orders]

    def list_executions(self, *, symbol: str | None = None, limit: int = 50, order_id: str | None = None) -> list[dict]:
        rows = [dict(row) for row in self.executions]
        if order_id:
            rows = [row for row in rows if str(row.get("orderId") or "") == str(order_id)]
        return rows[:limit]

    def list_closed_pnl(self, *, symbol: str | None = None, limit: int = 50) -> list[dict]:
        return self.list_closed_pnl_paginated(symbol=symbol, limit=limit)

    def list_closed_pnl_paginated(
        self,
        *,
        symbol: str | None = None,
        limit: int = 100,
        max_pages: int = 10,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[dict]:
        del symbol, max_pages, start_time_ms, end_time_ms
        self.closed_pnl_calls += 1
        if not self.closed_pnl_pages:
            return []
        index = min(self.closed_pnl_calls - 1, len(self.closed_pnl_pages) - 1)
        return [dict(row) for row in self.closed_pnl_pages[index][:limit]]

    def create_market_order(self, **kwargs) -> dict:
        self.write_call_count += 1
        self.create_order_calls += 1
        raise AssertionError("create_market_order_forbidden")

    def close_reduce_only(self, **kwargs) -> dict:
        self.write_call_count += 1
        self.create_order_calls += 1
        raise AssertionError("close_reduce_only_forbidden")

    def cancel_order(self, **kwargs) -> dict:
        self.write_call_count += 1
        raise AssertionError("cancel_order_forbidden")


def _seed_run8(ledger: FakeLedger) -> None:
    ledger.intents["p1ent_run8"] = {
        "order_intent_id": "p1ent_run8",
        "decision_id": "p1dec_run8aaaaaaaa",
        "trade_id": "p1trd_run8bbbbbbbb",
        "campaign_id": P1_CAMPAIGN_ID,
        "order_link_id": "nx-entry-run8",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "requested_qty": "0.001",
        "reduce_only": False,
        "state": "CLOSED",
        "bybit_order_id": "entry-oid-run8",
        "filled_qty": "0.001",
        "parent_order_intent_id": None,
        "created_at": "2026-08-18T07:00:00Z",
        "actual_entry_price": None,
        "actual_exit_price": None,
        "realized_demo_pnl": None,
        "pnl_provenance": "STRATEGY_OUTCOME_MODEL",
    }
    ledger.intents["p1cls_run8"] = {
        "order_intent_id": "p1cls_run8",
        "decision_id": "p1dec_run8aaaaaaaa",
        "trade_id": "p1trd_run8bbbbbbbb",
        "campaign_id": P1_CAMPAIGN_ID,
        "order_link_id": "nx-close-run8",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "requested_qty": "0.001",
        "reduce_only": True,
        "state": "CLOSED",
        "bybit_order_id": "close-oid-run8",
        "filled_qty": "0.001",
        "parent_order_intent_id": "p1ent_run8",
        "created_at": "2026-08-18T07:01:00Z",
    }


def _seed_exchange(client: FakeClient, *, delayed: bool = False) -> None:
    client.orders = {
        "entry-oid-run8": {
            "orderId": "entry-oid-run8",
            "orderLinkId": "nx-entry-run8",
            "orderStatus": "Filled",
            "qty": "0.001",
            "cumExecQty": "0.001",
        },
        "close-oid-run8": {
            "orderId": "close-oid-run8",
            "orderLinkId": "nx-close-run8",
            "orderStatus": "Filled",
            "qty": "0.001",
            "cumExecQty": "0.001",
        },
    }
    client.executions = [
        {"orderId": "entry-oid-run8", "execQty": "0.001", "execPrice": "65000", "execFee": "0.02"},
        {"orderId": "close-oid-run8", "execQty": "0.001", "execPrice": "64990", "execFee": "0.02"},
    ]
    exact = {
        "orderId": "close-oid-run8",
        "symbol": "BTCUSDT",
        "avgEntryPrice": "65000",
        "avgExitPrice": "64990",
        "closedSize": "0.001",
        "closedPnl": "-0.21",
        "openFee": "0.02",
        "closeFee": "0.02",
        "createdTime": "1710000000000",
        "updatedTime": "1710000060000",
    }
    historical = {
        "orderId": "historical-other",
        "symbol": "BTCUSDT",
        "avgEntryPrice": "1",
        "avgExitPrice": "2",
        "closedSize": "9",
        "closedPnl": "99.9",
        "openFee": "1",
        "closeFee": "1",
    }
    if delayed:
        client.closed_pnl_pages = [[historical], [historical], [historical, exact]]
    else:
        client.closed_pnl_pages = [[historical, exact]]


def _run(ledger: FakeLedger, client: FakeClient, clock: FakeClock | None = None, **kwargs):
    clock = clock or FakeClock()
    return recover_run8_accounting(
        client=client,
        ledger=ledger,
        sleep=clock.sleep,
        time_fn=clock.time,
        poll_interval_sec=kwargs.get("poll_interval_sec", 2.0),
        poll_timeout_sec=kwargs.get("poll_timeout_sec", 60.0),
    )


def test_exact_close_order_id_match_finalizes_existing_run8_without_new_trade():
    ledger = FakeLedger()
    client = FakeClient()
    _seed_run8(ledger)
    _seed_exchange(client)
    evidence = _run(ledger, client)
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "PASS"
    assert evidence["P1_EXCHANGE_REALIZED_PNL_PASS"] is True
    assert evidence["P1_DURABLE_LEDGER_LIFECYCLE_PASS"] is True
    assert evidence["P1_RUN8_EXACT_CLOSED_PNL_MATCH"] is True
    assert evidence["ledger_final_state"] == "CLOSED"
    assert evidence["realized_demo_pnl"] == "-0.21"
    assert evidence["pnl_provenance"] == PNL_PROVENANCE
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    assert client.create_order_calls == 0
    assert ledger.intents["p1ent_run8"]["realized_demo_pnl"] == "-0.21"
    assert ledger.intents["p1ent_run8"]["trade_id"] == "p1trd_run8bbbbbbbb"


def test_unrelated_historical_closed_pnl_row_is_rejected():
    rows = [
        {"orderId": "historical-other", "closedPnl": "99.9"},
        {"orderId": "close-oid-run8", "closedPnl": "-0.21"},
    ]
    matched = match_closed_pnl_by_close_order_id(rows, "close-oid-run8")
    assert matched is not None
    assert matched["closedPnl"] == "-0.21"
    assert match_closed_pnl_by_close_order_id(rows, "missing") is None
    assert identify_latest_p1_lifecycle([]) is None


def test_delayed_closed_pnl_appears_during_bounded_polling():
    ledger = FakeLedger()
    client = FakeClient()
    clock = FakeClock()
    _seed_run8(ledger)
    _seed_exchange(client, delayed=True)
    evidence = _run(ledger, client, clock, poll_interval_sec=2.0, poll_timeout_sec=60.0)
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "PASS"
    assert evidence["closed_pnl_poll_attempts"] == 3
    assert clock.sleeps == [2.0, 2.0]
    assert evidence["create_order_calls"] == 0


def test_polling_timeout_remains_hold():
    ledger = FakeLedger()
    client = FakeClient()
    clock = FakeClock()
    _seed_run8(ledger)
    _seed_exchange(client)
    client.closed_pnl_pages = [[{"orderId": "historical-other", "closedPnl": "99.9"}]]
    evidence = _run(ledger, client, clock, poll_interval_sec=2.0, poll_timeout_sec=4.0)
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    assert evidence["P1_EXCHANGE_REALIZED_PNL_PASS"] is False
    assert evidence["error"] == "exact_closed_pnl_unavailable"
    assert evidence["create_order_calls"] == 0
    assert ledger.accounting_writes == 0


def test_nonzero_position_blocks_ledger_finalization():
    ledger = FakeLedger()
    client = FakeClient()
    _seed_run8(ledger)
    _seed_exchange(client)
    client.positions = [{"symbol": "BTCUSDT", "size": "0.001"}]
    evidence = _run(ledger, client)
    assert evidence["P1_RUN8_POSITION_FLAT"] is False
    assert evidence["P1_RUN8_LEDGER_FINALIZED"] is False
    assert evidence["error"] == "position_not_flat"
    assert ledger.accounting_writes == 0
    assert evidence["create_order_calls"] == 0


def test_exchange_ledger_evidence_conflict_remains_hold():
    ledger = FakeLedger()
    client = FakeClient()
    _seed_run8(ledger)
    _seed_exchange(client)
    ledger.intents["p1ent_run8"]["realized_demo_pnl"] = "-9.99"
    ledger.intents["p1ent_run8"]["pnl_provenance"] = PNL_PROVENANCE
    evidence = _run(ledger, client)
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    assert evidence["error"] == "exchange_ledger_evidence_conflict"
    assert ledger.intents["p1ent_run8"]["realized_demo_pnl"] == "-9.99"
    assert ledger.accounting_writes == 0
    assert evidence["create_order_calls"] == 0


def test_recovery_is_idempotent_for_already_finalized_run8():
    ledger = FakeLedger()
    client = FakeClient()
    _seed_run8(ledger)
    _seed_exchange(client)
    first = _run(ledger, client)
    assert first["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "PASS"
    writes_after_first = ledger.accounting_writes
    second = _run(ledger, client)
    assert second["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "PASS"
    assert second["idempotent"] is True
    assert ledger.accounting_writes == writes_after_first
    assert second["create_order_calls"] == 0
    assert second["trade_id_prefix"] == "p1trd_ru"


def test_zero_exchange_write_calls_and_write_wrapper_blocks_create():
    inner = FakeClient()
    guarded = ReadOnlyExchangeClient(inner)
    with pytest.raises(RuntimeError, match="exchange_write_blocked"):
        guarded.create_market_order(symbol="BTCUSDT")
    assert guarded.create_order_calls == 1
    assert guarded.write_call_count == 1
    ledger = FakeLedger()
    client = FakeClient()
    _seed_run8(ledger)
    _seed_exchange(client)
    evidence = _run(ledger, client)
    assert evidence["exchange_write_call_count"] == 0
    assert evidence["create_order_calls"] == 0


def test_existing_run8_can_become_e2e_pass_without_a_new_trade():
    ledger = FakeLedger()
    client = FakeClient()
    _seed_run8(ledger)
    _seed_exchange(client)
    evidence = _run(ledger, client)
    assert evidence["run8_trade_already_occurred"] is True
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "PASS"
    assert evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] == "HOLD"
    assert set(ledger.intents) == {"p1ent_run8", "p1cls_run8"}
    assert evidence["create_order_calls"] == 0


def test_zero_or_multiple_candidates_hold():
    ledger = FakeLedger()
    client = FakeClient()
    _seed_exchange(client)
    evidence = _run(ledger, client)
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    assert evidence["candidate_count"] == 0
    _seed_run8(ledger)
    clone_entry = dict(ledger.intents["p1ent_run8"])
    clone_close = dict(ledger.intents["p1cls_run8"])
    clone_entry["order_intent_id"] = "p1ent_other"
    clone_entry["trade_id"] = "p1trd_otherbbbbbb"
    clone_entry["decision_id"] = "p1dec_otheraaaaaa"
    clone_entry["bybit_order_id"] = "entry-oid-other"
    clone_close["order_intent_id"] = "p1cls_other"
    clone_close["trade_id"] = "p1trd_otherbbbbbb"
    clone_close["decision_id"] = "p1dec_otheraaaaaa"
    clone_close["bybit_order_id"] = "close-oid-other"
    clone_close["parent_order_intent_id"] = "p1ent_other"
    ledger.intents["p1ent_other"] = clone_entry
    ledger.intents["p1cls_other"] = clone_close
    evidence = _run(ledger, client)
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    assert evidence["candidate_count"] == 2
    assert evidence["create_order_calls"] == 0


def test_bootstrap_exception_writes_nonempty_sanitized_evidence(tmp_path, monkeypatch):
    evidence_path = tmp_path / "p1_run8_accounting_recovery_evidence.json"
    bootstrap_path = tmp_path / "p1_run8_bootstrap_failure.json"
    monkeypatch.setenv("P1_EVIDENCE_PATH", str(evidence_path))
    monkeypatch.setenv("P1_BOOTSTRAP_FAILURE_PATH", str(bootstrap_path))
    import backend.nexus_demo_execution.p1_run8_accounting_recovery_bootstrap as bootstrap

    class Boom(Exception):
        pass

    def explode():
        raise Boom("postgres://user:secret@host/db")

    monkeypatch.setattr(
        "backend.nexus_demo_execution.p1_run8_accounting_recovery.run_recovery_with_probes",
        explode,
    )
    rc = bootstrap.main()
    assert rc == 1
    assert not evidence_path.exists()
    fail = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    assert fail["recovery_stage"] == "MODULE_IMPORT"
    assert fail["exception_type"] == "Boom"
    assert "postgres://" not in json.dumps(fail)
    assert fail["create_order_calls"] == 0
    assert fail["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
