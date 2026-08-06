"""Tests for PUB18-A Live Funnel and Market Pulse."""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from backend.nexus_pub18_live_funnel.constants import (
    AI_POSTURES,
    DATA_CLASS_LABELS,
    FIRST_SCREEN_ANSWER_IDS,
    FORBIDDEN_FOUNDER_FIELDS,
    FUNNEL_STAGE_IDS,
    HARD_BANS,
    PRIVATE_CONTRACT_TIP,
)
from backend.nexus_pub18_live_funnel.fixtures import catalog
from backend.nexus_pub18_live_funnel.hard_bans import (
    run_three_passes,
    scan_imports,
    scan_private_field_leaks_in_payloads,
)
from backend.nexus_pub18_live_funnel.honesty import (
    HonestyViolation,
    assert_not_fake_live,
    assert_not_unavailable_as_zero,
    build_metric_slot,
)
from backend.nexus_pub18_live_funnel.routes import register_pub18_live_funnel_routes
from backend.nexus_pub18_live_funnel.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
    count_execution_controls,
)
from backend.nexus_pub18_live_funnel.service import (
    build_first_screen,
    default_member_home_screen,
    list_first_screens,
)

ROOT = Path(__file__).resolve().parents[2]


def test_answer_ids_and_funnel_stages_exact():
    assert list(FIRST_SCREEN_ANSWER_IDS) == [
        "global_market_state",
        "crypto_derivatives_risk",
        "top_3_opportunities",
        "ai_posture",
        "supporting_evidence",
        "counter_evidence",
        "invalidation",
        "data_freshness",
        "data_class_label",
    ]
    assert list(FUNNEL_STAGE_IDS) == [
        "scanned",
        "data_available",
        "liquidity",
        "data_trust",
        "candidate",
        "ai_review",
        "cost_blocked",
        "risk_blocked",
        "shadow_decisions",
    ]
    assert set(AI_POSTURES) == {"LONG", "SHORT", "WAIT", "ABSTAIN"}
    assert set(DATA_CLASS_LABELS) == {"LIVE_READ_ONLY", "STALE", "UNAVAILABLE", "FIXTURE"}


def test_list_first_screens_honesty():
    feed = list_first_screens()
    assert feed["ok"] is True
    assert feed["private_field_leak_count"] == 0
    assert feed["execution_control_count"] == 0
    assert feed["member_execution_control_count"] == 0
    assert feed["private_contract_tip"] == PRIVATE_CONTRACT_TIP
    assert feed["customer_trading"] is False
    rows = feed["first_screens"]
    assert len(rows) >= 4
    labels = {r["data_class"] for r in rows}
    assert labels >= set(DATA_CLASS_LABELS)
    postures = {r["ai_posture"] for r in rows}
    assert postures & {"LONG", "SHORT", "WAIT", "ABSTAIN"}
    for row in rows:
        assert str(row["chrome_label"]).upper() != "LIVE"
        assert row["trade_buttons"] is False
        assert row["actually_traded"] is False
        assert row["execution_control_count"] == 0
        ids = [a["id"] for a in row["answers"]]
        assert ids == list(FIRST_SCREEN_ANSWER_IDS)
        stages = row["funnel"]["stages"]
        assert [s["id"] for s in stages] == list(FUNNEL_STAGE_IDS)
        for s in stages:
            if not s["available"]:
                assert s["display"] != "0"
                assert s["count"] is None


def test_live_read_only_real_zeros_allowed_when_available():
    live = next(c for c in catalog() if c["case_id"] == "pub18_live_read_only_bounded")
    screen = build_first_screen(live)
    assert screen["data_class"] == "LIVE_READ_ONLY"
    assert screen["chrome_label"] == "LIVE_READ_ONLY"
    stages = {s["id"]: s for s in screen["funnel"]["stages"]}
    # Fail-closed real zeros on LIVE_READ_ONLY when stage is available.
    assert stages["data_available"]["available"] is True
    assert stages["data_available"]["count"] == 0
    assert stages["data_available"]["display"] == "0"
    assert stages["candidate"]["count"] == 0
    assert stages["shadow_decisions"]["count"] == 0
    assert stages["scanned"]["count"] == 35


def test_stale_unavailable_never_zero_filled_as_live():
    for case_id in ("pub18_stale", "pub18_unavailable"):
        case = next(c for c in catalog() if c["case_id"] == case_id)
        screen = build_first_screen(case)
        assert screen["chrome_label"] != "LIVE"
        assert screen["chrome_label"] != "LIVE_READ_ONLY"
        for s in screen["funnel"]["stages"]:
            assert s["available"] is False
            assert s["display"] in {"STALE", "UNAVAILABLE"}
            assert s["display"] != "0"


def test_provider_required_not_fake_zero():
    try:
        assert_not_unavailable_as_zero(0, available=False, path="funding")
        raise AssertionError("expected HonestyViolation")
    except HonestyViolation:
        pass
    try:
        build_metric_slot(key="funding", value=0, available=False, provider_required=True)
        raise AssertionError("expected HonestyViolation")
    except HonestyViolation:
        pass
    try:
        assert_not_fake_live(data_class="FIXTURE", chrome_label="LIVE_READ_ONLY")
        raise AssertionError("expected HonestyViolation")
    except HonestyViolation:
        pass


def test_forbidden_founder_and_execution_controls():
    for key in (
        "position_size",
        "leverage",
        "exact_entry",
        "order_id",
        "private_threshold",
        "lesson_memory",
        "place_order",
        "trade_now",
        "execution_controls",
    ):
        try:
            assert_no_forbidden_keys({key: "x"})
            raise AssertionError(f"expected ban for {key}")
        except ForbiddenPayloadKeyError:
            pass
    assert "leverage" in FORBIDDEN_FOUNDER_FIELDS
    assert count_execution_controls({"execution_controls": {"place_order": True}}) == 1
    assert count_execution_controls({"trade_buttons": False}) == 0


def test_home_screen_and_routes():
    home = default_member_home_screen()
    assert home["ok"] is True
    assert home["first_screen"]["answer_count"] == 9
    assert home["first_screen"]["data_class"] == "LIVE_READ_ONLY"
    assert home["execution_control_count"] == 0

    app = Flask(__name__)
    register_pub18_live_funnel_routes(app)
    client = app.test_client()
    r = client.get("/api/public/live-funnel/home")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["first_screen"]["funnel"]["stages"]
    assert "X-NEXUS-Trade-Buttons" in r.headers
    assert r.headers["X-NEXUS-Trade-Buttons"] == "false"

    bad = client.post("/api/public/live-funnel/home", json={})
    assert bad.status_code == 405


def test_three_passes_and_leak_count():
    result = run_three_passes(ROOT)
    assert result["ok"] is True, result
    assert result["private_field_leak_count"] == 0
    assert result["execution_control_count"] == 0
    assert result["private_core_import_count"] == 0
    assert result["customer_trading"] is False
    imports = scan_imports(ROOT)
    assert imports["ok"] is True
    leaks = scan_private_field_leaks_in_payloads()
    assert leaks["private_field_leak_count"] == 0
    assert leaks["execution_control_count"] == 0
    assert "no_fake_live_zeros" in HARD_BANS
    assert "no_trade_buttons" in HARD_BANS


def test_rebuild_all_fixtures():
    for case in catalog():
        screen = build_first_screen(case)
        assert_no_forbidden_keys(screen)
        assert len(screen["answers"]) == 9
        assert len(screen["funnel"]["stages"]) == 9
