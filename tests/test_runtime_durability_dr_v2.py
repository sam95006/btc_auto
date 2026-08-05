"""Tests for V11 Runtime Durability + DR V2."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_recovery.dr_v2.matrix import run_injection_matrix
from backend.nexus_recovery.dr_v2.recovery import DisasterRecoveryV2
from backend.nexus_runtime.durability_v2.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    CORRUPTION_DETECTED,
    FULL_LEDGER_EVENTS,
    FULL_RECOVERY_DRILLS,
    FULL_SNAPSHOTS,
    SNAPSHOT_OK,
)
from backend.nexus_runtime.durability_v2.engine import RuntimeDurabilityV2
from backend.nexus_runtime.durability_v2.faults import (
    corrupt_lkg_pointer,
    inject_hash_chain_corruption,
    remove_latest_snapshot,
)
from backend.nexus_runtime.durability_v2.ledger import DiskLimitExceeded, DurableEventLedgerV2


def test_append_idempotent_and_monotonic(tmp_path: Path):
    led = DurableEventLedgerV2(tmp_path / "l.sqlite3")
    a = led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="t",
        payload={"n": 1},
        idempotency_key="k1",
    )
    b = led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="t",
        payload={"n": 1},
        idempotency_key="k1",
    )
    c = led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="Y",
        source="t",
        payload={"n": 2},
        idempotency_key="k2",
    )
    assert a.duplicate is False
    assert b.duplicate is True
    assert a.sequence_number == 1
    assert c.sequence_number == 2
    assert led.verify_hash_chain()["ledger_hash_chain_status"] == "PASS"
    led.close()


def test_hash_corruption_detected(tmp_path: Path):
    led = DurableEventLedgerV2(tmp_path / "l.sqlite3")
    led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="t",
        payload={"n": 1},
        idempotency_key="k1",
    )
    inject_hash_chain_corruption(led, seq=1)
    assert led.verify_hash_chain()["ledger_hash_chain_status"] == CORRUPTION_DETECTED
    led.close()


def test_ambiguous_latest_missing_blocks(tmp_path: Path):
    dur = RuntimeDurabilityV2(tmp_path / "d")
    led = dur.open_ledger()
    led.append(
        aggregate_id="a",
        aggregate_type="CANDIDATE",
        event_type="X",
        source="t",
        payload={"ok": True},
        idempotency_key="a1",
    )
    snap = dur.create_snapshot(led)
    assert snap.status == SNAPSHOT_OK
    led.close()
    remove_latest_snapshot(dur)
    restored = dur.restore_last_known_good()
    assert restored.status == BLOCKED_AMBIGUOUS_STATE


def test_lkg_corruption_detected(tmp_path: Path):
    dur = RuntimeDurabilityV2(tmp_path / "d")
    led = dur.open_ledger()
    led.append(
        aggregate_id="a",
        aggregate_type="CANDIDATE",
        event_type="X",
        source="t",
        payload={"ok": True},
        idempotency_key="a1",
    )
    assert dur.create_snapshot(led).status == SNAPSHOT_OK
    led.close()
    corrupt_lkg_pointer(dur)
    restored = dur.restore_last_known_good()
    assert restored.status == CORRUPTION_DETECTED


def test_live_ahead_of_lkg_blocks_without_evidence_loss_claim(tmp_path: Path):
    dur = RuntimeDurabilityV2(tmp_path / "d")
    led = dur.open_ledger()
    for i in range(3):
        led.append(
            aggregate_id=f"a{i}",
            aggregate_type="DECISION",
            event_type="X",
            source="t",
            payload={"i": i},
            idempotency_key=f"k{i}",
        )
    assert dur.create_snapshot(led).status == SNAPSHOT_OK
    # Append more after snapshot — restore would discard evidence
    led.append(
        aggregate_id="extra",
        aggregate_type="DECISION",
        event_type="X",
        source="t",
        payload={"extra": True},
        idempotency_key="extra",
    )
    led.close()
    restored = dur.restore_last_known_good()
    assert restored.status == BLOCKED_AMBIGUOUS_STATE
    assert restored.detail.get("evidence_loss_claimed_without_proof") is False


def test_clock_rollback_blocked(tmp_path: Path):
    clocks = [1_700_000_100.0]

    def clock() -> float:
        return clocks[0]

    led = DurableEventLedgerV2(tmp_path / "l.sqlite3", clock=clock)
    assert (
        led.append(
            aggregate_id="c",
            aggregate_type="DECISION",
            event_type="A",
            source="t",
            payload={},
            idempotency_key="1",
        ).status
        == "APPENDED"
    )
    clocks[0] -= 50
    r = led.append(
        aggregate_id="c",
        aggregate_type="DECISION",
        event_type="B",
        source="t",
        payload={},
        idempotency_key="2",
    )
    assert r.status == "BLOCKED_CLOCK_ROLLBACK"
    led.close()


def test_disk_hard_limit(tmp_path: Path):
    led = DurableEventLedgerV2(tmp_path / "l.sqlite3", hard_disk_limit_bytes=1)
    try:
        led.append(
            aggregate_id="d",
            aggregate_type="DECISION",
            event_type="X",
            source="t",
            payload={"x": 1},
            idempotency_key="d1",
        )
        raised = False
    except DiskLimitExceeded:
        raised = True
    led.close()
    assert raised


def test_injection_matrix_all_pass(tmp_path: Path):
    result = run_injection_matrix(base_root=tmp_path / "matrix")
    assert result["matrix_status"] == "PASS", result
    assert result["exchange_write_attempt_count"] == 0
    assert result["total"] == 16


def test_dr_recover_after_hash_corruption(tmp_path: Path):
    dr = DisasterRecoveryV2(tmp_path / "dr")
    led = dr.durability.open_ledger()
    for i in range(5):
        led.append(
            aggregate_id=f"a{i}",
            aggregate_type="DECISION",
            event_type="X",
            source="t",
            payload={"i": i},
            idempotency_key=f"k{i}",
        )
    assert dr.durability.create_snapshot(led).status == SNAPSHOT_OK
    inject_hash_chain_corruption(led, seq=2)
    led.close()
    outcome = dr.recover()
    assert outcome["status"] in {
        CORRUPTION_DETECTED,
        "RECOVERED_LAST_KNOWN_GOOD",
        "RECOVERED_EXACT",
        BLOCKED_AMBIGUOUS_STATE,
    }
    assert outcome.get("silent_recovery_guess") is False
    assert outcome.get("exchange_write_attempt_count") == 0


def test_full_scale_capability_documented():
    assert FULL_LEDGER_EVENTS == 1_000_000
    assert FULL_SNAPSHOTS == 1_000
    assert FULL_RECOVERY_DRILLS == 100


def test_harness_resolve_scale_env(monkeypatch):
    from tools.research.run_runtime_durability_dr_v2 import resolve_scale

    monkeypatch.setenv("NEXUS_DURABILITY_V2_MODE", "smoke")
    monkeypatch.delenv("NEXUS_DURABILITY_V2_EVENTS", raising=False)
    s = resolve_scale()
    assert s["events"] == 2_000
    assert s["full_capability_events"] == 1_000_000

    monkeypatch.setenv("NEXUS_DURABILITY_V2_MODE", "full")
    s2 = resolve_scale()
    assert s2["events"] == 1_000_000
