"""V18.2.27 Founder demo monitor — live core feed binding + provenance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_founder_demo_monitor.loader import load_raw_monitor_feed
from backend.nexus_founder_demo_monitor.snapshot import build_founder_demo_monitor_snapshot


def test_live_feed_preferred_over_fixture(monkeypatch, tmp_path: Path):
    live = tmp_path / "founder_demo_monitor_live.json"
    live.write_text(
        json.dumps(
            {
                "schema": "v18_2_27_founder_demo_monitor_live_v1",
                "source_timestamp": "2026-08-11T08:01:00Z",
                "provenance": "AGENT_B_TEST",
                "account_uid": "567649663",
                "equity": "5022.6119968",
                "wallet_balance": "5027.43833761",
                "lane_label": "PNL_BEARING_RESEARCH",
                "position_state": "FLAT",
                "current_real_positions": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED", str(live))
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED_ONLY", "1")

    blob, source, status, fixture_used = load_raw_monitor_feed()
    assert status == "FEED_READY"
    assert fixture_used is False
    assert source == str(live)
    assert blob is not None
    assert blob.get("position_state") == "FLAT"


def test_core_evidence_v26_maps_flat_with_wallet(monkeypatch, tmp_path: Path):
    core = tmp_path / "v18_2_26_core.json"
    core.write_text(
        json.dumps(
            {
                "schema": "v18_2_26_core_v1",
                "generated_at": "2026-08-11T08:01:00Z",
                "directive": "V18.2.26_TEST",
                "REAL_DEMO_ACCOUNT": {
                    "account_uid": "567649663",
                    "equity": "5022.6119968",
                    "wallet_balance": "5027.43833761",
                    "available_balance": "5027.43833761",
                    "settle_coin": "USDT",
                    "wallet_type": "UNIFIED",
                    "current_real_positions": [],
                },
                "PNL_ACCOUNTING": {
                    "v24_prior_exact_breakdown": {
                        "exchange_closed_pnl": "-0.34309373",
                        "total_fees": "0.35259373",
                        "wallet_delta": "-0.34309373",
                        "calculated_net_pnl": "-0.34309373",
                        "identities": {"exchange_closed_approx_wallet_delta": True},
                    }
                },
                "HORIZON": {
                    "plan": {
                        "strategy_family": "TREND",
                        "regime": "TREND_UP",
                        "hard_max_hold": 720,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED", str(core))
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED_ONLY", "1")

    snap = build_founder_demo_monitor_snapshot(actor_tier="FOUNDER", identity_source="test")
    assert snap["feed_ready"] is True
    assert snap["position_state"] == "FLAT"
    assert snap["active_position"]["open"] is False
    assert snap["active_position"]["state"] == "FLAT"
    assert snap["wallet"]["equity"] == 5022.6119968
    assert snap["display"]["wallet"] is True
    assert snap["display"]["live_position"] is False
    assert snap["accounting"]["exchange_closed_pnl"] == -0.34309373
    assert snap["thesis"] is not None
    assert "wallet.equity" in snap["field_provenance"]
    assert snap["field_provenance"]["wallet.equity"]["provenance"].startswith("AGENT_B_")


def test_field_provenance_present_on_live_feed(monkeypatch, tmp_path: Path):
    feed = tmp_path / "founder_demo_monitor_live.json"
    feed.write_text(
        json.dumps(
            {
                "source_timestamp": "2026-08-11T08:01:00Z",
                "provenance": "AGENT_B_LIVE",
                "account_uid": "567649663",
                "equity": 5000,
                "wallet_balance": 5000,
                "lane_label": "PNL_BEARING_RESEARCH",
                "position_state": "FLAT",
                "current_real_positions": [],
                "last_lifecycle": {
                    "realized_pnl": "-1.0",
                    "fees": "0.1",
                    "wallet_delta": "-1.0",
                    "exit_reason": "test_exit",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED", str(feed))
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED_ONLY", "1")

    snap = build_founder_demo_monitor_snapshot(actor_tier="FOUNDER", identity_source="test")
    required = (
        "wallet.equity",
        "position.state",
        "position.unrealized_pnl",
        "position.estimated_net_if_closed",
        "position.strategy_horizon",
        "mfe",
        "mae",
        "thesis",
        "accounting.last_realized_trade",
    )
    for key in required:
        assert key in snap["field_provenance"]
        meta = snap["field_provenance"][key]
        assert "source_timestamp" in meta
        assert "freshness_sec" in meta
        assert "lane" in meta
        assert "provenance" in meta


@pytest.mark.parametrize("tier", ["PRO", "FREE"])
def test_anonymous_routes_still_fail_closed_without_founder(monkeypatch, tier):
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
