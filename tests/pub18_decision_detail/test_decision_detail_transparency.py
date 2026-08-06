"""Tests for PUB18-B Decision Detail and Learning Transparency."""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from backend.nexus_pub18_decision_detail.constants import (
    AI_POSTURES,
    FORBIDDEN_PRIVATE_FIELDS,
    HARD_BANS,
    MEMBER_VISIBLE_FIELD_IDS,
)
from backend.nexus_pub18_decision_detail.fixtures import catalog
from backend.nexus_pub18_decision_detail.hard_bans import (
    run_three_passes,
    scan_imports,
    scan_private_field_leaks_in_payloads,
)
from backend.nexus_pub18_decision_detail.honesty import (
    HonestyViolation,
    assert_not_unavailable_as_zero,
    build_metric_slot,
)
from backend.nexus_pub18_decision_detail.routes import register_pub18_decision_detail_routes
from backend.nexus_pub18_decision_detail.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
)
from backend.nexus_pub18_decision_detail.service import (
    build_decision_detail,
    default_member_decision_detail,
    list_decision_details,
)

ROOT = Path(__file__).resolve().parents[2]


def test_twelve_member_visible_field_ids_exact():
    assert list(MEMBER_VISIBLE_FIELD_IDS) == [
        "decision_timeline",
        "market_regime",
        "data_trust",
        "strategy_expert_label",
        "evidence",
        "counter_evidence",
        "risk_reason",
        "why_wait_abstain",
        "historical_similarity_aggregate",
        "shadow_outcome",
        "process_classification_aggregate",
        "delayed_learning_summary",
    ]
    assert set(AI_POSTURES) == {"LONG", "SHORT", "WAIT", "ABSTAIN"}


def test_list_decision_details_honesty():
    feed = list_decision_details()
    assert feed["ok"] is True
    assert feed["private_field_leak_count"] == 0
    assert feed["private_core_import_count"] == 0
    assert feed["customer_trading"] is False
    rows = feed["decision_details"]
    assert len(rows) >= 4
    postures = {r["ai_posture"] for r in rows}
    assert postures & {"WAIT", "ABSTAIN"}
    for row in rows:
        assert str(row["chrome_label"]).upper() != "LIVE"
        if row["mode"] in {"DEMO_DATA", "FIXTURE", "PROVIDER_REQUIRED", "UNAVAILABLE"}:
            assert str(row["chrome_label"]).upper() != "LIVE_READ_ONLY"
        ids = [f["id"] for f in row["fields"]]
        assert ids == list(MEMBER_VISIBLE_FIELD_IDS)
        assert row["private_fields_included"] is False
        assert row["actually_traded"] is False
        assert row["exchange_write"] is False
        delayed = next(f for f in row["fields"] if f["id"] == "delayed_learning_summary")
        assert delayed.get("private_lesson_memory") is False


def test_provider_required_not_fake_zero():
    try:
        assert_not_unavailable_as_zero(0, available=False, provider_required=True, path="similarity")
        raise AssertionError("expected HonestyViolation")
    except HonestyViolation:
        pass
    try:
        build_metric_slot(key="similarity", value=0, available=False, provider_required=True)
        raise AssertionError("expected HonestyViolation")
    except HonestyViolation:
        pass
    slot = build_metric_slot(key="similarity", value=None, available=False, provider_required=True)
    assert slot["display"] == "PROVIDER_REQUIRED"
    assert slot["value"] is None


def test_forbidden_private_fields_rejected():
    for key in (
        "private_raw_graph",
        "proprietary_threshold",
        "strategy_weights",
        "founder_entry",
        "founder_exit",
        "internal_prompt",
        "raw_cot",
        "account_data",
        "chain_of_thought",
        "exact_entry",
        "system_prompt",
    ):
        try:
            assert_no_forbidden_keys({key: "x"})
            raise AssertionError(f"expected ban for {key}")
        except ForbiddenPayloadKeyError:
            pass
    assert "private_raw_graph" in FORBIDDEN_PRIVATE_FIELDS
    assert "strategy_weights" in FORBIDDEN_PRIVATE_FIELDS
    assert "raw_cot" in FORBIDDEN_PRIVATE_FIELDS


def test_default_detail_and_routes():
    home = default_member_decision_detail()
    assert home["ok"] is True
    assert home["decision_detail"]["field_count"] == 12
    assert home["decision_detail"]["ai_posture"] in AI_POSTURES

    app = Flask(__name__)
    register_pub18_decision_detail_routes(app)
    client = app.test_client()
    r = client.get("/api/public/decision-detail/default")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["decision_detail"]["field_count"] == 12
    assert "X-NEXUS-Learning-Transparency" in r.headers

    meta = client.get("/api/public/decision-detail/meta")
    assert meta.status_code == 200
    meta_body = meta.get_json()
    assert "private_raw_graph" in meta_body["member_must_not_see"]
    assert "decision_timeline" in meta_body["member_may_see"]

    bad = client.post("/api/public/decision-detail/default", json={})
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
    assert "no_private_raw_graph" in HARD_BANS
    assert "no_raw_cot" in HARD_BANS
    assert "no_account_data" in HARD_BANS


def test_rebuild_all_fixtures():
    for case in catalog():
        detail = build_decision_detail(case)
        assert_no_forbidden_keys(detail)
        assert len(detail["fields"]) == 12
        assert detail["field_count"] == 12
