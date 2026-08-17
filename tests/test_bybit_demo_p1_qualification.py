"""Offline P1 qualification gates — no live Bybit writes, no DSN required."""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_demo_execution.durable_order_ledger import (
    ALLOWED_TRANSITIONS,
    OrderIntent,
    make_order_link_id,
)
from backend.nexus_demo_execution.p1_qualification import (
    P1_GO_PHRASE,
    P1QualificationRunner,
    run_p1_qualification,
    sanitize_evidence,
)
from backend.nexus_persistence_pg.migrate import MigrationRunner, list_migrations


INSTRUMENT = {
    "status": "Trading",
    "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "minNotionalValue": "5"},
    "priceFilter": {"tickSize": "0.1"},
}


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.t = start

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += float(seconds)

    def now_ms(self) -> int:
        return int(self.t * 1000)


class MemoryLedger:
    def __init__(self) -> None:
        self.intents: dict[str, dict] = {}
        self._history: dict[str, list[dict]] = {}
        self.migrations = {"0001", "0005", "0006"}
        self.probe_ok = True

    def required_migrations_present(self) -> dict:
        missing = [item for item in ("0005", "0006") if item not in self.migrations]
        return {
            "ok": not missing,
            "present": sorted(self.migrations),
            "missing": missing,
            "migration_0005_present": "0005" in self.migrations,
            "migration_0006_present": "0006" in self.migrations,
        }

    def probe_write_read(self) -> dict:
        return {"ok": self.probe_ok}

    def unfinished(self) -> list[dict]:
        return [
            {
                "order_intent_id": item["order_intent_id"],
                "order_link_id": item["order_link_id"],
                "symbol": item["symbol"],
                "side": item["side"],
                "state": item["state"],
                "bybit_order_id": item.get("bybit_order_id"),
                "requested_qty": str(item["requested_qty"]),
                "filled_qty": str(item.get("filled_qty") or "0"),
            }
            for item in self.intents.values()
            if item["state"] not in {"CLOSED", "CANCELLED", "REJECTED"}
        ]

    def create_intent(self, intent: OrderIntent) -> str:
        link = make_order_link_id(intent.campaign_id, intent.decision_id, intent.order_intent_id)
        record = {
            "order_intent_id": intent.order_intent_id,
            "decision_id": intent.decision_id,
            "trade_id": intent.trade_id,
            "campaign_id": intent.campaign_id,
            "order_link_id": link,
            "symbol": intent.symbol,
            "side": intent.side,
            "requested_qty": intent.requested_qty,
            "reduce_only": intent.reduce_only,
            "parent_order_intent_id": intent.parent_order_intent_id,
            "state": "INTENT_CREATED",
            "filled_qty": Decimal("0"),
            "remaining_qty": intent.requested_qty,
        }
        self.intents[intent.order_intent_id] = record
        self._history[intent.order_intent_id] = [
            {"from_state": None, "to_state": "INTENT_CREATED", "source": "local_intent"}
        ]
        return link

    def transition(self, order_intent_id: str, state: str, *, source: str, exchange: dict | None = None) -> None:
        record = self.intents[order_intent_id]
        previous = record["state"]
        if state != previous and state not in ALLOWED_TRANSITIONS.get(previous, set()):
            raise ValueError(f"invalid_transition:{previous}->{state}")
        record["state"] = state
        exchange = exchange or {}
        if exchange.get("order_id"):
            record["bybit_order_id"] = exchange["order_id"]
        if exchange.get("status") is not None:
            record["exchange_status"] = exchange["status"]
        if exchange.get("filled_qty") is not None:
            record["filled_qty"] = exchange["filled_qty"]
        if exchange.get("remaining_qty") is not None:
            record["remaining_qty"] = exchange["remaining_qty"]
        if exchange.get("avg_fill_price") is not None:
            record["avg_fill_price"] = exchange["avg_fill_price"]
        self._history.setdefault(order_intent_id, []).append(
            {"from_state": previous, "to_state": state, "source": source, "detail": exchange}
        )

    def get_intent(self, order_intent_id: str) -> dict | None:
        record = self.intents.get(order_intent_id)
        if not record:
            return None
        out = dict(record)
        out["requested_qty"] = str(out["requested_qty"])
        out["filled_qty"] = str(out.get("filled_qty") or "0")
        return out

    def history(self, order_intent_id: str) -> list[dict]:
        return list(self._history.get(order_intent_id) or [])

    def record_accounting(self, order_intent_id: str, **kwargs) -> None:
        self.intents[order_intent_id].update({k: v for k, v in kwargs.items() if v is not None})


class FakeBybit:
    def __init__(self, ledger: MemoryLedger, *, now_ms: int) -> None:
        self.ledger = ledger
        self.base_url = DEMO_REST_BASE_URL
        self.api_key = "demo-key"
        self.api_secret = "demo-secret"
        self.write_call_count = 0
        self.urls_called: list[str] = []
        self.create_states: list[str] = []
        self.ticker_time = now_ms
        self.last_price = 100_000.0
        self.open_orders: list[dict] = []
        self.positions: list[dict] = []
        self.orders: dict[str, dict] = {}
        self.executions: list[dict] = []
        self.closed_pnls: list[dict] = []
        self.wallet_before = {
            "wallet_balance": "1000",
            "coin_balance": "1000",
            "source_endpoint": "/v5/account/wallet-balance",
        }
        self.wallet_after = {
            "wallet_balance": "999.8",
            "coin_balance": "999.8",
            "source_endpoint": "/v5/account/wallet-balance",
        }
        self._wallet = dict(self.wallet_before)
        self.fail_create = False

    def fetch_ticker(self, symbol: str) -> dict:
        return {"lastPrice": str(self.last_price), "markPrice": str(self.last_price), "time": str(self.ticker_time)}

    def fetch_instrument(self, symbol: str) -> dict:
        return dict(INSTRUMENT)

    def qty_step(self, info: dict) -> float:
        return float(info["lotSizeFilter"]["qtyStep"])

    def min_qty(self, info: dict) -> float:
        return float(info["lotSizeFilter"]["minOrderQty"])

    def min_notional(self, info: dict) -> float:
        return float(info["lotSizeFilter"]["minNotionalValue"])

    def tick_size(self, info: dict) -> float:
        return float(info["priceFilter"]["tickSize"])

    def format_price(self, price: float, tick: float) -> str:
        return f"{price:.1f}"

    def fetch_account_identity(self) -> dict:
        return {
            "exchange_domain": "api-demo.bybit.com",
            "api_key_fingerprint": "abc123",
            "account_uid": "demo-uid",
            "wallet_context": "UNIFIED",
        }

    def fetch_wallet_snapshot(self, **kwargs) -> dict:
        return dict(self._wallet)

    def list_open_orders(self, symbol: str | None = None) -> list[dict]:
        return list(self.open_orders)

    def list_positions(self, symbol: str | None = None) -> list[dict]:
        return list(self.positions)

    def list_executions(self, *, symbol: str | None = None, limit: int = 50) -> list[dict]:
        return list(self.executions)

    def list_closed_pnl(self, *, symbol: str | None = None, limit: int = 50) -> list[dict]:
        return list(self.closed_pnls)

    def find_order(self, *, symbol: str, order_id: str = "", order_link_id: str = "") -> dict | None:
        if order_link_id and order_link_id in self.orders:
            return self.orders[order_link_id]
        for item in self.orders.values():
            if order_id and item.get("orderId") == order_id:
                return item
        return None

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        self.write_call_count += 1
        self.urls_called.append("/v5/position/set-leverage")
        return {"retCode": 0}

    def create_market_order(self, **kwargs) -> dict:
        unfinished = self.ledger.unfinished()
        self.create_states.append(unfinished[0]["state"] if unfinished else "MISSING")
        if self.fail_create:
            raise AssertionError("create_market_order_should_not_run")
        self.write_call_count += 1
        self.urls_called.append("/v5/order/create")
        link = kwargs["order_link_id"]
        order = {
            "orderId": "ord-entry-1",
            "orderLinkId": link,
            "orderStatus": "Filled",
            "qty": kwargs["qty"],
            "cumExecQty": kwargs["qty"],
            "avgPrice": str(self.last_price),
            "symbol": kwargs["symbol"],
            "side": kwargs["side"],
        }
        self.orders[link] = order
        self.positions = [
            {"symbol": kwargs["symbol"], "side": kwargs["side"], "size": kwargs["qty"], "avgPrice": str(self.last_price)}
        ]
        self.executions.append(
            {
                "orderId": "ord-entry-1",
                "execId": "ex-entry-1",
                "execPrice": str(self.last_price),
                "execQty": kwargs["qty"],
                "execFee": "0.1",
                "symbol": kwargs["symbol"],
            }
        )
        return {"retCode": 0, "result": {"orderId": "ord-entry-1", "orderLinkId": link}}

    def close_reduce_only(self, **kwargs) -> dict:
        self.write_call_count += 1
        self.urls_called.append("/v5/order/create")
        link = kwargs["order_link_id"]
        qty = kwargs["qty"]
        order = {
            "orderId": "ord-close-1",
            "orderLinkId": link,
            "orderStatus": "Filled",
            "qty": qty,
            "cumExecQty": qty,
            "avgPrice": str(self.last_price + 1),
            "symbol": kwargs["symbol"],
            "side": "Sell",
            "reduceOnly": True,
        }
        self.orders[link] = order
        self.positions = []
        self._wallet = dict(self.wallet_after)
        self.executions.append(
            {
                "orderId": "ord-close-1",
                "execId": "ex-close-1",
                "execPrice": str(self.last_price + 1),
                "execQty": qty,
                "execFee": "0.1",
                "symbol": kwargs["symbol"],
                "reduceOnly": True,
            }
        )
        self.closed_pnls.append(
            {
                "orderId": "ord-close-1",
                "closedPnl": "-0.2",
                "avgEntryPrice": str(self.last_price),
                "avgExitPrice": str(self.last_price + 1),
                "openFee": "0.1",
                "closeFee": "0.1",
            }
        )
        return {"retCode": 0, "result": {"orderId": "ord-close-1", "orderLinkId": link}}


def _auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDER_P1_APPROVED", "true")
    monkeypatch.setenv("P1_GO", P1_GO_PHRASE)
    monkeypatch.setenv("BYBIT_DEMO_API_KEY", "demo-key")
    monkeypatch.setenv("BYBIT_DEMO_API_SECRET", "demo-secret")
    monkeypatch.setenv("MAINNET", "false")
    monkeypatch.setenv("REAL_MONEY", "false")
    monkeypatch.setenv("DEMO_AUTONOMOUS_ENABLED", "false")


def _run(monkeypatch, client, ledger, clock: FakeClock | None = None, **kwargs):
    clock = clock or FakeClock()
    return run_p1_qualification(
        client=client,
        ledger=ledger,
        sleep=clock.sleep,
        now_ms=clock.now_ms,
        time_fn=clock.time,
        apply_pending_schema=lambda: {"ok": True, "applied": []},
        fill_timeout_sec=kwargs.get("fill_timeout_sec", 5),
        close_timeout_sec=kwargs.get("close_timeout_sec", 5),
    )


def test_authorization_denies_create_order(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FOUNDER_P1_APPROVED", raising=False)
    monkeypatch.delenv("P1_GO", raising=False)
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=1_000_000)
    client.fail_create = True
    evidence = _run(monkeypatch, client, ledger)
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    assert evidence["create_order_calls"] == 0
    assert client.write_call_count == 0
    assert "/v5/order/create" not in client.urls_called
    assert evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] == "HOLD"


def test_preflight_fails_on_missing_migration(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    ledger = MemoryLedger()
    ledger.migrations.remove("0005")
    client = FakeBybit(ledger, now_ms=int(FakeClock().t * 1000))
    client.fail_create = True
    clock = FakeClock()
    client.ticker_time = clock.now_ms()
    evidence = _run(monkeypatch, client, ledger, clock)
    assert evidence["P1_PREFLIGHT_PASS"] is False
    assert evidence["BYBIT_DEMO_P1_LEDGER_CONNECTION_PASS"] is False
    assert client.write_call_count == 0


def test_preflight_fails_on_open_position(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms()
    client.positions = [{"symbol": "BTCUSDT", "size": "0.001", "side": "Buy"}]
    client.fail_create = True
    evidence = _run(monkeypatch, client, ledger, clock)
    assert evidence["PRE_ENTRY_RECONCILIATION_PASS"] is False
    assert evidence["create_order_calls"] == 0
    assert client.write_call_count == 0


def test_preflight_fails_on_stale_ticker(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms() - 60_000
    client.fail_create = True
    evidence = _run(monkeypatch, client, ledger, clock)
    assert evidence["FRESH_OFFICIAL_EXECUTION_DATA_PASS"] is False
    assert evidence["NO_MOCK_EXECUTION_PRICE_PASS"] is False
    assert evidence["create_order_calls"] == 0


def test_preflight_fails_on_mainnet_flag(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    monkeypatch.setenv("MAINNET", "true")
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms()
    client.fail_create = True
    evidence = _run(monkeypatch, client, ledger, clock)
    assert evidence["P1_PREFLIGHT_PASS"] is False
    assert client.write_call_count == 0


def test_intent_persisted_before_submit(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms()
    evidence = _run(monkeypatch, client, ledger, clock)
    assert client.create_states == ["SUBMITTING"]
    assert evidence["P1_ENTRY_RECONCILIATION_PASS"] is True


def test_happy_path_flat_position_and_exchange_pnl(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms()
    evidence = _run(monkeypatch, client, ledger, clock)
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "PASS"
    assert evidence["P1_CLOSE_RECONCILIATION_PASS"] is True
    assert evidence["P1_EXCHANGE_REALIZED_PNL_PASS"] is True
    assert evidence["P1_DURABLE_LEDGER_LIFECYCLE_PASS"] is True
    assert evidence["final_position_qty"] == "0"
    assert evidence["realized_demo_pnl"] == "-0.2"
    assert evidence["ledger_final_state"] == "CLOSED"
    assert evidence["recurring_loop"] is False
    assert evidence["process_flags"]["DEMO_AUTONOMOUS_ENABLED"] == "false"
    assert evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] == "HOLD"
    assert "INTENT_CREATED" in evidence["ledger_states"]
    assert "CLOSE_PENDING" in evidence["ledger_states"]


def test_ack_is_not_treated_as_fill(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms()

    def create_only_ack(**kwargs):
        client.write_call_count += 1
        client.urls_called.append("/v5/order/create")
        client.create_states.append(client.ledger.unfinished()[0]["state"])
        link = kwargs["order_link_id"]
        client.orders[link] = {
            "orderId": "ord-entry-1",
            "orderLinkId": link,
            "orderStatus": "New",
            "qty": kwargs["qty"],
            "cumExecQty": "0",
            "avgPrice": "0",
        }
        return {"retCode": 0, "result": {"orderId": "ord-entry-1", "orderLinkId": link}}

    client.create_market_order = create_only_ack  # type: ignore[method-assign]
    evidence = _run(monkeypatch, client, ledger, clock, fill_timeout_sec=2)
    assert evidence["P1_ENTRY_RECONCILIATION_PASS"] is False
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    assert evidence["create_order_calls"] == 1


def test_nonzero_close_position_fail_closed(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms()

    def close_but_remain(**kwargs):
        client.write_call_count += 1
        client.urls_called.append("/v5/order/create")
        link = kwargs["order_link_id"]
        client.orders[link] = {
            "orderId": "ord-close-1",
            "orderLinkId": link,
            "orderStatus": "Filled",
            "qty": kwargs["qty"],
            "cumExecQty": kwargs["qty"],
            "avgPrice": "100001",
        }
        return {"retCode": 0, "result": {"orderId": "ord-close-1"}}

    client.close_reduce_only = close_but_remain  # type: ignore[method-assign]
    evidence = _run(monkeypatch, client, ledger, clock)
    assert evidence["P1_CLOSE_RECONCILIATION_PASS"] is False
    assert evidence["fail_closed"] is True
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"
    entry = next(item for item in ledger.intents.values() if not item.get("reduce_only"))
    assert entry["state"] != "CLOSED"


def test_create_failure_stays_submit_unknown_without_retry(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms()

    def boom(**kwargs):
        client.write_call_count += 1
        client.urls_called.append("/v5/order/create")
        raise RuntimeError("transport")

    client.create_market_order = boom  # type: ignore[method-assign]
    evidence = _run(monkeypatch, client, ledger, clock)
    assert evidence["create_order_calls"] == 1
    assert client.urls_called.count("/v5/order/create") == 1
    entry = next(item for item in ledger.intents.values() if not item.get("reduce_only"))
    assert entry["state"] == "SUBMIT_UNKNOWN"
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"


def test_unrelated_closed_pnl_is_not_attributed(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms()
    original_close = client.close_reduce_only

    def close_with_foreign_pnl(**kwargs):
        resp = original_close(**kwargs)
        client.closed_pnls = [{"orderId": "historical-other", "closedPnl": "99.9"}]
        return resp

    client.close_reduce_only = close_with_foreign_pnl  # type: ignore[method-assign]
    evidence = _run(monkeypatch, client, ledger, clock)
    assert evidence["P1_EXCHANGE_REALIZED_PNL_PASS"] is False
    assert evidence["realized_demo_pnl"] is None
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"


def test_synthetic_pnl_is_not_labelled_exchange(monkeypatch: pytest.MonkeyPatch):
    _auth_env(monkeypatch)
    clock = FakeClock()
    ledger = MemoryLedger()
    client = FakeBybit(ledger, now_ms=clock.now_ms())
    client.ticker_time = clock.now_ms()
    original_close = client.close_reduce_only

    def close_without_pnl(**kwargs):
        resp = original_close(**kwargs)
        client.closed_pnls = []
        return resp

    client.close_reduce_only = close_without_pnl  # type: ignore[method-assign]
    evidence = _run(monkeypatch, client, ledger, clock)
    assert evidence["P1_EXCHANGE_REALIZED_PNL_PASS"] is False
    assert evidence["realized_demo_pnl"] is None
    assert evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "HOLD"


def test_sanitize_evidence_strips_secrets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BYBIT_DEMO_API_SECRET", "super-secret-value")
    payload = sanitize_evidence({"note": "super-secret-value", "api_secret": "super-secret-value"})
    assert "super-secret-value" not in json.dumps(payload)


def test_migration_0006_is_forward_only():
    files = {item.version: item for item in list_migrations()}
    assert "0005" in files
    assert "0006" in files
    assert "DROP TABLE" not in files["0006"].sql.upper()
    assert "parent_order_intent_id" in files["0006"].sql
    assert MigrationRunner().validate()["ok"] is True


@pytest.mark.skipif(
    not (os.getenv("NEXUS_P1_LEDGER_ITEST_URL") or "").strip(),
    reason="P1 ledger integration test requires NEXUS_P1_LEDGER_ITEST_URL",
)
def test_postgres_ledger_write_read_and_history(monkeypatch: pytest.MonkeyPatch):
    from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger
    from backend.nexus_persistence_pg.pool import PostgresPool

    monkeypatch.setenv("NEXUS_ENV", "TEST")
    monkeypatch.setenv("NEXUS_POSTGRES_URL", os.environ["NEXUS_P1_LEDGER_ITEST_URL"])
    pool = PostgresPool(os.environ["NEXUS_P1_LEDGER_ITEST_URL"])
    pool.open()
    try:
        applied = MigrationRunner().apply_pending(pool)
        assert applied["ok"] is True
        ledger = DurableOrderLedger(pool)
        present = ledger.required_migrations_present()
        assert present["migration_0005_present"] is True
        assert present["ok"] is True
        probe = ledger.probe_write_read()
        assert probe["ok"] is True
        intent = OrderIntent(
            order_intent_id="p1itest_entry",
            decision_id="p1itest_dec",
            trade_id="p1itest_trd",
            campaign_id="p1itest",
            symbol="BTCUSDT",
            side="Buy",
            requested_qty=Decimal("0.001"),
            order_type="Market",
        )
        link = ledger.create_intent(intent)
        assert link.startswith("nx-")
        ledger.transition("p1itest_entry", "SUBMITTING", source="test")
        history = ledger.history("p1itest_entry")
        assert [row["to_state"] for row in history] == ["INTENT_CREATED", "SUBMITTING"]
        ledger.transition("p1itest_entry", "REJECTED", source="test_cleanup")
    finally:
        pool.close()
