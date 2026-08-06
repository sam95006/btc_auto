"""Tests for PUB17-B Market Pulse and Top Opportunities first screen."""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from backend.nexus_pub17_market_pulse.constants import (
    AI_POSTURES,
    FIRST_SCREEN_ANSWER_IDS,
    FORBIDDEN_FOUNDER_FIELDS,
    HARD_BANS,
)
from backend.nexus_pub17_market_pulse.hard_bans import (
    run_three_passes,
    scan_imports,
    scan_private_field_leaks_in_payloads,
)
from backend.nexus_pub17_market_pulse.honesty import (
    HonestyViolation,
    assert_not_unavailable_as_zero,
    build_metric_slot,
)
from backend.nexus_pub17_market_pulse.routes import register_pub17_market_pulse_routes
from backend.nexus_pub17_market_pulse.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
)
from backend.nexus_pub17_market_pulse.service import (
    build_first_screen,
    default_member_home_screen,
    list_first_screens,
)
from backend.nexus_pub17_market_pulse.fixtures import catalog

ROOT = Path(__file__).resolve().parents[2]


def test_nine_answer_ids_exact():
    assert list(FIRST_SCREEN_ANSWER_IDS) == [
        "global_market_state",
        "crypto_derivatives_risk",
        "top_3_markets_contracts",
        "ai_posture",
        "supporting_evidence",
        "counter_evidence",
        "invalidation",
        "data_freshness",
        "analysis_vs_actual_trading",
    ]
    assert set(AI_POSTURES) == {"LONG", "SHORT", "WAIT", "ABSTAIN"}


def test_list_first_screens_honesty():
    feed = list_first_screens()
    assert feed["ok"] is True
    assert feed["private_field_leak_count"] == 0
    assert feed["private_core_import_count"] == 0
    assert feed["customer_trading"] is False
    rows = feed["first_screens"]
    assert len(rows) >= 3
    postures = {r["ai_posture"] for r in rows}
    assert postures & {"LONG", "SHORT", "WAIT", "ABSTAIN"}
    for row in rows:
        assert str(row["chrome_label"]).upper() != "LIVE"
        ids = [a["id"] for a in row["answers"]]
        assert ids == list(FIRST_SCREEN_ANSWER_IDS)
        assert row["private_fields_included"] is False
        for a in row["answers"]:
            if a["id"] == "crypto_derivatives_risk":
                for m in a.get("metrics") or []:
                    if not m["available"]:
                        assert m["display"] != "0"
                        assert m["display"] != 0
                    if m.get("provider_required"):
                        assert m["display"] == "PROVIDER_REQUIRED"
            if a["id"] == "analysis_vs_actual_trading":
                assert a.get("actually_traded") is False
                assert a.get("exchange_write") is False


def test_provider_required_not_fake_zero():
    try:
        assert_not_unavailable_as_zero(0, available=False, provider_required=True, path="funding")
        raise AssertionError("expected HonestyViolation")
    except HonestyViolation:
        pass
    try:
        build_metric_slot(key="funding", value=0, available=False, provider_required=True)
        raise AssertionError("expected HonestyViolation")
    except HonestyViolation:
        pass
    slot = build_metric_slot(key="funding", value=None, available=False, provider_required=True)
    assert slot["display"] == "PROVIDER_REQUIRED"
    assert slot["value"] is None


def test_forbidden_founder_fields_rejected():
    for key in (
        "position_size",
        "leverage",
        "exact_entry",
        "exact_stop",
        "order_id",
        "private_threshold",
        "strategy_source",
        "entry_price",
        "stop_loss",
    ):
        try:
            assert_no_forbidden_keys({key: "x"})
            raise AssertionError(f"expected ban for {key}")
        except ForbiddenPayloadKeyError:
            pass
    assert "leverage" in FORBIDDEN_FOUNDER_FIELDS
    assert "position_size" in FORBIDDEN_FOUNDER_FIELDS


def test_home_screen_and_routes():
    home = default_member_home_screen()
    assert home["ok"] is True
    assert home["first_screen"]["answer_count"] == 9
    assert home["first_screen"]["ai_posture"] in AI_POSTURES

    app = Flask(__name__)
    register_pub17_market_pulse_routes(app)
    client = app.test_client()
    r = client.get("/api/public/market-pulse/home")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["first_screen"]["answer_count"] == 9
    assert "X-NEXUS-Analysis-Only" in r.headers

    bad = client.post("/api/public/market-pulse/home", json={})
    assert bad.status_code == 405


def test_three_passes_and_leak_count():
    result = run_three_passes(ROOT)
    assert result["ok"] is True
    assert result["private_field_leak_count"] == 0
    assert result["private_core_import_count"] == 0
    assert result["customer_trading"] is False
    assert result["exchange_api_used"] is False
    imports = scan_imports(ROOT)
    assert imports["ok"] is True
    leaks = scan_private_field_leaks_in_payloads()
    assert leaks["private_field_leak_count"] == 0
    assert "no_leverage" in HARD_BANS
    assert "no_fake_live_zeros" in HARD_BANS


def test_rebuild_all_fixtures():
    for case in catalog():
        screen = build_first_screen(case)
        assert_no_forbidden_keys(screen)
        assert len(screen["answers"]) == 9
