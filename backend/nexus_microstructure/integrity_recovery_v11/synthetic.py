"""24h synthetic logical capture + fixture builders for integrity recovery tests."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import (
    DurablePartitionWriterV11,
    manifest_path_for,
)


def _event(symbol: str, family: str, ts_ms: int, seq: int) -> dict[str, Any]:
    return {
        "schema": "microstructure_event_v11_fixture",
        "family": family,
        "symbol": symbol,
        "exchange_timestamp": ts_ms,
        "receive_wall_timestamp": ts_ms + 1,
        "seq": seq,
        "price": "1.0",
        "size": "0.01",
    }


def write_sanitized_open_tail_fixture(root: Path) -> dict[str, Any]:
    """Reproduce EXPECTED_OPEN_TAIL: kill mid-write leaves truncated gzip + .open marker."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    w = DurablePartitionWriterV11(
        root,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="ms12_FIX_OPEN_1",
        flush_interval_s=0.01,
        buffer_max_events=1,
    )
    base = 1_720_000_000_000
    for i in range(20):
        w.accept(_event("BTCUSDT", "AGGRESSIVE_TRADE_FLOW", base + i * 1000, i))
    abandoned = w.abandon_open_without_finalize()
    assert abandoned is not None
    return {"class": "EXPECTED_OPEN_TAIL", "path": str(abandoned), "open_marker": str(abandoned) + ".open"}


def write_sanitized_manifest_bug_fixture(root: Path) -> dict[str, Any]:
    """Reproduce MANIFEST_BUG: intact gzip, missing manifest (finalize race)."""
    root = Path(root)
    w = DurablePartitionWriterV11(
        root,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="ETHUSDT",
        capture_session_id="ms12_FIX_MAN_1",
        flush_interval_s=0.01,
        buffer_max_events=1,
    )
    base = 1_720_000_000_000
    for i in range(10):
        w.accept(_event("ETHUSDT", "AGGRESSIVE_TRADE_FLOW", base + i * 1000, i))
    report = w.close()
    path = Path(report["partitions"][0]["path"])
    man = manifest_path_for(path)
    if man.exists():
        man.unlink()
    return {"class": "MANIFEST_BUG", "path": str(path), "manifest_removed": True}


def write_sanitized_linkage_semantics_fixture(root: Path) -> dict[str, Any]:
    """Two symbols without manifests — V1 would cross-link; V11 must not."""
    root = Path(root)
    parts_dir = root / "partitions"
    for sym in ("AAAUSDT", "BBBUSDT"):
        d = parts_dir / "AGGRESSIVE_TRADE_FLOW" / sym
        d.mkdir(parents=True, exist_ok=True)
        pid = f"ms12_FIX_LINK_1_AGGRESSIVE_TRADE_FLOW_{sym}_20260804_13_0"
        gz = d / f"{pid}.jsonl.gz"
        with gzip.open(gz, "wb") as fh:
            fh.write(b'{"symbol":"%s","exchange_timestamp":1}\n' % sym.encode())
        # Intentionally no manifest → missing identity for V1
    return {"class": "LINKAGE_SEMANTICS_BUG", "partitions_root": str(parts_dir)}


def write_sanitized_checksum_mismatch_fixture(root: Path) -> dict[str, Any]:
    """ACTUAL_DATA_CORRUPTION: intact gzip but wrong rolling_checksum in manifest."""
    root = Path(root)
    w = DurablePartitionWriterV11(
        root,
        exchange="BYBIT",
        family="LIQUIDATION_EVENTS",
        symbol="SOLUSDT",
        capture_session_id="ms12_FIX_CSUM_1",
        flush_interval_s=0.01,
        buffer_max_events=1,
    )
    base = 1_720_000_000_000
    for i in range(5):
        w.accept(_event("SOLUSDT", "LIQUIDATION_EVENTS", base + i * 1000, i))
    report = w.close()
    man_path = manifest_path_for(Path(report["partitions"][0]["path"]))
    man = json.loads(man_path.read_text(encoding="utf-8"))
    man["rolling_checksum"] = "0" * 64
    man_path.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    return {"class": "ACTUAL_DATA_CORRUPTION", "manifest_path": str(man_path)}


def run_24h_synthetic_logical_capture(root: Path, *, hours: int = 24, events_per_hour: int = 3) -> dict[str, Any]:
    """Logical 24h capture across UTC hours (synthetic timestamps), graceful stop."""
    root = Path(root)
    session = "ms12_SYN24_1"
    writers = {
        "BTCUSDT": DurablePartitionWriterV11(
            root,
            exchange="BYBIT",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="BTCUSDT",
            capture_session_id=session,
            flush_interval_s=0.01,
            buffer_max_events=1,
        ),
        "ETHUSDT": DurablePartitionWriterV11(
            root,
            exchange="BYBIT",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol="ETHUSDT",
            capture_session_id=session,
            flush_interval_s=0.01,
            buffer_max_events=1,
        ),
    }
    # 2026-08-04 00:00 UTC
    base = 1_754_265_600_000
    seq = 0
    for h in range(hours):
        for sym, w in writers.items():
            for j in range(events_per_hour):
                ts = base + h * 3_600_000 + j * 1_000
                w.accept(_event(sym, "AGGRESSIVE_TRADE_FLOW", ts, seq))
                seq += 1
    reports = [w.close() for w in writers.values()]
    return {
        "hours": hours,
        "symbols": list(writers.keys()),
        "partition_count": sum(r["partition_count"] for r in reports),
        "checksum_replay_verified": all(r["checksum_replay_verified"] for r in reports),
        "graceful_stop": all(r["graceful_stop"] for r in reports),
        "reports": reports,
    }


def write_all_sanitized_fixtures(fixtures_root: Path) -> dict[str, Any]:
    fixtures_root = Path(fixtures_root)
    fixtures_root.mkdir(parents=True, exist_ok=True)
    out = {
        "EXPECTED_OPEN_TAIL": write_sanitized_open_tail_fixture(fixtures_root / "open_tail"),
        "MANIFEST_BUG": write_sanitized_manifest_bug_fixture(fixtures_root / "manifest_bug"),
        "LINKAGE_SEMANTICS_BUG": write_sanitized_linkage_semantics_fixture(fixtures_root / "linkage"),
        "ACTUAL_DATA_CORRUPTION": write_sanitized_checksum_mismatch_fixture(fixtures_root / "checksum_mismatch"),
        "SYNTHETIC_24H": run_24h_synthetic_logical_capture(fixtures_root / "synthetic_24h", hours=24),
    }
    (fixtures_root / "fixture_index.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out
