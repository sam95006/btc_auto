"""Synthetic development candidates for V15-E dossier builder.

Evidence class: FIXTURE_AND_DEVELOPMENT_ONLY.
Statuses capped at DEVELOPMENT_REVIEW / DEVELOPMENT_PROMISING_NOT_QUALIFIED.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from backend.nexus_candidate_dossier.constants import (
    CODE_SURFACE_DEFAULT,
    COST_VERSION_DEFAULT,
    EVIDENCE_CLASS,
    EXECUTION_VERSION_DEFAULT,
    FEATURE_VERSION_DEFAULT,
    PARAMETER_SURFACE_DEFAULT,
    RISK_VERSION_DEFAULT,
    SCHEMA_ID,
)


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _lineage(
    *,
    candidate_id: str,
    mechanism_semantic_id: str,
    symbols: list[str],
    as_of_ms: int,
    feature_ids: list[str],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    universe_payload = {
        "symbols": symbols,
        "as_of_ms": as_of_ms,
        "universe_class": "FIXTURE_DEVELOPMENT",
    }
    code_payload = {
        "surface": CODE_SURFACE_DEFAULT,
        "mechanism_semantic_id": mechanism_semantic_id,
        "candidate_id": candidate_id,
    }
    param_payload = {
        "surface": PARAMETER_SURFACE_DEFAULT,
        "parameters": parameters,
    }
    return {
        "data_lineage": {
            "source": "synthetic_fixture_bundle",
            "campaign_id": "syn_v15e_dev_bundle",
            "as_of_ms": as_of_ms,
            "pit_semantics": "exchange_timestamp_and_receive_timestamp_le_as_of_ms",
            "fixture_only": True,
        },
        "universe_checksum": _sha(universe_payload),
        "feature_version": FEATURE_VERSION_DEFAULT,
        "feature_ids": feature_ids,
        "code_checksum": _sha(code_payload),
        "parameter_checksum": _sha(param_payload),
        "cost_version": COST_VERSION_DEFAULT,
        "risk_version": RISK_VERSION_DEFAULT,
        "execution_version": EXECUTION_VERSION_DEFAULT,
    }


def _failed_siblings(seed: str) -> list[dict[str, Any]]:
    return [
        {
            "experiment_id": f"{seed}_SIB_FAIL_COST",
            "outcome": "COST_DESTROYED",
            "fixture_only": True,
            "reason": "net_expectancy_negative_under_canonical_cost",
        },
        {
            "experiment_id": f"{seed}_SIB_FAIL_REGIME",
            "outcome": "REGIME_FRAGILE",
            "fixture_only": True,
            "reason": "signal_collapsed_in_liq_thin_regime",
        },
        {
            "experiment_id": f"{seed}_SIB_FAIL_SAMPLE",
            "outcome": "INSUFFICIENT_SAMPLE",
            "fixture_only": True,
            "reason": "bootstrap_ci_unstable_below_min_n",
        },
    ]


def _base_candidate(
    *,
    candidate_id: str,
    mechanism_semantic_id: str,
    mechanism_family: str,
    economic_rationale: str,
    feature_ids: list[str],
    symbols: list[str],
    as_of_ms: int,
    sample_n: int,
    dossier_status: str,
    promising: bool,
    gross_expectancy: float,
    net_expectancy: float,
    parameters: dict[str, Any],
    multiple_testing_status: str,
    remaining_blockers: list[str],
) -> dict[str, Any]:
    intervals = [
        {
            "start_ms": as_of_ms - 90 * 86_400_000,
            "end_ms": as_of_ms - 60 * 86_400_000,
            "category": "development_only",
            "label": "dev_window_a",
        },
        {
            "start_ms": as_of_ms - 60 * 86_400_000,
            "end_ms": as_of_ms - 30 * 86_400_000,
            "category": "development_only",
            "label": "dev_window_b",
        },
    ]
    lineage = _lineage(
        candidate_id=candidate_id,
        mechanism_semantic_id=mechanism_semantic_id,
        symbols=symbols,
        as_of_ms=as_of_ms,
        feature_ids=feature_ids,
        parameters=parameters,
    )
    body = {
        "candidate_id": candidate_id,
        "dossier_status": dossier_status,
        "semantic_mechanism": {
            "mechanism_semantic_id": mechanism_semantic_id,
            "mechanism_family": mechanism_family,
            "deterministic": True,
            "fixture_only": True,
        },
        "economic_rationale": economic_rationale,
        **lineage,
        "development_intervals": intervals,
        "failed_sibling_experiments": _failed_siblings(candidate_id),
        "regime_breakdown": {
            "vol_high": {"sample_n": sample_n // 3, "net_expectancy": net_expectancy * 0.8},
            "liq_thin": {"sample_n": sample_n // 3, "net_expectancy": net_expectancy * 0.4},
            "funding_stress": {
                "sample_n": sample_n - 2 * (sample_n // 3),
                "net_expectancy": net_expectancy * 1.1,
            },
            "fragile": not promising,
            "fixture_only": True,
        },
        "symbol_breakdown": {
            sym: {
                "sample_n": sample_n // len(symbols),
                "gross_expectancy": gross_expectancy,
                "net_expectancy": net_expectancy,
            }
            for sym in symbols
        },
        "cost_breakdown": {
            "fees": 0.0004,
            "spread": 0.0002,
            "slippage": 0.0003,
            "impact": 0.0001,
            "funding": 0.00005,
            "gross_expectancy": gross_expectancy,
            "net_expectancy": net_expectancy,
            "cost_destroyed": net_expectancy < 0,
            "canonical_cost_authority_consumed": True,
            "fixture_only": True,
        },
        "capacity_assumptions": {
            "max_notional_usd": 25_000 if promising else 10_000,
            "max_participation_rate": 0.02,
            "liquidity_floor_usd": 500_000,
            "thin_market_block": True,
            "fixture_only": True,
        },
        "known_failure_conditions": [
            "future_data_leak",
            "cost_destruction",
            "regime_flip",
            "universe_checksum_mismatch",
            "sibling_cost_collapse",
        ],
        "multiple_testing_status": multiple_testing_status,
        "remaining_blockers": list(remaining_blockers),
        "sample_n": sample_n,
        "parameters": parameters,
        "qualified": False,
        "selected": False,
        "promoted": False,
        "demo_ready": False,
        "oos_touched": False,
        "formal_walk_forward_executed": False,
        "profitability_claim": False,
        "fixture_only": True,
        "evidence_class": EVIDENCE_CLASS,
        "as_of_ms": as_of_ms,
        "signals": {
            "promising": promising,
            "needs_review": not promising,
        },
    }
    body["candidate_checksum"] = _sha(
        {
            "candidate_id": candidate_id,
            "mechanism_semantic_id": mechanism_semantic_id,
            "universe_checksum": lineage["universe_checksum"],
            "code_checksum": lineage["code_checksum"],
            "parameter_checksum": lineage["parameter_checksum"],
            "feature_version": lineage["feature_version"],
            "cost_version": lineage["cost_version"],
            "intervals": intervals,
            "dossier_status": dossier_status,
        }
    )
    return body


def build_synthetic_dossier_inputs(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, Any]:
    """Two fixture candidates — one review, one promising-not-qualified."""
    features = [
        "aggressive_buy_sell_imbalance",
        "trade_intensity",
        "price_impact",
        "spread_shock_z",
    ]
    symbols = ["SYNTHUSDT", "FIXTUREBTCUSDT", "FIXTUREETHUSDT"]
    candidates = [
        _base_candidate(
            candidate_id="SYN_V15E_REVIEW_001",
            mechanism_semantic_id="MECH_ABSORPTION_V4",
            mechanism_family="absorption",
            economic_rationale=(
                "Fixture absorption hypothesis: transient liquidity absorption "
                "may produce short-horizon mean reversion under thin books."
            ),
            feature_ids=features,
            symbols=symbols,
            as_of_ms=as_of_ms,
            sample_n=320,
            dossier_status="DEVELOPMENT_REVIEW",
            promising=False,
            gross_expectancy=0.35,
            net_expectancy=0.05,
            parameters={"lookback_bars": 20, "entry_z": 1.5, "exit_z": 0.25},
            multiple_testing_status="PENDING_DEVELOPMENT_CORRECTION",
            remaining_blockers=[
                "formal_walk_forward_blocked",
                "oos_reservation_blocked",
                "multiple_testing_correction_incomplete",
                "capacity_stress_incomplete",
            ],
        ),
        _base_candidate(
            candidate_id="SYN_V15E_PROMISING_002",
            mechanism_semantic_id="MECH_LIQUIDITY_WITHDRAWAL_V4",
            mechanism_family="liquidity_withdrawal",
            economic_rationale=(
                "Fixture liquidity-withdrawal hypothesis: sudden top-of-book "
                "withdrawal may precede short-lived continuation in aggressive flow."
            ),
            feature_ids=features,
            symbols=symbols,
            as_of_ms=as_of_ms,
            sample_n=640,
            dossier_status="DEVELOPMENT_PROMISING_NOT_QUALIFIED",
            promising=True,
            gross_expectancy=0.7,
            net_expectancy=0.25,
            parameters={"lookback_bars": 12, "entry_z": 2.0, "exit_z": 0.5},
            multiple_testing_status="DEVELOPMENT_SURVIVED_FAMILYWISE_SCREEN",
            remaining_blockers=[
                "formal_walk_forward_blocked",
                "oos_reservation_blocked",
                "qualification_ready_forbidden",
                "strategy_promotion_banned",
            ],
        ),
    ]
    bundle = {
        "schema": SCHEMA_ID,
        "bundle_kind": "V15_E_DOSSIER_INPUT_BUNDLE",
        "evidence_class": EVIDENCE_CLASS,
        "fixture_only": True,
        "as_of_ms": as_of_ms,
        "candidates": candidates,
        "qualification_ready_count": 0,
        "formal_walk_forward_executed": False,
        "oos_touched": False,
        "selected_strategy": None,
        "promoted_strategy": None,
    }
    bundle["bundle_checksum"] = _sha(
        {
            "as_of_ms": as_of_ms,
            "ids": [c["candidate_id"] for c in candidates],
            "checksums": [c["candidate_checksum"] for c in candidates],
        }
    )
    return bundle


def clone_inputs(
    bundle: dict[str, Any] | None = None, *, as_of_ms: int | None = None
) -> dict[str, Any]:
    src = deepcopy(bundle) if bundle is not None else build_synthetic_dossier_inputs()
    if as_of_ms is not None:
        src["as_of_ms"] = as_of_ms
        for c in src.get("candidates") or []:
            c["as_of_ms"] = as_of_ms
    return src
