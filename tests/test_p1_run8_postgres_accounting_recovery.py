"""Optional PostgreSQL Run #8 recovery tests — require NEXUS_P1_LEDGER_ITEST_URL or NEXUS_TEST_DATABASE_URL."""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger, OrderIntent
from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID
from backend.nexus_demo_execution.p1_run8_accounting_recovery import PNL_PROVENANCE, recover_run8_accounting
from backend.nexus_persistence_pg.migrate import MigrationRunner
from backend.nexus_persistence_pg.pool import PostgresPool
from tests.test_bybit_demo_p1_run8_accounting_recovery import FakeClient, FakeClock, _seed_exchange


pytestmark = pytest.mark.skipif(
    not (os.getenv("NEXUS_P1_LEDGER_ITEST_URL") or "").strip(),
    reason="PostgreSQL integration requires NEXUS_P1_LEDGER_ITEST_URL",
)


def test_postgres_run8_provisional_provenance_upgrades_with_exact_closed_pnl(monkeypatch):
    url = (os.getenv("NEXUS_P1_LEDGER_ITEST_URL") or "").strip()
    monkeypatch.setenv("NEXUS_ENV", "TEST")
    monkeypatch.setenv("NEXUS_POSTGRES_URL", url)
    pool = PostgresPool(url)
    pool.open()
    try:
        applied = MigrationRunner().apply_pending(pool)
        assert applied["ok"] is True
        ledger = DurableOrderLedger(pool)
        present = ledger.required_migrations_present()
        assert present["migration_0005_present"] is True
        assert present["migration_0006_present"] is True
        entry = OrderIntent(
            order_intent_id="p1pg_entry_run8",
            decision_id="p1pg_dec_run8",
            trade_id="p1pg_trd_run8",
            campaign_id=P1_CAMPAIGN_ID,
            symbol="BTCUSDT",
            side="Buy",
            requested_qty=Decimal("0.001"),
            order_type="Market",
        )
        close = OrderIntent(
            order_intent_id="p1pg_close_run8",
            decision_id="p1pg_dec_run8",
            trade_id="p1pg_trd_run8",
            campaign_id=P1_CAMPAIGN_ID,
            symbol="BTCUSDT",
            side="Sell",
            requested_qty=Decimal("0.001"),
            order_type="Market",
            reduce_only=True,
            parent_order_intent_id="p1pg_entry_run8",
        )
        ledger.create_intent(entry)
        ledger.create_intent(close)
        for state in ("SUBMITTING", "ACCEPTED", "FILLED", "CLOSE_PENDING", "CLOSED"):
            try:
                ledger.transition("p1pg_entry_run8", state, source="seed", exchange={"order_id": "entry-oid-run8"})
            except ValueError:
                pass
        for state in ("SUBMITTING", "ACCEPTED", "FILLED", "CLOSED"):
            try:
                ledger.transition("p1pg_close_run8", state, source="seed", exchange={"order_id": "close-oid-run8"})
            except ValueError:
                pass
        ledger.record_accounting("p1pg_entry_run8", pnl_provenance="STRATEGY_OUTCOME_MODEL")
        client = FakeClient()
        _seed_exchange(client)
        clock = FakeClock()
        evidence = recover_run8_accounting(
            client=client,
            ledger=ledger,
            sleep=clock.sleep,
            time_fn=clock.time,
        )
        assert evidence["create_order_calls"] == 0
        assert evidence["exchange_write_call_count"] == 0
        assert evidence["pnl_provenance"] == PNL_PROVENANCE
        stored = ledger.get_intent("p1pg_entry_run8") or {}
        assert stored.get("pnl_provenance") == PNL_PROVENANCE
        assert stored.get("realized_demo_pnl") == "-0.21"
        again = recover_run8_accounting(client=client, ledger=ledger, sleep=clock.sleep, time_fn=clock.time)
        assert again["idempotent"] is True
        assert again["create_order_calls"] == 0
    finally:
        pool.close()
