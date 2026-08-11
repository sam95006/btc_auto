"""V18.2.25 Founder-only demo monitor — auth + fail-closed empty + feed mapping."""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask

from backend.nexus_founder_demo_monitor.snapshot import (
    build_founder_demo_monitor_snapshot,
    mask_demo_uid,
)
from backend.nexus_founder_demo_monitor.sanitize import assert_no_forbidden_keys


def _app():
    app = Flask(__name__)
    from backend.api.founder_private_routes import register_founder_private_routes

    register_founder_private_routes(app)
    return app


def _founder_env(monkeypatch):
    monkeypatch.delenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", raising=False)
    monkeypatch.delenv("ZEABUR", raising=False)
    monkeypatch.delenv("ZEABUR_SERVICE_ID", raising=False)
    monkeypatch.setenv("NEXUS_ENTITLEMENT_TEST_MODE", "1")
    monkeypatch.setenv("NEXUS_MEMBERSHIP_TIER", "FOUNDER")
    monkeypatch.setenv("NEXUS_FOUNDER_ROUTES_ENABLED", "1")
    monkeypatch.setenv("NEXUS_ENV", "development")


def _member_env(monkeypatch, tier: str = "PRO"):
    monkeypatch.delenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", raising=False)
    monkeypatch.setenv("NEXUS_ENTITLEMENT_TEST_MODE", "1")
    monkeypatch.setenv("NEXUS_MEMBERSHIP_TIER", tier)
    monkeypatch.setenv("NEXUS_FOUNDER_ROUTES_ENABLED", "1")
    monkeypatch.setenv("NEXUS_ENV", "development")


def test_mask_demo_uid():
    assert mask_demo_uid("567649663") == "567***663"
    assert mask_demo_uid(None) is None


def test_member_gets_403(monkeypatch):
    _member_env(monkeypatch, "PRO")
    r = _app().test_client().get("/api/nexus/founder/demo-monitor")
    assert r.status_code == 403
    body = r.get_json()
    assert body["ok"] is False
    assert body["memberAccessible"] is False
    assert body["founderOnly"] is True


def test_spoof_header_rejected(monkeypatch):
    _member_env(monkeypatch, "PRO")
    r = (
        _app()
        .test_client()
        .get("/api/nexus/founder/demo-monitor", headers={"X-Nexus-Tier": "FOUNDER"})
    )
    assert r.status_code == 403
    assert "fake_header_rejected" in r.get_json()["error"]


def test_founder_fail_closed_empty_without_v25_feed(monkeypatch, tmp_path: Path):
    _founder_env(monkeypatch)
    # Point evidence root at empty dir so stale v23/v24 cores are not consumed as live.
    monkeypatch.setenv("NEXUS_EVIDENCE_COORDINATOR", str(tmp_path))
    monkeypatch.delenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED", raising=False)
    # Override default absolute candidates by setting feed to missing path.
    missing = tmp_path / "missing_live.json"
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED", str(missing))
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED_ONLY", "1")

    # Also shadow defaults: loader still checks DEFAULT paths; build should
    # fail-closed on FEED_STALE_CORE or empty. Force empty by using only env feed.
    r = _app().test_client().get("/api/nexus/founder/demo-monitor")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["founderOnly"] is True
    assert body["memberAccessible"] is False
    assert body["feed_ready"] is False
    assert body["display"]["live_position"] is False
    assert body["display"]["wallet"] is False
    assert body["display"]["MFE_MAE"] is False
    assert body["display"]["accounting_visible"] is False
    assert body["demo_uid_masked"] is None
    assert body["active_position"]["open"] is False
    assert assert_no_forbidden_keys(body) == []


def test_founder_consumes_ready_feed(monkeypatch, tmp_path: Path):
    _founder_env(monkeypatch)
    feed = tmp_path / "founder_demo_monitor_live.json"
    feed.write_text(
        json.dumps(
            {
                "schema": "v18_2_25_founder_only_demo_monitor_v1",
                "account_uid": "567649663",
                "equity": "5022.70751813",
                "wallet_balance": "5027.43833761",
                "available_balance": "5027.43833761",
                "settle_coin": "USDT",
                "demo_account_type": "UNIFIED",
                "lane_label": "PNL_BEARING_RESEARCH",
                "current_real_position": [],
                "mfe": 12.5,
                "mae": -3.2,
                "last_lifecycle": {
                    "symbol": "BTCUSDT",
                    "side": "LONG",
                    "entry": "64016.9",
                    "exit": "64016.9",
                    "qty": "0.001",
                    "realized_pnl": "-0.34309373",
                    "fees": "0.35259373",
                    "wallet_delta": "-0.34309373",
                    "wallet_recon_status": "WALLET_RECONCILIATION_PASS",
                    "exit_reason": "reduce_only_or_max_hold",
                    "process_class": "GOOD_PROCESS_LOSS",
                    "pnl_provenance": "EXCHANGE_REALIZED_PNL",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED", str(feed))
    monkeypatch.setenv("NEXUS_EVIDENCE_COORDINATOR", str(tmp_path))

    r = _app().test_client().get("/api/nexus/founder/demo-monitor")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["feed_ready"] is True
    assert body["demo_uid_masked"] == "567***663"
    assert body["lane_label"] == "PNL_BEARING_RESEARCH"
    assert body["wallet"]["equity"] == 5022.70751813
    assert body["display"]["wallet"] is True
    assert body["display"]["MFE_MAE"] is True
    assert body["display"]["accounting_visible"] is True
    assert body["accounting"]["last_exit_reason"] == "reduce_only_or_max_hold"
    assert body["accounting"]["wallet_reconciliation_status"] == "WALLET_RECONCILIATION_PASS"
    assert body["mfe"] == 12.5
    assert body["mae"] == -3.2
    assert "orderId" not in json.dumps(body)
    assert assert_no_forbidden_keys(body) == []


def test_build_snapshot_open_position(monkeypatch, tmp_path: Path):
    feed = tmp_path / "founder_demo_monitor_live.json"
    feed.write_text(
        json.dumps(
            {
                "account_uid": "567649663",
                "equity": 5000,
                "wallet_balance": 5000,
                "lane_label": "EXECUTION_CANARY",
                "active_position": {
                    "symbol": "ETHUSDT",
                    "side": "SHORT",
                    "qty": 0.1,
                    "entry": 2500,
                    "current": 2490,
                    "stop": 2520,
                    "target": 2450,
                    "unrealized_pnl": 1.0,
                    "expected_net_target": 4.5,
                    "expected_time_to_target": "12m",
                    "strategy_horizon": "intraday",
                    "hold_duration": "180s",
                    "mfe": 2.0,
                    "mae": -0.5,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_FOUNDER_DEMO_MONITOR_FEED", str(feed))
    snap = build_founder_demo_monitor_snapshot(
        actor_tier="FOUNDER",
        identity_source="test",
    )
    assert snap["feed_ready"] is True
    assert snap["lane_label"] == "EXECUTION_CANARY"
    assert snap["active_position"]["open"] is True
    assert snap["active_position"]["symbol"] == "ETHUSDT"
    assert snap["active_position"]["notional"] == 250.0
    assert snap["display"]["live_position"] is True
