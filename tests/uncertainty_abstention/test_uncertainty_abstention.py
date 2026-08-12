"""Tests for V16-G Uncertainty and Abstention Engine."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_uncertainty_abstention.adversarial import run_fail_open_attacks
from backend.nexus_uncertainty_abstention.constants import (
    AGREEMENT_CHANNELS,
    HARD_BANS,
    PASS_COUNT,
    REQUIRED_INPUT_KEYS,
    VERDICTS,
)
from backend.nexus_uncertainty_abstention.engine import (
    apply_ai_suggestion,
    evaluate_inputs,
    evaluate_raw,
)
from backend.nexus_uncertainty_abstention.fixtures import (
    expected_verdict,
    fixture_catalog,
    _base,
)
from backend.nexus_uncertainty_abstention.hard_bans import (
    HardBanViolation,
    assert_no_status_json_write,
    hard_ban_probe_matrix,
    scan_owned_paths_for_banned_claims,
)
from backend.nexus_uncertainty_abstention.parser import ParseFailure, parse_provider_payload
from backend.nexus_uncertainty_abstention.three_pass import run_pass, run_three_passes


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_required_input_keys_cover_founder_channels() -> None:
    for ch in AGREEMENT_CHANNELS:
        assert ch in REQUIRED_INPUT_KEYS
    for ch in (
        "calibration_reliability",
        "similarity_coverage",
        "prediction_interval_width",
        "data_freshness_sec",
        "stated_confidence",
        "provider_status",
    ):
        assert ch in REQUIRED_INPUT_KEYS


def test_verdict_ladder() -> None:
    assert VERDICTS == (
        "ALLOW",
        "ALLOW_REDUCED",
        "WAIT",
        "ABSTAIN",
        "BLOCK",
    )


def test_healthy_allow() -> None:
    result = evaluate_raw(_base())
    assert result["verdict"] == "ALLOW"
    assert result["execution_allowed"] is True
    assert result["size_multiplier"] == 1.0
    assert result["fail_closed"] is True


def test_consensus_cannot_override_bad_data() -> None:
    result = evaluate_raw(
        _base(
            model_agreement=0.99,
            historical_agreement=0.99,
            regime_agreement=0.99,
            execution_agreement=0.99,
            risk_agreement=0.99,
            data_agreement=0.45,
            stated_confidence=0.99,
        )
    )
    assert result["verdict"] in {"ABSTAIN", "BLOCK"}
    assert result["bad_data_blocked"] is True
    assert result["execution_allowed"] is False
    codes = {r["code"] for r in result["reasons"]}
    assert "BAD_DATA_NOT_OVERRIDABLE" in codes or "CONSENSUS_OVERRIDE_BLOCKED" in codes


def test_high_confidence_low_calibration_degrades() -> None:
    degraded = evaluate_raw(
        _base(stated_confidence=0.95, calibration_reliability=0.55)
    )
    assert degraded["verdict"] == "ALLOW_REDUCED"
    assert degraded["size_multiplier"] < 1.0

    abstained = evaluate_raw(
        _base(stated_confidence=0.98, calibration_reliability=0.25)
    )
    assert abstained["verdict"] == "ABSTAIN"
    assert abstained["execution_allowed"] is False


def test_low_coverage_shows_uncertainty() -> None:
    reduced = evaluate_raw(_base(similarity_coverage=0.45))
    assert reduced["verdict"] == "ALLOW_REDUCED"
    assert reduced["uncertainty_score"] > 0.0

    abstained = evaluate_raw(_base(similarity_coverage=0.10))
    assert abstained["verdict"] == "ABSTAIN"


def test_provider_failure_invalid_json_stale_contradiction() -> None:
    assert evaluate_raw(_base(provider_status="FAILED"))["verdict"] == "BLOCK"
    assert evaluate_raw(_base(provider_status="TIMEOUT"))["verdict"] == "BLOCK"
    assert evaluate_raw("{bad")["verdict"] == "BLOCK"
    assert evaluate_raw(None)["verdict"] == "BLOCK"
    stale = evaluate_raw(_base(data_freshness_sec=200.0))
    assert stale["verdict"] == "BLOCK"
    contrad = evaluate_raw(
        _base(
            model_agreement=0.95,
            historical_agreement=0.40,
            regime_agreement=0.41,
        )
    )
    assert contrad["verdict"] == "ABSTAIN"
    assert contrad["contradiction"] is True


def test_missing_inputs_never_fail_open() -> None:
    with pytest.raises(ParseFailure):
        parse_provider_payload({"provider_status": "OK"})
    result = evaluate_raw({"provider_status": "OK", "stated_confidence": 1.0})
    assert result["verdict"] == "BLOCK"
    assert result["execution_allowed"] is False
    assert result["parse_failure"] is True


def test_ai_cannot_override_verdict() -> None:
    blocked = evaluate_raw(_base(provider_status="FAILED"))
    after = apply_ai_suggestion(
        blocked,
        {"verdict": "ALLOW", "execution_allowed": True, "size_multiplier": 1.0},
    )
    assert after["verdict"] == "BLOCK"
    assert after["ai_override_applied"] is False
    assert after["ai_override_attempted"] is True
    assert after["execution_allowed"] is False


def test_status_json_hard_banned() -> None:
    with pytest.raises(HardBanViolation):
        assert_no_status_json_write("foo_status.json")
    with pytest.raises(HardBanViolation):
        assert_no_status_json_write("lane_report.json")


def test_fixture_catalog_matches_expected() -> None:
    for case in fixture_catalog():
        if "raw" in case:
            got = evaluate_raw(case["raw"])["verdict"]
        else:
            got = evaluate_raw(case)["verdict"]
        assert got == expected_verdict(case["case_id"]), case["case_id"]


def test_fail_open_attacks_all_blocked() -> None:
    review = run_fail_open_attacks()
    assert review["all_fail_open_blocked"] is True
    assert review["hard_ban_all_refused"] is True
    assert review["pass"] is True
    assert review["attack_count"] >= 10


def test_hard_ban_matrix() -> None:
    matrix = hard_ban_probe_matrix()
    assert matrix["all_refused"] is True
    assert set(HARD_BANS).issubset(set(matrix["hard_bans"]))


def test_three_passes() -> None:
    assert PASS_COUNT == 3
    campaign = run_three_passes(repo_root=REPO_ROOT)
    assert campaign["pass_count"] == 3
    assert campaign["all_passes_ok"] is True
    assert campaign["deterministic"] is True
    assert campaign["final_status"] == "PASS"
    assert campaign["status_json_written"] is False
    assert campaign["lane_report_written"] is False
    assert campaign["banned_claim_scan"]["ok"] is True
    for p in campaign["passes"]:
        assert p["pass_ok"] is True
        assert p["ai_override_applied_count"] == 0
        assert p["allow_on_bad_data_count"] == 0
        assert p["mismatch_count"] == 0


def test_single_pass_idempotent() -> None:
    a = run_pass(1)
    b = run_pass(2)
    c = run_pass(3)
    assert a["code_checksum"] == b["code_checksum"] == c["code_checksum"]
    assert a["verdict_histogram"] == b["verdict_histogram"] == c["verdict_histogram"]


def test_evaluate_inputs_direct() -> None:
    inputs = parse_provider_payload(_base())
    result = evaluate_inputs(inputs)
    assert result["verdict"] == "ALLOW"
    assert result["schema"].startswith("FOUNDER_V16_G")


def test_owned_path_claim_scan_clean() -> None:
    scan = scan_owned_paths_for_banned_claims(REPO_ROOT)
    assert scan["ok"] is True
    assert scan["hits"] == []
