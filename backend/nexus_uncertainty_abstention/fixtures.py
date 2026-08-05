"""Synthetic fixtures for V16-G Uncertainty and Abstention Engine."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_uncertainty_abstention.constants import PROVIDER_OK, RANDOM_SEED


def _base(**overrides: Any) -> dict[str, Any]:
    payload = {
        "case_id": "BASE_ALLOW",
        "symbol": "BTCUSDT",
        "provider_status": PROVIDER_OK,
        "model_agreement": 0.92,
        "data_agreement": 0.91,
        "historical_agreement": 0.88,
        "regime_agreement": 0.90,
        "execution_agreement": 0.87,
        "risk_agreement": 0.89,
        "calibration_reliability": 0.85,
        "similarity_coverage": 0.78,
        "prediction_interval_width": 0.18,
        "data_freshness_sec": 8.0,
        "stated_confidence": 0.75,
        "notes": "healthy_baseline",
    }
    payload.update(overrides)
    return payload


def fixture_catalog() -> list[dict[str, Any]]:
    """Deterministic catalog covering all founder-required behaviors."""
    cases = [
        _base(case_id="ALLOW_HEALTHY"),
        _base(
            case_id="ALLOW_REDUCED_PARTIAL_AGREEMENT",
            model_agreement=0.72,
            historical_agreement=0.70,
            regime_agreement=0.71,
            execution_agreement=0.69,
            risk_agreement=0.70,
            notes="partial_agreement_reduced",
        ),
        _base(
            case_id="ALLOW_REDUCED_LOW_COVERAGE",
            similarity_coverage=0.45,
            notes="low_coverage_uncertainty",
        ),
        _base(
            case_id="ALLOW_REDUCED_HIGH_CONF_LOW_CAL",
            stated_confidence=0.95,
            calibration_reliability=0.55,
            notes="high_conf_low_cal_must_degrade",
        ),
        _base(
            case_id="WAIT_FRESHNESS",
            data_freshness_sec=100.0,
            notes="freshness_wait_band",
        ),
        _base(
            case_id="WAIT_LOW_AGREEMENT",
            model_agreement=0.58,
            historical_agreement=0.55,
            regime_agreement=0.56,
            execution_agreement=0.54,
            risk_agreement=0.57,
            notes="agreement_wait_band",
        ),
        _base(
            case_id="ABSTAIN_CONTRADICTION",
            model_agreement=0.95,
            historical_agreement=0.40,
            regime_agreement=0.42,
            notes="model_historical_regime_contradiction",
        ),
        _base(
            case_id="ABSTAIN_LOW_COVERAGE",
            similarity_coverage=0.15,
            stated_confidence=0.90,
            notes="coverage_abstain",
        ),
        _base(
            case_id="ABSTAIN_HIGH_CONF_VERY_LOW_CAL",
            stated_confidence=0.98,
            calibration_reliability=0.25,
            notes="high_conf_very_low_cal_abstain",
        ),
        _base(
            case_id="ABSTAIN_BAD_DATA_DESPITE_CONSENSUS",
            model_agreement=0.99,
            historical_agreement=0.98,
            regime_agreement=0.97,
            execution_agreement=0.96,
            risk_agreement=0.95,
            data_agreement=0.45,
            notes="consensus_cannot_override_bad_data",
        ),
        _base(
            case_id="BLOCK_STALE",
            data_freshness_sec=180.0,
            notes="stale_evidence_block",
        ),
        _base(
            case_id="BLOCK_VERY_BAD_DATA",
            data_agreement=0.20,
            notes="catastrophic_data_quality",
        ),
        _base(
            case_id="BLOCK_PROVIDER_FAILED",
            provider_status="FAILED",
            notes="provider_failure",
        ),
        {
            "case_id": "BLOCK_INVALID_JSON",
            "raw": "{not-json",
            "notes": "invalid_json_payload",
        },
        _base(
            case_id="BLOCK_MISSING_INPUTS",
            # delete keys after copy
            notes="missing_inputs_fail_closed",
        ),
        _base(
            case_id="ALLOW_REDUCED_WIDE_INTERVAL",
            prediction_interval_width=0.50,
            notes="elevated_interval",
        ),
        _base(
            case_id="ABSTAIN_WIDE_INTERVAL",
            prediction_interval_width=0.85,
            notes="abstain_interval",
        ),
        _base(
            case_id="WAIT_RISK_EXEC_GAP",
            risk_agreement=0.95,
            execution_agreement=0.50,
            notes="risk_execution_disagreement",
        ),
    ]

    # Materialize missing-inputs attack case.
    for case in cases:
        if case.get("case_id") == "BLOCK_MISSING_INPUTS":
            case.pop("calibration_reliability", None)
            case.pop("similarity_coverage", None)

    # Determinism salt — unused numerically but documents seed binding.
    assert RANDOM_SEED == 20260806
    return cases


def expected_verdict(case_id: str) -> str:
    mapping = {
        "ALLOW_HEALTHY": "ALLOW",
        "ALLOW_REDUCED_PARTIAL_AGREEMENT": "ALLOW_REDUCED",
        "ALLOW_REDUCED_LOW_COVERAGE": "ALLOW_REDUCED",
        "ALLOW_REDUCED_HIGH_CONF_LOW_CAL": "ALLOW_REDUCED",
        "ALLOW_REDUCED_WIDE_INTERVAL": "ALLOW_REDUCED",
        "WAIT_FRESHNESS": "WAIT",
        "WAIT_LOW_AGREEMENT": "WAIT",
        "WAIT_RISK_EXEC_GAP": "WAIT",
        "ABSTAIN_CONTRADICTION": "ABSTAIN",
        "ABSTAIN_LOW_COVERAGE": "ABSTAIN",
        "ABSTAIN_HIGH_CONF_VERY_LOW_CAL": "ABSTAIN",
        "ABSTAIN_BAD_DATA_DESPITE_CONSENSUS": "ABSTAIN",
        "ABSTAIN_WIDE_INTERVAL": "ABSTAIN",
        "BLOCK_STALE": "BLOCK",
        "BLOCK_VERY_BAD_DATA": "BLOCK",
        "BLOCK_PROVIDER_FAILED": "BLOCK",
        "BLOCK_INVALID_JSON": "BLOCK",
        "BLOCK_MISSING_INPUTS": "BLOCK",
    }
    return mapping[case_id]


def clone_case(case: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(case)
