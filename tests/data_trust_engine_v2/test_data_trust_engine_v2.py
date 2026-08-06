"""Tests for V17-F Data Quality and Trust Engine V2."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_data_trust_engine_v2.constants import (
    DOMINANCE_TRUST_STATUSES,
    GATE_ACTIONS,
    HARD_BANS,
    LICENSE_BLOCKING_STATUSES,
    REQUIRED_INPUT_KEYS,
    TRUST_STATUSES,
)
from backend.nexus_data_trust_engine_v2.engine import (
    apply_ai_suggestion,
    evaluate_raw,
)
from backend.nexus_data_trust_engine_v2.fixtures import (
    _base,
    expected_trust_status,
    fixture_catalog,
)
from backend.nexus_data_trust_engine_v2.hard_bans import (
    HardBanViolation,
    assert_no_status_json_write,
    hard_ban_probe_matrix,
    scan_owned_paths_for_banned_claims,
)
from backend.nexus_data_trust_engine_v2.parser import ParseFailure, parse_trust_inputs


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_required_inputs_cover_founder_channels() -> None:
    for key in (
        "freshness",
        "completeness",
        "cross_source_agreement",
        "schema_validity",
        "timestamp_integrity",
        "revision_uncertainty",
        "license_status",
        "market_coverage",
        "microstructure_availability",
        "anomaly_rate",
    ):
        assert key in REQUIRED_INPUT_KEYS


def test_trust_status_ladder() -> None:
    assert TRUST_STATUSES == (
        "TRUSTED",
        "USABLE_WITH_LIMITS",
        "DEGRADED",
        "STALE",
        "CONFLICTED",
        "LICENSE_BLOCKED",
        "UNAVAILABLE",
    )


def test_gate_actions_include_wait_abstain_block() -> None:
    for action in ("WAIT", "ABSTAIN", "BLOCK"):
        assert action in GATE_ACTIONS


def test_healthy_trusted() -> None:
    result = evaluate_raw(_base())
    assert result["trust_status"] == "TRUSTED"
    assert result["gate_action"] == "ALLOW"
    assert result["execution_allowed"] is True
    assert result["fail_closed"] is True
    assert result["license_blocked"] is False


def test_dominance_degraded_blocks_even_if_ai_99() -> None:
    """Founder rule: Data Trust dominates AI confidence.

    If DEGRADED then WAIT/ABSTAIN/BLOCK even when AI confidence is 99%.
    """
    result = evaluate_raw(
        _base(
            schema_validity=0.55,
            ai_confidence=0.99,
            case_id="DOMINANCE_DEGRADED_AI99",
        )
    )
    assert result["trust_status"] == "DEGRADED"
    assert result["trust_status"] in DOMINANCE_TRUST_STATUSES
    assert result["gate_action"] in {"WAIT", "ABSTAIN", "BLOCK"}
    assert result["execution_allowed"] is False
    assert result["dominance_applied"] is True
    codes = {r["code"] for r in result["reasons"]}
    assert "TRUST_DOMINATES_AI_CONFIDENCE" in codes

    # AI cannot reopen to ALLOW.
    after = apply_ai_suggestion(
        result,
        {
            "trust_status": "TRUSTED",
            "gate_action": "ALLOW",
            "execution_allowed": True,
            "ai_confidence": 0.99,
        },
    )
    assert after["trust_status"] == "DEGRADED"
    assert after["gate_action"] in {"WAIT", "ABSTAIN", "BLOCK"}
    assert after["execution_allowed"] is False
    assert after["ai_override_applied"] is False
    assert after["ai_override_attempted"] is True


def test_license_blocked_review_required() -> None:
    result = evaluate_raw(
        _base(
            license_status="LICENSE_REVIEW_REQUIRED",
            ai_confidence=0.99,
            case_id="LICENSE_BLOCKED_REVIEW",
        )
    )
    assert result["trust_status"] == "LICENSE_BLOCKED"
    assert result["license_blocked"] is True
    assert result["gate_action"] == "BLOCK"
    assert result["execution_allowed"] is False
    codes = {r["code"] for r in result["reasons"]}
    assert "LICENSE_BLOCKED" in codes
    assert result["dominance_applied"] is True


def test_license_blocked_unknown_not_trusted() -> None:
    result = evaluate_raw(
        _base(license_status="UNKNOWN", ai_confidence=0.99)
    )
    assert result["trust_status"] == "LICENSE_BLOCKED"
    assert result["license_blocked"] is True
    assert result["gate_action"] == "BLOCK"
    assert "UNKNOWN" in LICENSE_BLOCKING_STATUSES


def test_stale_conflicted_unavailable() -> None:
    stale = evaluate_raw(_base(freshness=0.15, ai_confidence=0.99))
    assert stale["trust_status"] == "STALE"
    assert stale["gate_action"] == "BLOCK"
    assert stale["execution_allowed"] is False

    conflicted = evaluate_raw(
        _base(cross_source_agreement=0.25, ai_confidence=0.99)
    )
    assert conflicted["trust_status"] == "CONFLICTED"
    assert conflicted["gate_action"] == "ABSTAIN"
    assert conflicted["execution_allowed"] is False

    unavailable = evaluate_raw(_base(completeness=0.05, ai_confidence=0.99))
    assert unavailable["trust_status"] == "UNAVAILABLE"
    assert unavailable["gate_action"] == "BLOCK"


def test_usable_with_limits() -> None:
    result = evaluate_raw(_base(freshness=0.70))
    assert result["trust_status"] == "USABLE_WITH_LIMITS"
    assert result["gate_action"] == "ALLOW_REDUCED"
    assert result["execution_allowed"] is True
    assert result["size_multiplier"] < 1.0


def test_missing_inputs_never_fail_open() -> None:
    with pytest.raises(ParseFailure):
        parse_trust_inputs({"ai_confidence": 1.0})
    result = evaluate_raw({"ai_confidence": 1.0, "freshness": 1.0})
    assert result["trust_status"] == "UNAVAILABLE"
    assert result["gate_action"] == "BLOCK"
    assert result["execution_allowed"] is False
    assert result["parse_failure"] is True


def test_fixture_catalog_matches_expected() -> None:
    for case in fixture_catalog():
        expected = expected_trust_status(case)
        result = evaluate_raw(case)
        if expected is not None:
            assert result["trust_status"] == expected, case["case_id"]
        if result["trust_status"] in DOMINANCE_TRUST_STATUSES:
            assert result["gate_action"] in {"WAIT", "ABSTAIN", "BLOCK"}
            assert result["execution_allowed"] is False


def test_hard_bans_and_no_status_json() -> None:
    assert "no_ai_confidence_override_of_degraded_trust" in HARD_BANS
    assert "no_acceleration_report_edit" in HARD_BANS
    assert "no_exchange_write" in HARD_BANS
    assert "no_pr26_merge" in HARD_BANS
    matrix = hard_ban_probe_matrix()
    assert matrix["all_refused"] is True
    assert matrix["env_guard"]["ok"] is True
    with pytest.raises(HardBanViolation):
        assert_no_status_json_write("v17_f_status.json")
    scan = scan_owned_paths_for_banned_claims(REPO_ROOT)
    assert scan["ok"] is True, scan["hits"]
