"""Focused tests — binder + alert truth + scanners."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.nexus_runtime_snapshot_v18_1.alerts import (
    AlertTruthError,
    build_runtime_alerts,
    fixture_as_live_count,
)
from backend.nexus_runtime_snapshot_v18_1.binder import (
    build_bound_home,
    snapshot_to_live_funnel_screen,
    snapshot_to_mobile_surface,
)
from backend.nexus_runtime_snapshot_v18_1.hard_bans import run_phase_b_scans
from backend.nexus_runtime_snapshot_v18_1.loader import load_runtime_snapshot


def _write_stopped(tmp: Path) -> Path:
    now = datetime.now(timezone.utc)
    hb_at = now - timedelta(seconds=30)
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
        "source_read_success_count": 10,
        "source_read_failure_count": 0,
        "live_records_ingested": 3,
        "records_quarantined": 0,
        "AI_requests": 2,
        "AI_success": 2,
        "AI_timeout": 0,
        "AI_invalid_json": 0,
        "deterministic_fallback_count": 0,
        "provider_capacity_blocked_count": 0,
    }
    (tmp / "heartbeat.json").write_text(
        json.dumps(
            {
                "runtime_state": "STOPPED",
                "heartbeat_at": hb_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "started_at": (hb_at - timedelta(seconds=15)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "last_successful_cycle_at": hb_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data_class": "LIVE_PARTIAL_DEGRADED",
                "metrics": metrics,
            }
        ),
        encoding="utf-8",
    )
    (tmp / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (tmp / "public_safe_projection.jsonl").write_text(
        json.dumps(
            {
                "symbol": "BTCUSDT",
                "decision": "BLOCK",
                "data_class": "LIVE_PARTIAL_DEGRADED",
                "actual_ordered": False,
                "actual_filled": False,
                "shadow_decision_id": "v18_1-test",
                "as_of": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp


def test_binder_screen_stopped_honesty(tmp_path: Path, monkeypatch):
    root = _write_stopped(tmp_path)
    snap = load_runtime_snapshot(root)
    screen = snapshot_to_live_funnel_screen(snap)
    assert screen["is_live_view"] is False
    assert screen["chrome_label"] == "RUNTIME_STOPPED"
    assert screen["trade_buttons"] is False
    assert screen["actual_ordered"] is False
    assert screen["actual_filled"] is False
    assert screen["member_execution_control_count"] == 0
    mobile = snapshot_to_mobile_surface(snap)
    assert mobile["trade_buttons"] is False
    assert mobile["runtime_status"] == "STOPPED"


def test_runtime_stopped_alert_not_fixture_live(tmp_path: Path):
    root = _write_stopped(tmp_path)
    snap = load_runtime_snapshot(root)
    alerts = build_runtime_alerts(snap)
    assert any(a["kind"] == "RUNTIME_STOPPED" for a in alerts)
    assert fixture_as_live_count(alerts) == 0
    for a in alerts:
        assert a["public_safe"] is True
        assert a["actionable_trade"] is False
        blob = f"{a['title']} {a['body']} {a['reason']}".upper()
        for banned in ("BUY NOW", "SELL NOW", "GUARANTEED", "COPY TRADE"):
            assert banned not in blob


def test_fixture_as_live_alert_refused():
    bad = {
        "runtime_state": "RUNNING",
        "data_freshness": "FIXTURE",
        "data_class": "LIVE_READ_ONLY",
        "is_live_view": True,
        "binding_mode": "fixture",
        "shadow_status": {},
        "universe_funnel": {},
        "source_health": {},
        "AI_gateway_status": {},
        "degraded_reasons": [],
    }
    try:
        build_runtime_alerts(bad)
        raised = False
    except AlertTruthError:
        raised = True
    assert raised


def test_bound_home_against_real_runtime_root():
    # Uses D:\NEXUS_RUNTIME\live_shadow_runtime (Phase A STOPPED evidence).
    body = build_bound_home()
    assert body["actual_ordered"] is False
    assert body["actual_filled"] is False
    assert body["fixture_as_live_count"] == 0
    snap = body["runtime_snapshot"]
    assert snap["runtime_state"] in {"STOPPED", "UNAVAILABLE", "RUNNING", "DEGRADED", "PAUSED"}
    if snap["runtime_state"] == "STOPPED":
        assert snap["is_live_view"] is False
        assert snap["display_label"] in {"RUNTIME_STOPPED", "STALE", "UNAVAILABLE", "STOPPED"}


def test_phase_b_scans_pass():
    root = Path(__file__).resolve().parents[2]
    report = run_phase_b_scans(root)
    assert report["private_import_count"] == 0
    assert report["member_execution_control_count"] == 0
    assert report["embedded_secret_count"] == 0
    assert report["private_field_leak_count"] == 0
    assert report["fixture_as_live_count"] == 0
    assert report["actual_ordered"] is False
    assert report["actual_filled"] is False
    assert report["stale_labeling"]["ok"] is True
    assert report["ok"] is True
