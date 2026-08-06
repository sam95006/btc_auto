"""Tests for PUB18 Alert Engine shared read-only contract."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_pub18_alert_engine.constants import (
    ALERT_KIND_LABELS,
    ALERT_KINDS,
    HYPE_PHRASES,
    REQUIRED_FIELDS,
)
from backend.nexus_pub18_alert_engine.contract import (
    build_alert_engine_contract,
    validate_alert_envelope,
)
from backend.nexus_pub18_alert_engine.hard_bans import (
    HardBanViolation,
    assert_no_hype_phrases,
    run_three_passes,
)
from backend.nexus_pub18_alert_engine.models import (
    build_readonly_alert,
    fixture_alert_catalog,
)

ROOT = Path(__file__).resolve().parents[2]


def test_alert_kinds_exact_founder_set():
    assert list(ALERT_KINDS) == [
        "OPPORTUNITY_READY",
        "POSTURE_CHANGE",
        "DATA_TRUST_DEGRADED",
        "REGIME_TRANSITION",
        "INVALIDATION",
        "SHADOW_CLOSED",
        "PROVIDER_DEGRADED",
        "MARKET_ANOMALY",
        "MAJOR_RISK",
    ]
    assert ALERT_KIND_LABELS["OPPORTUNITY_READY"] == "Opportunity READY"
    assert ALERT_KIND_LABELS["DATA_TRUST_DEGRADED"] == "Data Trust degraded"
    assert ALERT_KIND_LABELS["SHADOW_CLOSED"] == "Shadow closed"


def test_required_fields_include_honesty_metadata():
    assert list(REQUIRED_FIELDS) == [
        "kind",
        "source",
        "as_of",
        "freshness",
        "data_class",
        "decision_id",
        "reason",
        "severity",
        "public_safe",
    ]


def test_fixture_catalog_valid_and_public_safe():
    rows = fixture_alert_catalog()
    assert len(rows) == len(ALERT_KINDS)
    for row in rows:
        assert row["public_safe"] is True
        assert row["read_only"] is True
        assert row["actionable_trade"] is False
        result = validate_alert_envelope(row)
        assert result["ok"] is True, result


def test_hype_phrases_banned():
    assert "already ordered" in HYPE_PHRASES
    assert "guaranteed profit" in HYPE_PHRASES
    try:
        assert_no_hype_phrases("Position already ordered with guaranteed profit")
        raise AssertionError("expected hype ban")
    except HardBanViolation:
        pass


def test_build_live_readonly_requires_honest_freshness():
    alert = build_readonly_alert(
        kind="POSTURE_CHANGE",
        source="probe://live",
        reason="posture_changed",
        severity="MEDIUM",
        freshness="FRESH",
        data_class="LIVE_READ_ONLY",
        title="Posture updated",
        body="Public posture changed to WAIT.",
        decision_id="dec_live_1",
    )
    payload = alert.to_dict()
    assert payload["data_class"] == "LIVE_READ_ONLY"
    assert payload["public_safe"] is True


def test_contract_guarantees_zero_execution():
    contract = build_alert_engine_contract()
    g = contract["guarantees"]
    assert g["execution_control_count"] == 0
    assert g["exchange_write_capability"] == 0
    assert g["member_execution_control_count"] == 0
    assert g["fabricated_live_alerts"] == 0
    assert g["unavailable_as_zero"] == 0
    assert g["stale_without_indicator"] == 0


def test_web_and_mobile_mirrors_exist():
    web = ROOT / "frontend" / "src" / "member" / "alerts" / "alertEngineContract.ts"
    mobile = ROOT / "mobile" / "nexus_notify_prototypes" / "lib" / "src" / "pub18_alert_engine.dart"
    assert web.is_file()
    assert mobile.is_file()
    web_text = web.read_text(encoding="utf-8")
    mobile_text = mobile.read_text(encoding="utf-8")
    for kind in ALERT_KINDS:
        assert kind in web_text
        assert kind in mobile_text


def test_three_passes_gate():
    result = run_three_passes(ROOT)
    assert result["ok"] is True, result
    assert result["private_core_import_count"] == 0
    assert result["private_field_leak_count"] == 0
    assert result["exchange_controls"] == 0
    assert result["fabricated_live_values"] == 0
    assert result["unavailable_as_zero"] == 0
    assert result["stale_without_indicator"] == 0
    assert result["member_execution_control_count"] == 0
