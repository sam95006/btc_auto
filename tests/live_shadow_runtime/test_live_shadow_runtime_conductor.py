"""Focused tests for V18.1 Live Shadow Runtime Conductor."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.nexus_live_shadow_runtime import (
    HARD_BANS,
    RUNTIME_STATES,
    LiveShadowRuntimeConductor,
    PublicSafeProjectionWriter,
    RuntimeMetrics,
    RuntimeStateMachine,
    filter_public_safe,
)
from backend.nexus_live_shadow_runtime.conductor import ConductorConfig
from backend.nexus_live_shadow_runtime.projection import ProjectionError
from backend.nexus_live_shadow_runtime.state_machine import InvalidRuntimeTransitionError


os.environ["NEXUS_ALLOW_NON_RUNTIME_ROOT"] = "1"


def test_import_smoke():
    import backend.nexus_live_shadow_runtime as pkg

    assert pkg.SCHEMA
    assert "STARTING" in pkg.RUNTIME_STATES
    assert "FAILED_SAFE" in pkg.RUNTIME_STATES
    assert len(RUNTIME_STATES) == 9


def test_state_machine_happy_path():
    sm = RuntimeStateMachine()
    assert sm.state == "STARTING"
    sm.transition("PREFLIGHT", reason="boot")
    sm.transition("RUNNING", reason="ok")
    sm.transition("STOPPING", reason="done")
    sm.transition("STOPPED", reason="exit")
    assert sm.is_terminal
    assert sm.state == "STOPPED"


def test_state_machine_fail_closed_illegal():
    sm = RuntimeStateMachine()
    with pytest.raises(InvalidRuntimeTransitionError):
        sm.transition("RUNNING", reason="skip_preflight")


def test_state_machine_degraded_backoff():
    sm = RuntimeStateMachine()
    sm.transition("PREFLIGHT", reason="boot")
    sm.transition("DEGRADED", reason="partial")
    sm.transition("BACKOFF", reason="retry")
    sm.transition("DEGRADED", reason="resume")
    sm.transition("FAILED_SAFE", reason="give_up")
    assert sm.failure_reason == "give_up"


def test_metrics_forbid_ordered_filled_busy_loop_bump():
    m = RuntimeMetrics()
    with pytest.raises(RuntimeError):
        m.bump("actual_ordered_count", 1)
    with pytest.raises(RuntimeError):
        m.bump("busy_loop_count", 1)
    m.record_decision("WAIT")
    m.record_decision("BLOCK")
    d = m.to_dict()
    assert d["WAIT_count"] == 1
    assert d["BLOCK_count"] == 1
    assert d["actual_ordered_count"] == 0
    assert d["actual_filled_count"] == 0
    assert d["busy_loop_count"] == 0
    m.assert_safety_invariants()


def test_projection_allow_list(tmp_path: Path):
    writer = PublicSafeProjectionWriter(tmp_path / "proj.jsonl")
    with pytest.raises(ProjectionError):
        filter_public_safe({"api_key": "x", "decision": "WAIT"})
    with pytest.raises(ProjectionError):
        writer.append({"schema": "t", "secret_token": "nope", "decision": "WAIT"})
    safe = writer.append(
        {
            "schema": "t",
            "shadow_decision_id": "y",
            "lifecycle_state": "OBSERVED",
            "decision": "ABSTAIN",
            "data_class": "BOUNDED_LIVE_SMOKE",
            "actual_ordered": True,  # forced false on write
        }
    )
    assert safe["actual_ordered"] is False
    assert safe["actual_filled"] is False
    assert safe["exchange_order_id"] is None
    lines = (tmp_path / "proj.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["actual_ordered"] is False


def test_lock_single_instance(tmp_path: Path):
    cfg = ConductorConfig(
        runtime_root=tmp_path / "rt",
        max_cycles=1,
        max_seconds=30,
        cycle_sleep_sec=0.0,
        live=True,
    )
    c1 = LiveShadowRuntimeConductor(cfg)
    c1.acquire_lock()
    c2 = LiveShadowRuntimeConductor(
        ConductorConfig(
            runtime_root=tmp_path / "rt",
            max_cycles=1,
            max_seconds=5,
            cycle_sleep_sec=0.0,
        )
    )
    with pytest.raises(Exception):
        c2.acquire_lock()
    c1.release_lock()


def test_hard_bans_declared():
    assert "no_exchange_write" in HARD_BANS
    assert "no_busy_loop" in HARD_BANS
    assert "no_force_long_short_on_insufficient_data" in HARD_BANS


def test_bounded_conductor_run_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Run with live adapters; network may fail — must fail-closed with real counters."""
    # Force adapter failures by monkeypatching fetch to raise.
    from backend.nexus_official_market_adapters.binance.adapter import BinanceUsdmPublicAdapter
    from backend.nexus_official_market_adapters.bybit.adapter import BybitPublicV5Adapter

    def _boom(*_a, **_k):
        raise RuntimeError("network_blocked_for_test")

    monkeypatch.setattr(BybitPublicV5Adapter, "fetch_instrument_catalog", _boom)
    monkeypatch.setattr(BybitPublicV5Adapter, "fetch_ticker", _boom)
    monkeypatch.setattr(BinanceUsdmPublicAdapter, "fetch_instrument_catalog", _boom)
    monkeypatch.setattr(BinanceUsdmPublicAdapter, "fetch_ticker", _boom)

    cfg = ConductorConfig(
        runtime_root=tmp_path / "smoke_fail",
        max_cycles=2,
        max_seconds=60,
        cycle_sleep_sec=0.0,
        live=True,
    )
    snap = LiveShadowRuntimeConductor(cfg).run()
    metrics = snap["metrics"]
    assert metrics["source_read_failure_count"] > 0
    assert metrics["actual_ordered_count"] == 0
    assert metrics["actual_filled_count"] == 0
    assert metrics["busy_loop_count"] == 0
    assert metrics["exchange_write_attempt_count"] == 0
    assert snap["data_class"] in {
        "FAILED_SAFE",
        "LIVE_PARTIAL_DEGRADED",
        "BOUNDED_LIVE_SMOKE",
        "LIVE_READ_ONLY",
    }
    # Decisions must not be LONG/SHORT when both adapters fail.
    last = snap.get("last_shadow_decision") or {}
    if last:
        assert last.get("decision") in {"WAIT", "ABSTAIN", "BLOCK", None} or last.get(
            "decision"
        ) not in {"LONG", "SHORT"}
    assert (tmp_path / "smoke_fail" / "smoke_exit.json").exists()
    assert (tmp_path / "smoke_fail" / "heartbeat.json").exists()
