"""closed_at must be UTC datetime for TIMESTAMPTZ, never raw Bybit epoch milliseconds."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from backend.nexus_demo_execution.p1_exchange_accounting import (
    ClosedAtError,
    bybit_epoch_ms_to_utc_datetime,
    coerce_closed_at_for_timestamptz,
)
from tests.test_bybit_demo_p1_run8_accounting_recovery import FakeLedger


def test_bybit_epoch_ms_normalizes_to_aware_utc_datetime():
    converted = bybit_epoch_ms_to_utc_datetime("1710000060000")
    assert isinstance(converted, datetime)
    assert converted.tzinfo is not None
    assert converted.utcoffset() == timezone.utc.utcoffset(converted)
    assert converted.year == 2024
    assert converted == datetime(2024, 3, 9, 16, 1, tzinfo=timezone.utc)


def test_raw_13_digit_epoch_string_is_rejected_before_sql():
    ledger = FakeLedger()
    ledger.intents["x"] = {"order_intent_id": "x"}
    with pytest.raises(ClosedAtError, match="closed_at_epoch_ms_rejected"):
        ledger.record_accounting("x", closed_at="1710000060000")
    assert ledger.accounting_writes == 0
    with pytest.raises(ClosedAtError, match="closed_at_epoch_ms_rejected"):
        coerce_closed_at_for_timestamptz("1710000060000")


def test_aware_datetime_is_accepted():
    value = datetime(2024, 3, 9, 16, 1, tzinfo=timezone.utc)
    assert coerce_closed_at_for_timestamptz(value) == value
    ledger = FakeLedger()
    ledger.intents["x"] = {"order_intent_id": "x"}
    ledger.record_accounting("x", closed_at=value)
    assert ledger.intents["x"]["closed_at"] == value
    assert ledger.accounting_writes == 1


def test_iso8601_utc_is_normalized_and_accepted():
    converted = coerce_closed_at_for_timestamptz("2024-03-09T16:01:00Z")
    assert converted == datetime(2024, 3, 9, 16, 1, tzinfo=timezone.utc)
    converted = coerce_closed_at_for_timestamptz("2024-03-09T16:01:00+00:00")
    assert converted == datetime(2024, 3, 9, 16, 1, tzinfo=timezone.utc)


def test_overflow_timestamp_is_rejected():
    with pytest.raises(ClosedAtError, match="closed_at_overflow"):
        bybit_epoch_ms_to_utc_datetime("9999999999999999999")
    with pytest.raises(ClosedAtError):
        coerce_closed_at_for_timestamptz("not-a-timestamp")


@pytest.mark.skipif(
    not (
        (os.getenv("NEXUS_P1_LEDGER_ITEST_URL") or os.getenv("NEXUS_P1_LEDGER_ITEST_URL") or "").strip()
    ),
    reason="PostgreSQL TIMESTAMPTZ bind requires NEXUS_P1_LEDGER_ITEST_URL",
)
def test_normalized_closed_at_binds_to_postgres_timestamptz(monkeypatch):
    url = (os.getenv("NEXUS_P1_LEDGER_ITEST_URL") or os.getenv("NEXUS_P1_LEDGER_ITEST_URL") or "").strip()
    monkeypatch.setenv("NEXUS_ENV", "TEST")
    monkeypatch.setenv("NEXUS_POSTGRES_URL", url)
    from backend.nexus_persistence_pg.pool import PostgresPool

    converted = bybit_epoch_ms_to_utc_datetime("1710000060000")
    pool = PostgresPool(url)
    pool.open()

    class _Rollback(Exception):
        pass

    try:
        try:
            with pool.connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("SELECT %s::timestamptz", (converted,))
                        row = cur.fetchone()
                        assert row is not None
                        bound = row[0]
                        assert bound.year == 2024
                    raise _Rollback()
        except _Rollback:
            pass
    finally:
        pool.close()
