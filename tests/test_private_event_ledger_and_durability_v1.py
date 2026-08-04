"""Tests for Private Event Ledger + Runtime Durability V1."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_autonomy.private_event_ledger_v1 import PrivateEventLedger
from backend.nexus_autonomy.runtime_durability_v1 import RuntimeDurabilityV1, run_failure_injection_matrix


def test_ledger_hash_chain_and_idempotency(tmp_path: Path):
    led = PrivateEventLedger(tmp_path / "l.sqlite3")
    a = led.append(
        aggregate_id="a1",
        aggregate_type="ORDER_INTENT",
        event_type="CREATED",
        source="test",
        payload={"x": 1},
        idempotency_key="k1",
    )
    b = led.append(
        aggregate_id="a1",
        aggregate_type="ORDER_INTENT",
        event_type="CREATED",
        source="test",
        payload={"x": 1},
        idempotency_key="k1",
    )
    assert a.duplicate is False
    assert b.duplicate is True
    assert led.verify_hash_chain()["ledger_hash_chain_status"] == "PASS"
    assert led.integrity_check() == "ok"
    assert len(led.replay()) == 1
    led.close()


def test_durability_matrix_pass(tmp_path: Path):
    result = run_failure_injection_matrix(tmp_path / "dur")
    assert result["durability_status"] == "NEXUS_RUNTIME_DURABILITY_V1_PASS"
    assert result["preserved_facts"]["old_trading_db_recovered"] is False
    assert result["exchange_write_attempt_count"] == 0


def test_snapshot_restore_exact(tmp_path: Path):
    dur = RuntimeDurabilityV1(tmp_path / "r")
    led = dur.open_ledger()
    led.append(
        aggregate_id="c",
        aggregate_type="CANDIDATE",
        event_type="X",
        source="t",
        payload={"ok": True},
        idempotency_key="c1",
    )
    snap = dur.create_snapshot(led)
    assert snap["status"] == "SNAPSHOT_OK"
    led.close()
    restored = dur.restore_last_known_good()
    assert restored.status in {"RECOVERED_EXACT", "RECOVERED_LAST_KNOWN_GOOD"}
