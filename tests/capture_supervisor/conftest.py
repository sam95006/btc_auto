"""Shared fixtures for capture supervisor tests."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest


@pytest.fixture
def synth_campaign(tmp_path: Path) -> dict:
    runtime = tmp_path / "runtime"
    wt = tmp_path / "capture_wt"
    parts = wt / ".nexus_runtime" / "microstructure" / "v1_2"
    parts.mkdir(parents=True)
    runtime.mkdir(parents=True)

    campaign_id = "ms_accum_v13_integrity_14d"
    launch = {
        "schema": "coordinator_ms_accum_v13_integrity_14d_launch",
        "campaign_id": campaign_id,
        "live_capture_started": True,
        "capture_start_UTC": "2026-08-05T09:42:05Z",
        "capture_PID": 999999,  # dead by default unless overridden
        "capture_worker_PID": 999998,
        "symbol_count": 25,
        "worktree": str(wt),
        "event_study_readiness": "NOT_READY",
        "exchange_write_attempt_count": 0,
    }
    (runtime / f"{campaign_id}_launch.json").write_text(json.dumps(launch, indent=2), encoding="utf-8")
    health = {
        "schema": "ms_accum_v13_integrity_14d_health",
        "checked_at": "2026-08-05T11:00:00Z",
        "campaign_id": campaign_id,
        "live_capture_started": True,
        "capture_PID": 999999,
        "capture_worker_PID": 999998,
        "data_file_count": 2,
        "data_bytes": 100,
        "free_gib": 200,
        "integrity_status": "LIVE_WRITING",
        "event_study_readiness": "NOT_READY",
        "exchange_write_attempt_count": 0,
    }
    (runtime / f"{campaign_id}_health.json").write_text(json.dumps(health, indent=2), encoding="utf-8")

    # One sealed + one open-tail partition
    sym_dir = parts / "BYBIT" / "AGGRESSIVE_TRADE_FLOW" / "BTCUSDT"
    sym_dir.mkdir(parents=True)
    sealed = sym_dir / "ms12_ACCUM24_1_AGGRESSIVE_TRADE_FLOW_BTCUSDT_20260805_09_0.jsonl.gz"
    with gzip.open(sealed, "wb") as fh:
        fh.write(b'{"x":1}\n')
    man = {
        "partition_id": sealed.name.replace(".jsonl.gz", ""),
        "record_count": 1,
        "rolling_checksum": "abc",
        "original_sha256_file": None,
    }
    sealed.with_name(sealed.name.replace(".jsonl.gz", ".jsonl.manifest.json")).write_text(
        json.dumps(man, indent=2), encoding="utf-8"
    )
    open_p = sym_dir / "ms12_ACCUM24_1_AGGRESSIVE_TRADE_FLOW_BTCUSDT_20260805_11_0.jsonl.gz"
    with gzip.open(open_p, "wb") as fh:
        fh.write(b'{"x":2}\n')

    ck = {
        "accumulation_run_id": campaign_id,
        "session_id": "ms12_ACCUM24_1",
        "trade_count": 10,
        "liq_count": 1,
        "symbols": ["BTCUSDT"],
    }
    (parts / f"{campaign_id}.checkpoint.json").write_text(json.dumps(ck, indent=2), encoding="utf-8")

    return {
        "runtime": runtime,
        "worktree": wt,
        "partitions": parts,
        "campaign_id": campaign_id,
        "launch": launch,
        "health": health,
    }
