"""Focused tests — Runtime Snapshot loader + stale honesty."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.nexus_runtime_snapshot_v18_1.constants import REQUIRED_SNAPSHOT_FIELDS
from backend.nexus_runtime_snapshot_v18_1.loader import (
    compute_freshness_and_label,
    load_runtime_snapshot,
    map_public_runtime_state,
)


def _write_runtime(tmp: Path, *, state: str = "STOPPED", age_sec: float = 10.0) -> Path:
    now = datetime.now(timezone.utc)
    hb_at = now - timedelta(seconds=age_sec)
    started = hb_at - timedelta(seconds=20)
    metrics = {
        "total_contracts_seen": 40,
        "eligible_contracts_latest": 0,
        "observe_only_contracts_latest": 0,
        "blocked_contracts_latest": 40,
        "candidates_generated": 5,
        "LONG_count": 0,
        "SHORT_count": 0,
        "WAIT_count": 0,
        "ABSTAIN_count": 0,
        "BLOCK_count": 5,
        "shadow_opened_count": 0,
        "shadow_closed_count": 0,
        "actual_ordered_count": 0,
        "actual_filled_count": 0,
        "source_read_success_count": 52,
        "source_read_failure_count": 0,
        "live_records_ingested": 14,
        "records_quarantined": 0,
        "AI_requests": 5,
        "AI_success": 5,
        "AI_timeout": 0,
        "AI_invalid_json": 0,
        "deterministic_fallback_count": 0,
        "provider_capacity_blocked_count": 0,
    }
    heartbeat = {
        "schema": "test_heartbeat",
        "runtime_state": state,
        "heartbeat_at": hb_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_successful_cycle_at": hb_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_class": "LIVE_PARTIAL_DEGRADED",
        "metrics": metrics,
    }
    (tmp / "heartbeat.json").write_text(json.dumps(heartbeat), encoding="utf-8")
    (tmp / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    proj = {
        "schema": "v18_1_live_shadow_runtime_conductor_v1",
        "shadow_decision_id": "v18_1-test-BTCUSDT",
        "symbol": "BTCUSDT",
        "decision": "BLOCK",
        "data_class": "LIVE_PARTIAL_DEGRADED",
        "runtime_state": state,
        "actual_ordered": False,
        "actual_filled": False,
        "as_of": 1785989662540,
        "emitted_at": hb_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (tmp / "public_safe_projection.jsonl").write_text(
        json.dumps(proj) + "\n", encoding="utf-8"
    )
    return tmp


def test_map_public_runtime_state():
    assert map_public_runtime_state("RUNNING") == "RUNNING"
    assert map_public_runtime_state("STOPPING") == "STOPPED"
    assert map_public_runtime_state("FAILED_SAFE") == "STOPPED"
    assert map_public_runtime_state("BACKOFF") == "DEGRADED"
    assert map_public_runtime_state(None) == "UNAVAILABLE"


def test_stopped_must_not_be_live(tmp_path: Path):
    root = _write_runtime(tmp_path, state="STOPPED")
    snap = load_runtime_snapshot(root)
    assert snap["runtime_state"] == "STOPPED"
    assert snap["is_live_view"] is False
    assert snap["display_label"] in {"RUNTIME_STOPPED", "STOPPED", "STALE", "UNAVAILABLE"}
    assert snap["data_freshness"] == "RUNTIME_STOPPED"
    assert not str(snap["data_class"]).startswith("LIVE")
    assert snap["actual_ordered"] is False
    assert snap["actual_filled"] is False
    for field in REQUIRED_SNAPSHOT_FIELDS:
        assert field in snap


def test_missing_runtime_is_unavailable(tmp_path: Path):
    snap = load_runtime_snapshot(tmp_path / "missing")
    assert snap["runtime_state"] == "UNAVAILABLE"
    assert snap["is_live_view"] is False
    assert snap["data_class"] == "UNAVAILABLE"
    assert snap["ok"] is False


def test_stale_heartbeat_while_running(tmp_path: Path):
    root = _write_runtime(tmp_path, state="RUNNING", age_sec=600)
    snap = load_runtime_snapshot(root)
    assert snap["is_live_view"] is False
    assert snap["data_freshness"] == "STALE"
    assert snap["display_label"] == "STALE"


def test_running_fresh_is_live_view(tmp_path: Path):
    root = _write_runtime(tmp_path, state="RUNNING", age_sec=5)
    snap = load_runtime_snapshot(root)
    assert snap["runtime_state"] == "RUNNING"
    assert snap["is_live_view"] is True
    assert snap["actual_ordered"] is False
    assert snap["actual_filled"] is False


def test_compute_freshness_helpers():
    now = datetime.now(timezone.utc)
    f, label, live = compute_freshness_and_label(
        runtime_state="STOPPED", heartbeat_at=now, now=now
    )
    assert f == "RUNTIME_STOPPED"
    assert live is False
    assert label == "RUNTIME_STOPPED"


def test_private_field_in_projection_fails(tmp_path: Path):
    root = _write_runtime(tmp_path, state="RUNNING", age_sec=5)
    bad = {
        "schema": "v18_1_live_shadow_runtime_conductor_v1",
        "symbol": "BTCUSDT",
        "decision": "WAIT",
        "api_secret": "should-not-leak",
        "actual_ordered": False,
        "actual_filled": False,
    }
    (root / "public_safe_projection.jsonl").write_text(
        json.dumps(bad) + "\n", encoding="utf-8"
    )
    with pytest.raises(Exception):
        load_runtime_snapshot(root)
