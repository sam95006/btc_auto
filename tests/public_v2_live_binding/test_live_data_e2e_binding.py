"""PUB2-B live data e2e binding tests — three passes, required counters."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_v2_live_binding.binder import bind_all_components, bind_component
from backend.nexus_public_v2_live_binding.constants import (
    BINDING_REQUIRED_KEYS,
    HARD_BANS,
    LANE,
    REQUIRED_COUNTERS,
)
from backend.nexus_public_v2_live_binding.display_rules import (
    format_display_value,
    is_unavailable_shown_as_zero,
)
from backend.nexus_public_v2_live_binding.hard_bans import (
    HardBanViolation,
    refuse_demo_as_live,
    refuse_exchange_write,
    refuse_fabricated_live,
    refuse_pr_merge,
    refuse_private_core,
    run_three_passes,
)
from backend.nexus_public_v2_live_binding.inventory import COMPONENT_LIVE_SPECS
from backend.nexus_public_v2_live_binding.routes import register_public_v2_live_binding_routes
from backend.nexus_public_v2_live_binding.three_pass import run_three_pass_verification
from backend.nexus_public_v2_live_binding.verifier import compute_counters, verify_live_e2e_binding
from backend.nexus_public_ui_trace.component_catalog import UI_COMPONENT_CATALOG

ROOT = Path(__file__).resolve().parents[2]


def test_inventory_covers_all_ui_components():
    catalog_ids = {c.component_id for c in UI_COMPONENT_CATALOG}
    spec_ids = {s.component_id for s in COMPONENT_LIVE_SPECS}
    assert catalog_ids == spec_ids
    assert len(COMPONENT_LIVE_SPECS) >= 50


def test_bind_all_components_have_required_keys():
    payload = bind_all_components(mode="LIVE")
    assert payload["mode"] == "LIVE"
    assert payload["component_count"] == len(COMPONENT_LIVE_SPECS)
    for cid, comp in payload["components"].items():
        assert comp["slots"], cid
        for slot in comp["slots"]:
            for key in BINDING_REQUIRED_KEYS:
                assert key in slot, f"{cid}.{slot['slot_id']} missing {key}"
            assert slot["value_source"] == "LIVE"
            assert slot["hardcoded"] is False
            assert slot["fabricated"] is False
            assert slot["demo_data"] is False
            # UNAVAILABLE must not display as 0
            if str(slot["freshness"]).upper() in {"UNAVAILABLE", "BLOCKED"}:
                assert str(slot["display_value"]) not in {"0", "0.0"}


def test_refuse_non_live_mode():
    with pytest.raises(ValueError, match="LIVE-only"):
        bind_all_components(mode="FIXTURE")
    with pytest.raises(ValueError, match="LIVE-only"):
        bind_all_components(mode="DEMO")


def test_unavailable_never_shown_as_zero():
    text, shown_zero = format_display_value(
        None, freshness="UNAVAILABLE", completeness="MISSING"
    )
    assert text == "UNAVAILABLE"
    assert shown_zero is False
    assert is_unavailable_shown_as_zero(
        value=None,
        freshness="UNAVAILABLE",
        completeness="MISSING",
        display_text="UNAVAILABLE",
    ) is False
    assert is_unavailable_shown_as_zero(
        value=None,
        freshness="UNAVAILABLE",
        completeness="MISSING",
        display_text="0",
    ) is True


def test_stale_requires_indicator_in_bindings():
    # Construct via real bind; if any STALE/DEGRADED, indicator must be present
    payload = bind_all_components()
    for comp in payload["components"].values():
        for slot in comp["slots"]:
            if str(slot["freshness"]).upper() in {"STALE", "DEGRADED"}:
                assert slot["stale_indicator_present"] is True


def test_counters_all_zero():
    counters = compute_counters(root=ROOT)
    assert counters.as_dict() == {
        "hardcoded_live_value_count": 0,
        "fabricated_live_value_count": 0,
        "stale_without_indicator_count": 0,
        "unavailable_shown_as_zero_count": 0,
    }
    assert list(REQUIRED_COUNTERS) == list(counters.as_dict().keys())


def test_verify_pass():
    result = verify_live_e2e_binding(root=ROOT)
    assert result["status"] == "PASS"
    assert result["lane"] == LANE


def test_three_pass_verification():
    result = run_three_pass_verification(root=ROOT)
    assert result["pass_count"] == 3
    assert result["three_pass_status"] == "PASS"
    assert result["counters_match"] is True
    assert result["status_json_written"] is False
    assert result["observed"]["hardcoded_live_value_count"] == 0
    assert result["observed"]["fabricated_live_value_count"] == 0
    assert result["observed"]["stale_without_indicator_count"] == 0
    assert result["observed"]["unavailable_shown_as_zero_count"] == 0


def test_hard_ban_refusers_and_three_passes():
    with pytest.raises(HardBanViolation):
        refuse_demo_as_live()
    with pytest.raises(HardBanViolation):
        refuse_fabricated_live()
    with pytest.raises(HardBanViolation):
        refuse_exchange_write()
    with pytest.raises(HardBanViolation):
        refuse_private_core()
    with pytest.raises(HardBanViolation):
        refuse_pr_merge()
    bans = run_three_passes(ROOT)
    assert bans["pass_count"] == 3
    assert bans["ok"] is True
    assert set(HARD_BANS).issubset(set(bans["passes"][0]["hard_bans"]))


def test_bind_unknown_component():
    with pytest.raises(KeyError):
        bind_component("not.a.real.component")


def test_flask_routes_read_only():
    flask = pytest.importorskip("flask")
    app = flask.Flask("test_pub2_b")
    register_public_v2_live_binding_routes(app)
    client = app.test_client()
    res = client.get("/api/public/v2/live-bindings")
    assert res.status_code == 200
    body = res.get_json()
    assert body["mode"] == "LIVE"
    assert body["component_count"] >= 50
    denied = client.post("/api/public/v2/live-bindings")
    assert denied.status_code == 405
