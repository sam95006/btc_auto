"""Tests for UX-B Member Web Intelligence Experience."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_member_intel.constants import (
    FUNNEL_STAGE_IDS,
    HARD_BANS,
    LIFECYCLE_STATES,
    MEMBER_POSTURES,
)
from backend.nexus_public_member_intel.hard_bans import run_three_passes, scan_imports
from backend.nexus_public_member_intel.honesty import (
    HonestyViolation,
    assert_mode_label,
    assert_suggestion_not_filled,
    format_count,
)
from backend.nexus_public_member_intel.routes import register_public_member_intel_routes
from backend.nexus_public_member_intel.service import list_experiences, state_matrix

ROOT = Path(__file__).resolve().parents[1]


def test_lifecycle_states_complete():
    required = {
        "OBSERVING",
        "AI_ANALYZING",
        "AI_SUGGESTION",
        "RISK_REVIEW",
        "READY",
        "ENTERED",
        "MANAGING",
        "EXITED",
        "BLOCKED",
        "ABSTAINED",
        "SIMULATION",
        "HISTORICAL_REPLAY",
        "DEMO_DATA",
        "UNAVAILABLE",
        "STALE",
    }
    assert set(LIFECYCLE_STATES) == required
    assert len(LIFECYCLE_STATES) == len(set(LIFECYCLE_STATES))


def test_funnel_and_postures():
    assert list(FUNNEL_STAGE_IDS) == [
        "markets_scanned",
        "liquidity",
        "data_quality",
        "ai_analysis",
        "cost_blocked",
        "risk_blocked",
    ]
    assert set(MEMBER_POSTURES) == {"LONG", "SHORT", "WAIT", "ABSTAIN"}


def test_list_experiences_honesty():
    feed = list_experiences()
    assert feed["ok"] is True
    assert feed["private_core_import_count"] == 0
    assert feed["customer_trading"] is False
    rows = feed["experiences"]
    assert len(rows) >= 4
    postures_seen = {r["posture"] for r in rows}
    assert postures_seen & {"LONG", "SHORT", "WAIT", "ABSTAIN"}
    for row in rows:
        assert row["order_fill_claimed"] is False
        if row["lifecycle_state"] == "AI_SUGGESTION":
            assert row["actually_ordered"] is not True
        if row["mode"] in {"DEMO_DATA", "HISTORICAL_REPLAY", "SIMULATION"}:
            assert str(row["chrome_label"]).upper() != "LIVE"
        for stage in row["funnel"]["stages"]:
            if not stage["available"]:
                assert stage["display"] == "UNAVAILABLE"
                assert stage["count"] is None
                assert stage["display"] != "0"
        similar = row["similar_case_stats"]
        assert similar["guarantee_claimed"] is False
        assert similar.get("win_rate") != 0.6 or similar["guarantee_claimed"] is False
        intel = row["intelligence"]
        assert intel["private_core_import_count"] == 0
        assert intel["raw_memory_graph"] is False
        for key in (
            "regime_probabilities",
            "ai_recommendation_state",
            "supporting_evidence",
            "contradicting_evidence",
            "uncertainty",
            "abstention_reason",
            "strategy_expert_label",
            "lesson_applied_label",
            "similar_case_summary",
            "data_freshness",
            "decision_lifecycle_status",
        ):
            assert key in intel


def test_unavailable_never_formats_as_zero():
    assert format_count(None, available=False) == "UNAVAILABLE"
    assert format_count(0, available=False) == "UNAVAILABLE"
    with pytest.raises(HonestyViolation):
        assert_mode_label(mode="DEMO_DATA", label="LIVE")
    with pytest.raises(HonestyViolation):
        assert_suggestion_not_filled(
            lifecycle_state="AI_SUGGESTION",
            actually_ordered=True,
            order_fill_claimed=True,
        )


def test_state_matrix_distinct():
    matrix = state_matrix()
    states = [s["state"] for s in matrix["states"]]
    assert states == list(LIFECYCLE_STATES)


def test_three_passes():
    result = run_three_passes(ROOT)
    assert result["ok"] is True
    assert result["pass_count"] == 3
    assert result["private_core_import_count"] == 0
    assert result["status_json_written"] is False
    assert all(p["ok"] for p in result["passes"])


def test_private_core_import_count_zero():
    scan = scan_imports(ROOT)
    assert scan["ok"] is True
    assert scan["private_core_import_count"] == 0


def test_routes_register():
    from flask import Flask

    app = Flask(__name__)
    register_public_member_intel_routes(app)
    client = app.test_client()
    meta = client.get("/api/public/member-intel/meta")
    assert meta.status_code == 200
    body = meta.get_json()
    assert body["ok"] is True
    assert body["lane"] == "UX-B"
    feed = client.get("/api/public/member-intel/experiences")
    assert feed.status_code == 200
    assert feed.headers.get("X-NEXUS-Demo-Data") == "DEMO_DATA"
    denied = client.post("/api/public/member-intel/experiences")
    assert denied.status_code == 405


def test_hard_bans_listed():
    for ban in (
        "no_unavailable_as_zero",
        "no_fixture_as_live",
        "no_ai_suggestion_as_filled_order",
        "no_backtest_as_live",
        "no_fake_60_percent_guarantee",
        "no_private_core_imports",
    ):
        assert ban in HARD_BANS
