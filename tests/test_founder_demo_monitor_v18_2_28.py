"""V18.2.28 Founder demo monitor — trading intel / performance / learning."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_founder_demo_monitor.constants import SCHEMA_ID
from backend.nexus_founder_demo_monitor.loader import load_raw_monitor_feed
from backend.nexus_founder_demo_monitor.snapshot import build_founder_demo_monitor_snapshot


def test_schema_v18_2_28():
    assert SCHEMA_ID == "NEXUS_FOUNDER_DEMO_MONITOR_V18_2_28"


def test_v28_core_path_preferred(monkeypatch, tmp_path: Path):
    v28 = tmp_path / "v18_2_28_core.json"
    v27 = tmp_path / "v18_2_27_core.json"
    v28.write_text(
        json.dumps(
            {
                "schema": "v18_2_28_core_v1",
                "generated_at": "2026-08-11T09:00:00Z",
                "directive": "V18.2.28_TEST",
                "REAL_DEMO_ACCOUNT": {
                    "account_uid": "567649663",
                    "equity": "5100.0",
                    "wallet_balance": "5100.0",
                    "current_real_positions": [],
                },
                "PERFORMANCE": {
                    "win_rate_long": 0.5,
                    "win_rate_short": 0.0,
                    "win_rate_aggregate": 0.0,
                    "net_pnl": -0.34309373,
                    "profit_factor": None,
                },
            }
        ),
        encoding="utf-8",
    )
    v27.write_text(
        json.dumps(
            {
                "schema": "v18_2_27_core_v1",
                "generated_at": "2026-08-11T08:00:00Z",
                "REAL_DEMO_ACCOUNT": {
                    "account_uid": "567649663",
                    "equity": "5000.0",
                    "current_real_positions": [],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_EVIDENCE_COORDINATOR", str(tmp_path))
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED_ONLY", "1")

    blob, source, status, fixture_used = load_raw_monitor_feed()
    assert status == "FEED_READY"
    assert fixture_used is False
    assert source == str(v28)
    assert blob is not None
    assert blob.get("equity") == "5100.0"


def test_trading_intel_fields_and_provenance(monkeypatch, tmp_path: Path):
    feed = tmp_path / "founder_demo_monitor_live.json"
    feed.write_text(
        json.dumps(
            {
                "schema": "v18_2_28_founder_demo_monitor_live_v1",
                "source_timestamp": "2026-08-11T09:01:00Z",
                "provenance": "AGENT_B_V28",
                "account_uid": "567649663",
                "equity": 5022.61,
                "wallet_balance": 5027.43,
                "lane_label": "PNL_BEARING_RESEARCH",
                "position_state": "OPEN",
                "active_position": {
                    "symbol": "BTCUSDT",
                    "side": "LONG",
                    "entry": 64000,
                    "current": 64100,
                    "stop": 63500,
                    "target": 65000,
                    "initial_target": 65000,
                    "dynamic_profit_zone": {"lower": 64500, "upper": 65200},
                    "unrealized_pnl": 0.1,
                    "estimated_net_if_closed": 0.08,
                    "mfe": 0.15,
                    "mae": -0.05,
                },
                "trading_intel": {
                    "mfe_capture_estimate": 0.53,
                    "remaining_net_edge": 1.2,
                    "continuation_score": 0.72,
                    "giveback_risk": 0.18,
                    "ai_thesis": "TREND continuation after horizon pass",
                    "last_ai_position_review": {"verdict": "HOLD", "as_of": "2026-08-11T09:00:30Z"},
                },
                "performance": {
                    "win_rate_long": 0.0,
                    "win_rate_short": None,
                    "win_rate_aggregate": 0.0,
                    "net_pnl": -0.34309373,
                    "profit_factor": None,
                },
                "learning": {
                    "mistake_signatures": [{"id": "FEE_LOAD", "count": 1}],
                    "pending_candidate_lessons": [{"id": "L-001", "status": "PENDING"}],
                },
                "last_lifecycle": {"exit_reason": "reduce_only_or_max_hold"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED", str(feed))
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED_ONLY", "1")

    snap = build_founder_demo_monitor_snapshot(actor_tier="FOUNDER", identity_source="test")
    assert snap["schema"] == SCHEMA_ID
    assert snap["feed_ready"] is True
    assert snap["active_position"]["open"] is True
    assert snap["active_position"]["side"] == "LONG"
    assert snap["trading_intel"]["side"] == "LONG"
    assert snap["trading_intel"]["position_state"] == "OPEN"
    assert snap["trading_intel"]["dynamic_profit_zone"]["lower"] == 64500
    assert snap["trading_intel"]["mfe_capture_estimate"] == 0.53
    assert snap["trading_intel"]["continuation_score"] == 0.72
    assert snap["performance"]["net_pnl"] == -0.34309373
    assert len(snap["learning"]["mistake_signatures"]) == 1
    assert snap["display"]["trading_intel_visible"] is True
    assert snap["display"]["performance_visible"] is True
    assert snap["display"]["learning_visible"] is True

    required = (
        "trading_intel.side",
        "trading_intel.mfe_capture_estimate",
        "trading_intel.continuation_score",
        "performance.win_rate_aggregate",
        "performance.net_pnl",
        "learning.mistake_signatures",
        "learning.pending_candidate_lessons",
    )
    for key in required:
        assert key in snap["field_provenance"]
        meta = snap["field_provenance"][key]
        assert meta["source_timestamp"] == "2026-08-11T09:01:00Z"
        assert "freshness_sec" in meta
        assert meta["lane"] == "PNL_BEARING_RESEARCH"
        assert meta["provenance"] == "AGENT_B_V28"


def test_flat_no_fabricated_trading_intel(monkeypatch, tmp_path: Path):
    feed = tmp_path / "founder_demo_monitor_live.json"
    feed.write_text(
        json.dumps(
            {
                "source_timestamp": "2026-08-11T09:00:00Z",
                "provenance": "AGENT_B_LIVE",
                "equity": 5000,
                "position_state": "FLAT",
                "current_real_positions": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED", str(feed))
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED_ONLY", "1")

    snap = build_founder_demo_monitor_snapshot(actor_tier="FOUNDER", identity_source="test")
    assert snap["position_state"] == "FLAT"
    assert snap["trading_intel"]["side"] is None
    assert snap["trading_intel"]["mfe_capture_estimate"] is None
    assert snap["performance"]["win_rate_aggregate"] is None
    assert snap["learning"]["mistake_signatures"] == []
    assert snap["display"]["trading_intel_visible"] is False


@pytest.mark.parametrize("tier", ["PRO", "FREE"])
def test_members_still_403(monkeypatch, tier):
    from flask import Flask

    from backend.api.founder_private_routes import register_founder_private_routes

    monkeypatch.setenv("NEXUS_ENTITLEMENT_TEST_MODE", "1")
    monkeypatch.setenv("NEXUS_MEMBERSHIP_TIER", tier)
    monkeypatch.setenv("NEXUS_FOUNDER_ROUTES_ENABLED", "1")
    monkeypatch.setenv("NEXUS_ENV", "development")

    app = Flask(__name__)
    register_founder_private_routes(app)
    r = app.test_client().get("/api/nexus/founder/demo-monitor")
    assert r.status_code == 403
