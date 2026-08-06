"""Synthetic fixtures for V18-D Live Opportunity Pipeline E2E."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_live_opportunity_pipeline.constants import AS_OF_MS_DEFAULT, DEFAULT_MARKET


def _trust_inputs(**overrides: Any) -> dict[str, Any]:
    payload = {
        "case_id": "PIPELINE_TRUSTED",
        "symbol": "BTCUSDT",
        "source_id": "fixture_pipeline",
        "freshness": 0.95,
        "completeness": 0.97,
        "cross_source_agreement": 0.92,
        "schema_validity": 1.0,
        "timestamp_integrity": 1.0,
        "revision_uncertainty": 0.05,
        "license_status": "APPROVED_PUBLIC",
        "market_coverage": 0.90,
        "microstructure_availability": 0.88,
        "anomaly_rate": 0.02,
        "ai_confidence": 0.80,
        "availability": True,
        "notes": "pipeline_baseline",
    }
    payload.update(overrides)
    return payload


def _abstention_inputs(**overrides: Any) -> dict[str, Any]:
    payload = {
        "case_id": "PIPELINE_ALLOW",
        "symbol": "BTCUSDT",
        "provider_status": "OK",
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
        "notes": "pipeline_baseline",
    }
    payload.update(overrides)
    return payload


def fixture_case_catalog() -> list[dict[str, Any]]:
    """Deterministic cases covering decision enum + dominance rules."""
    base = {
        "as_of_ms": AS_OF_MS_DEFAULT,
        "market": DEFAULT_MARKET,
        "regime_scenario": "strong_bull",
        "execution_cost_bps": 8.0,
        "liquidity_score": 0.82,
        "historical_stability": 0.75,
        "portfolio_exposure": 0.20,
        "open_position_side": None,
        "risk_gate_allow": True,
        "risk_gate_reason": "PASS",
        "ai_confidence": 0.80,
        "ai_attempt_override_trust": False,
        "ai_attempt_override_risk": False,
        "force_symbols": None,
    }
    return [
        {
            **deepcopy(base),
            "case_id": "LONG_HEALTHY",
            "symbol": "BTCUSDT",
            "expect_decision_in": ("LONG", "WAIT", "ABSTAIN"),
            "trust": _trust_inputs(symbol="BTCUSDT", ai_confidence=0.80),
            "abstention": _abstention_inputs(symbol="BTCUSDT"),
        },
        {
            **deepcopy(base),
            "case_id": "SHORT_BEAR_TREND",
            "symbol": "ETHUSDT",
            "regime_scenario": "strong_bear",
            "expect_decision_in": ("SHORT", "WAIT", "REDUCE", "ABSTAIN"),
            "trust": _trust_inputs(symbol="ETHUSDT", case_id="PIPELINE_TRUSTED_ETH"),
            "abstention": _abstention_inputs(symbol="ETHUSDT"),
        },
        {
            **deepcopy(base),
            "case_id": "WAIT_COST_INFEASIBLE",
            "symbol": "BTCUSDT",
            "execution_cost_bps": 55.0,
            "expect_decision_in": ("WAIT", "ABSTAIN", "BLOCK"),
            "trust": _trust_inputs(),
            "abstention": _abstention_inputs(),
        },
        {
            **deepcopy(base),
            "case_id": "REDUCE_OPEN_POSITION_STRESS",
            "symbol": "BTCUSDT",
            "regime_scenario": "liquidity_stress",
            "open_position_side": "LONG",
            "portfolio_exposure": 0.80,
            "expect_decision_in": ("REDUCE", "WAIT", "ABSTAIN", "BLOCK"),
            "trust": _trust_inputs(freshness=0.70),
            "abstention": _abstention_inputs(
                data_freshness_sec=40.0,
                similarity_coverage=0.50,
            ),
        },
        {
            **deepcopy(base),
            "case_id": "ABSTAIN_UNCERTAINTY",
            "symbol": "BTCUSDT",
            "regime_scenario": "mixed",
            "expect_decision_in": ("ABSTAIN", "WAIT", "BLOCK"),
            "trust": _trust_inputs(freshness=0.75, completeness=0.80),
            "abstention": _abstention_inputs(
                case_id="PIPELINE_ABSTAIN",
                model_agreement=0.95,
                historical_agreement=0.40,
                regime_agreement=0.42,
                stated_confidence=0.99,
            ),
        },
        {
            **deepcopy(base),
            "case_id": "BLOCK_TRUST_DOMINANCE_AI99",
            "symbol": "BTCUSDT",
            "ai_confidence": 0.99,
            "ai_attempt_override_trust": True,
            "expect_decision_in": ("BLOCK", "ABSTAIN", "WAIT"),
            "trust": _trust_inputs(
                case_id="DOMINANCE_DEGRADED_AI99",
                timestamp_integrity=0.50,
                ai_confidence=0.99,
            ),
            "abstention": _abstention_inputs(stated_confidence=0.99),
        },
        {
            **deepcopy(base),
            "case_id": "BLOCK_RISK_GATE",
            "symbol": "BTCUSDT",
            "risk_gate_allow": False,
            "risk_gate_reason": "MAX_DRAWDOWN_BUDGET",
            "ai_attempt_override_risk": True,
            "ai_confidence": 0.99,
            "expect_decision_in": ("ABSTAIN", "BLOCK", "REDUCE", "WAIT"),
            "trust": _trust_inputs(ai_confidence=0.99),
            "abstention": _abstention_inputs(stated_confidence=0.99, risk_agreement=0.95),
        },
        {
            **deepcopy(base),
            "case_id": "BLOCK_STALE_LICENSE",
            "symbol": "BTCUSDT",
            "expect_decision_in": ("BLOCK",),
            "trust": _trust_inputs(
                case_id="LICENSE_BLOCKED",
                license_status="LICENSE_REVIEW_REQUIRED",
                ai_confidence=0.99,
            ),
            "abstention": _abstention_inputs(stated_confidence=0.99),
        },
    ]
