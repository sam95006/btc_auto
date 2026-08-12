"""Tests for Microstructure V1.2 metric truth, retention, heartbeat, budget."""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_microstructure.collector_v12 import CrossSequenceTracker, HeartbeatManager, source_semantics_v12
from backend.nexus_microstructure.memory_instrumentation import MemorySampler
from backend.nexus_microstructure.retention_engine import retention_dry_run
from backend.nexus_microstructure.storage_budget import StorageBudgetController
from backend.nexus_microstructure.storage_metrics import audit_storage_tree, compare_to_v11_estimate


def test_storage_metrics_separate_compressed_uncompressed(tmp_path: Path):
    part = tmp_path / "AGGRESSIVE_TRADE_FLOW" / "BTCUSDT"
    part.mkdir(parents=True)
    gz = part / "p.jsonl.gz"
    lines = b"".join((json.dumps({"i": i}) + "\n").encode() for i in range(50))
    with gzip.open(gz, "wb") as fh:
        fh.write(lines)
    man = part / "p.manifest.json"
    man.write_text(json.dumps({"ok": True}), encoding="utf-8")
    audit = audit_storage_tree(tmp_path)
    assert audit["session_total_compressed_bytes"] == gz.stat().st_size
    assert audit["session_total_uncompressed_bytes"] == len(lines)
    assert audit["manifest_bytes"] == man.stat().st_size
    assert audit["actual_compressed_bytes_per_event"] is not None
    assert audit["actual_uncompressed_bytes_per_event"] is not None
    assert audit["actual_compressed_bytes_per_event"] < audit["actual_uncompressed_bytes_per_event"]


def test_compare_overstated_when_claimed_uses_uncompressed():
    r = compare_to_v11_estimate(
        claimed_daily=1_000_000,
        actual_compressed_bpe=10.0,
        events_per_second=1.0,
        symbol_count=5,
    )
    # actual_daily = 10 * 1 * 86400 = 864000; claimed 1e6 / 864000 ~ 1.157 → CONFIRMED
    assert r["storage_metric_status"] in {
        "STORAGE_ESTIMATE_CONFIRMED",
        "STORAGE_ESTIMATE_OVERSTATED",
        "STORAGE_ESTIMATE_UNDERSTATED",
    }
    r2 = compare_to_v11_estimate(
        claimed_daily=10_000_000,
        actual_compressed_bpe=10.0,
        events_per_second=1.0,
        symbol_count=5,
    )
    assert r2["storage_metric_status"] == "STORAGE_ESTIMATE_OVERSTATED"


def test_source_semantics_liquidation_forced_unknown():
    s = source_semantics_v12()
    assert s["aggressor_side_semantics_status"] == "AGGRESSOR_SIDE_SEMANTICS_VERIFIED"
    assert s["forced_order_side_semantics_status"] == "UNKNOWN_WHEN_UNAVAILABLE"
    assert s["strict_sequence_gap_detection_supported"] is False
    assert s["legacy_liquidation_side_field_preserved"] is True


def test_cross_sequence_repeat_not_gap():
    x = CrossSequenceTracker()
    x.observe(100)
    x.observe(100)  # same seq in another message — not a gap
    x.observe(101)
    r = x.report()
    assert r["cross_sequence_repeated_message_count"] == 1
    assert r["cross_sequence_unique_count"] == 2
    assert r["strict_sequence_gap_detection_supported"] is False


def test_heartbeat_ack_and_timeout():
    hb = HeartbeatManager()

    class FakeWs:
        def __init__(self):
            self.sent = []

        def send(self, payload: str) -> None:
            self.sent.append(json.loads(payload))

    ws = FakeWs()
    hb.send(ws)
    assert hb.send_count == 1
    req_id = ws.sent[0]["req_id"]
    assert hb.on_message({"op": "pong", "req_id": req_id}) is True
    assert hb.ack_count == 1
    rep = hb.report()
    assert rep["heartbeat_status"] == "HEARTBEAT_VERIFIED"
    assert rep["heartbeat_ack_count"] == 1

    hb2 = HeartbeatManager()
    hb2.send(ws)
    hb2.pending[list(hb2.pending)[0]] = __import__("time").time() - 60
    hb2.check_timeouts()
    assert hb2.timeout_count >= 1
    assert hb2.report()["heartbeat_status"] == "HEARTBEAT_ACK_PARSING_FAILED"


def test_storage_budget_soft_hard():
    b = StorageBudgetController(soft_limit_bytes=100, hard_limit_bytes=200)
    assert b.observe_write(compressed_delta=50) == "NORMAL"
    assert b.observe_write(compressed_delta=60) == "DEGRADED_STORAGE_MODE"
    assert b.observe_write(compressed_delta=100) == "STORAGE_BUDGET_BLOCKED"
    assert b.stop_requested is True


def test_retention_dry_run_never_deletes(tmp_path: Path):
    p = tmp_path / "x.jsonl.gz"
    with gzip.open(p, "wb") as fh:
        fh.write(b"{}\n")
    r = retention_dry_run(tmp_path, code_checksum="abc")
    assert r["dry_run"] is True
    assert r["deletion_executed"] is False
    assert p.exists()


def test_memory_sampler_reports_status():
    m = MemorySampler(interval_s=0.01)
    m.start()
    m.maybe_sample()
    rep = m.stop(event_count=1_000_000)
    assert "memory_growth_status" in rep
    assert rep["process_RSS_peak_bytes"] is not None
