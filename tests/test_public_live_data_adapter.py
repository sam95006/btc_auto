"""Tests for PUB-C Public Live Data Adapter and lineage."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_live_data.constants import (
    DEMO_DATA_BANNER,
    HARD_BANS,
    LINEAGE_REQUIRED_KEYS,
    MODE_FIXTURE,
    MODE_LIVE,
    PUBLIC_SAFE_FIELDS,
)
from backend.nexus_public_live_data.hard_bans import (
    HardBanViolation,
    refuse_customer_trading,
    refuse_exchange_write,
    refuse_fabricated_live_value,
    refuse_private_core_import,
    refuse_silent_fixture_fallback,
    run_two_passes,
)
from backend.nexus_public_live_data.lineage import assert_lineage_complete
from backend.nexus_public_live_data.routes import register_public_live_data_routes
from backend.nexus_public_live_data.sanitize import ForbiddenPayloadKeyError, assert_no_forbidden_keys
from backend.nexus_public_live_data import adapter, sources

ROOT = Path(__file__).resolve().parents[1]


def test_public_safe_fields_cover_directive_examples():
    required = {
        "market.last_price.BTCUSDT",
        "system.runtime_health",
        "system.capture_campaign_health",
        "system.reflection_v23_progress",
        "system.qualification_state",
        "system.event_study_readiness",
        "system.qualification_ready_count",
    }
    assert required.issubset(set(PUBLIC_SAFE_FIELDS))


def test_fixture_mode_shows_demo_data_prominently():
    body = adapter.bind_all(mode=MODE_FIXTURE)
    assert body["mode"] == MODE_FIXTURE
    assert body["demo_data"] is True
    assert body["banner"] == DEMO_DATA_BANNER
    assert body["banner_prominent"] is True
    assert "DEMO_DATA" in body["disclaimer"]
    for field_id, row in body["fields"].items():
        assert row["demo_data"] is True
        assert row["mode"] == MODE_FIXTURE
        assert row["freshness"] == "DEMO_DATA"
        assert row["display_state"] == "DEMO_DATA"
        assert_lineage_complete(row)
        for key in LINEAGE_REQUIRED_KEYS:
            assert key in row, f"{field_id} missing {key}"


def test_live_mode_never_silent_fixture_fallback():
    # Force market fetch failure → UNAVAILABLE, not DEMO numbers
    def boom(_symbol: str):
        raise RuntimeError("forced_unavailable")

    bound = sources.bind_market_field(
        field_id="market.last_price.BTCUSDT",
        symbol="BTCUSDT",
        source_field="result.list[0].lastPrice",
        unit="USD",
        extractor=lambda r: r.get("lastPrice"),
        fetch=boom,
    )
    payload = bound.to_dict()
    assert payload["mode"] == MODE_LIVE
    assert payload["demo_data"] is False
    assert payload["value"] is None
    assert payload["display_state"] == "UNAVAILABLE"
    assert payload["freshness"] == "UNAVAILABLE"
    assert payload["fallback"] == "display_UNAVAILABLE"
    assert_lineage_complete(payload)


def test_live_bind_all_rejects_demo_leak(monkeypatch):
    from backend.nexus_public_live_data.lineage import demo_bound

    monkeypatch.setattr(
        adapter,
        "_live_binders",
        lambda: {
            fid: (lambda f=fid: demo_bound(
                field_id=f,
                value=1,
                unit="x",
                source_field="x",
                as_of="2026-08-05T12:00:00Z",
            ))
            for fid in PUBLIC_SAFE_FIELDS
        },
    )
    with pytest.raises(adapter.LiveModeFixtureLeakError):
        adapter.bind_field("market.last_price.BTCUSDT", mode=MODE_LIVE)


def test_qualification_and_event_study_are_blocked_not_fake_positive():
    q = adapter.bind_field("system.qualification_state", mode=MODE_LIVE)
    assert q["value"] == "BLOCKED"
    assert q["display_state"] == "BLOCKED"
    assert q["demo_data"] is False
    es = adapter.bind_field("system.event_study_readiness", mode=MODE_LIVE)
    assert es["value"] == "NOT_READY"
    count = adapter.bind_field("system.qualification_ready_count", mode=MODE_LIVE)
    assert count["value"] == 0


def test_missing_runtime_health_is_unavailable():
    bound = sources.bind_runtime_health(runtime_root=ROOT / "does_not_exist_runtime")
    payload = bound.to_dict()
    assert payload["value"] is None
    assert payload["freshness"] == "UNAVAILABLE"
    assert payload["display_state"] == "UNAVAILABLE"


def test_lineage_keys_on_live_policy_fields():
    for field_id in (
        "system.qualification_state",
        "system.event_study_readiness",
        "system.qualification_ready_count",
        "decision.cloud.freshness",
        "decision.cloud.availability",
    ):
        row = adapter.bind_field(field_id, mode=MODE_LIVE)
        assert_lineage_complete(row)
        assert row["demo_data"] is False
        assert row["mode"] == MODE_LIVE


def test_sanitize_blocks_secrets():
    with pytest.raises(ForbiddenPayloadKeyError):
        assert_no_forbidden_keys({"api_key": "x"})


def test_hard_ban_refusers():
    with pytest.raises(HardBanViolation):
        refuse_fabricated_live_value()
    with pytest.raises(HardBanViolation):
        refuse_silent_fixture_fallback()
    with pytest.raises(HardBanViolation):
        refuse_customer_trading()
    with pytest.raises(HardBanViolation):
        refuse_exchange_write()
    with pytest.raises(HardBanViolation):
        refuse_private_core_import()


def test_hard_ban_two_passes():
    result = run_two_passes(ROOT)
    assert result["pass_count"] == 2
    assert result["ok"] is True
    assert result["hard_bans_intact"] is True
    assert result["lane"] == "PUB-C"
    assert len(result["passes"]) == 2
    assert result["passes"][0]["pass_number"] == 1
    assert result["passes"][1]["pass_number"] == 2
    assert set(HARD_BANS).issubset(set(result["passes"][0]["hard_bans"]))


def test_flask_routes_fixture_banner_and_read_only():
    flask = pytest.importorskip("flask")
    app = flask.Flask("test_live_data")
    register_public_live_data_routes(app)
    client = app.test_client()

    meta = client.get("/api/public/live-data/meta?mode=FIXTURE")
    assert meta.status_code == 200
    assert meta.headers.get("X-NEXUS-DEMO-DATA") == "DEMO_DATA"
    payload = meta.get_json()
    assert payload["banner"] == "DEMO_DATA"
    assert payload["banner_prominent"] is True
    assert payload["customer_trading"] is False
    assert payload["exchange_write"] is False

    bindings = client.get("/api/public/live-data/bindings?mode=FIXTURE")
    assert bindings.status_code == 200
    body = bindings.get_json()
    assert body["demo_data"] is True
    assert body["summary"]["silent_fixture_fallback"] is False

    denied = client.post("/api/public/live-data/bindings")
    assert denied.status_code == 405
