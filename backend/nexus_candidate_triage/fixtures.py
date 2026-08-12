"""Synthetic research bundle fixtures for V14-H Candidate Triage.

Evidence class: FIXTURE_AND_DEVELOPMENT_ONLY.
Not real strategy candidates. Never qualify / promote / demo-ready.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from backend.nexus_candidate_triage.constants import EVIDENCE_CLASS, SCHEMA_ID


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _mechanism(semantic_id: str, family: str) -> dict[str, Any]:
    return {
        "mechanism_semantic_id": semantic_id,
        "mechanism_family": family,
        "economic_rationale": f"fixture_rationale_{family}",
        "required_data": ["AGGRESSIVE_TRADE_FLOW", "TOP_OF_BOOK"],
        "pit_semantics": "exchange_timestamp_and_receive_timestamp_le_as_of_ms",
        "entry_hypothesis": f"fixture_entry_{semantic_id}",
        "exit_hypothesis": f"fixture_exit_{semantic_id}",
        "failure_hypothesis": f"fixture_failure_{semantic_id}",
        "cost_sensitivity": "high",
        "market_capacity_assumptions": "thin_fixture_capacity",
        "invalidating_conditions": ["future_data", "cost_destruction", "regime_flip"],
        "deterministic": True,
        "fixture_only": True,
    }


def _base_candidate(
    *,
    candidate_id: str,
    mechanism_semantic_id: str,
    mechanism_family: str,
    feature_ids: list[str],
    symbols: list[str],
    as_of_ms: int,
    sample_n: int,
    data_quality_ok: bool,
    pit_ok: bool,
    gross_expectancy: float,
    net_expectancy: float,
    cost_destroyed: bool,
    regime_fragile: bool,
    robustness_label: str,
    rejected: bool,
    promising: bool,
) -> dict[str, Any]:
    interval = {
        "start_ms": as_of_ms - 60 * 86_400_000,
        "end_ms": as_of_ms - 30 * 86_400_000,
        "category": "development_only",
    }
    body = {
        "candidate_id": candidate_id,
        "mechanism": _mechanism(mechanism_semantic_id, mechanism_family),
        "feature_ids": feature_ids,
        "universe_symbols": symbols,
        "development_interval": interval,
        "sample_n": sample_n,
        "data_quality_ok": data_quality_ok,
        "pit_ok": pit_ok,
        "cost_sensitivity": {
            "gross_expectancy": gross_expectancy,
            "net_expectancy": net_expectancy,
            "cost_destroyed": cost_destroyed,
            "break_even_cost": abs(gross_expectancy) * 0.5,
            "fragility_score": 0.9 if cost_destroyed else 0.2,
            "canonical_cost_authority_consumed": True,
            "fixture_only": True,
        },
        "robustness": {
            "label": robustness_label,
            "bootstrap_stable": robustness_label == "DEVELOPMENT_ROBUST",
            "regime_stable": not regime_fragile,
            "sample_sufficient": sample_n >= 200,
            "multiple_testing_rejected": rejected and robustness_label == "MULTIPLE_TESTING_REJECTED",
            "fixture_only": True,
        },
        "regime": {
            "fragile": regime_fragile,
            "regimes_tested": ["vol_high", "liq_thin", "funding_stress"],
            "fixture_only": True,
        },
        "signals": {
            "rejected": rejected,
            "promising": promising,
            "needs_review": (not promising) and (not rejected) and (not cost_destroyed),
        },
        "qualified": False,
        "selected": False,
        "promoted": False,
        "demo_ready": False,
        "oos_touched": False,
        "formal_walk_forward_executed": False,
        "fixture_only": True,
        "evidence_class": EVIDENCE_CLASS,
        "as_of_ms": as_of_ms,
    }
    body["candidate_checksum"] = _sha(
        {
            "candidate_id": candidate_id,
            "mechanism_semantic_id": mechanism_semantic_id,
            "feature_ids": feature_ids,
            "symbols": symbols,
            "interval": interval,
            "sample_n": sample_n,
            "gross": gross_expectancy,
            "net": net_expectancy,
        }
    )
    return body


def build_synthetic_research_bundle(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, Any]:
    """Seven fixture candidates — one covering each allowed triage outcome path."""
    features_common = [
        "aggressive_buy_sell_imbalance",
        "trade_intensity",
        "price_impact",
    ]
    symbols_ok = ["SYNTHUSDT", "FIXTUREBTCUSDT"]
    candidates = [
        _base_candidate(
            candidate_id="SYN_V14H_DATA_001",
            mechanism_semantic_id="MECH_ORDER_FLOW_IMBALANCE_V4",
            mechanism_family="order_flow_imbalance",
            feature_ids=features_common,
            symbols=symbols_ok,
            as_of_ms=as_of_ms,
            sample_n=400,
            data_quality_ok=False,
            pit_ok=False,
            gross_expectancy=0.4,
            net_expectancy=0.1,
            cost_destroyed=False,
            regime_fragile=False,
            robustness_label="DATA_QUALITY_BLOCKED",
            rejected=False,
            promising=False,
        ),
        _base_candidate(
            candidate_id="SYN_V14H_SAMPLE_002",
            mechanism_semantic_id="MECH_SPREAD_SHOCK_V4",
            mechanism_family="spread_shock",
            feature_ids=features_common,
            symbols=symbols_ok,
            as_of_ms=as_of_ms,
            sample_n=40,
            data_quality_ok=True,
            pit_ok=True,
            gross_expectancy=0.5,
            net_expectancy=0.2,
            cost_destroyed=False,
            regime_fragile=False,
            robustness_label="INSUFFICIENT_SAMPLE",
            rejected=False,
            promising=False,
        ),
        _base_candidate(
            candidate_id="SYN_V14H_COST_003",
            mechanism_semantic_id="MECH_AGGRESSION_PERSISTENCE_V4",
            mechanism_family="aggression_persistence",
            feature_ids=features_common,
            symbols=symbols_ok,
            as_of_ms=as_of_ms,
            sample_n=500,
            data_quality_ok=True,
            pit_ok=True,
            gross_expectancy=0.8,
            net_expectancy=-0.3,
            cost_destroyed=True,
            regime_fragile=False,
            robustness_label="COST_DESTROYED",
            rejected=False,
            promising=False,
        ),
        _base_candidate(
            candidate_id="SYN_V14H_REGIME_004",
            mechanism_semantic_id="MECH_REGIME_MEAN_REVERSION_V4",
            mechanism_family="regime_conditioned_mean_reversion",
            feature_ids=features_common,
            symbols=symbols_ok,
            as_of_ms=as_of_ms,
            sample_n=350,
            data_quality_ok=True,
            pit_ok=True,
            gross_expectancy=0.45,
            net_expectancy=0.15,
            cost_destroyed=False,
            regime_fragile=True,
            robustness_label="DEVELOPMENT_FRAGILE",
            rejected=False,
            promising=False,
        ),
        _base_candidate(
            candidate_id="SYN_V14H_REJECT_005",
            mechanism_semantic_id="MECH_FAILED_BREAKOUT_V4",
            mechanism_family="failed_breakout",
            feature_ids=features_common,
            symbols=symbols_ok,
            as_of_ms=as_of_ms,
            sample_n=300,
            data_quality_ok=True,
            pit_ok=True,
            gross_expectancy=-0.2,
            net_expectancy=-0.5,
            cost_destroyed=False,
            regime_fragile=False,
            robustness_label="MULTIPLE_TESTING_REJECTED",
            rejected=True,
            promising=False,
        ),
        _base_candidate(
            candidate_id="SYN_V14H_REVIEW_006",
            mechanism_semantic_id="MECH_ABSORPTION_V4",
            mechanism_family="absorption",
            feature_ids=features_common,
            symbols=symbols_ok,
            as_of_ms=as_of_ms,
            sample_n=280,
            data_quality_ok=True,
            pit_ok=True,
            gross_expectancy=0.35,
            net_expectancy=0.05,
            cost_destroyed=False,
            regime_fragile=False,
            robustness_label="DEVELOPMENT_FRAGILE",
            rejected=False,
            promising=False,
        ),
        _base_candidate(
            candidate_id="SYN_V14H_PROMISING_007",
            mechanism_semantic_id="MECH_LIQUIDITY_WITHDRAWAL_V4",
            mechanism_family="liquidity_withdrawal",
            feature_ids=features_common,
            symbols=symbols_ok,
            as_of_ms=as_of_ms,
            sample_n=600,
            data_quality_ok=True,
            pit_ok=True,
            gross_expectancy=0.7,
            net_expectancy=0.25,
            cost_destroyed=False,
            regime_fragile=False,
            robustness_label="DEVELOPMENT_ROBUST",
            rejected=False,
            promising=True,
        ),
    ]
    bundle = {
        "schema": SCHEMA_ID,
        "bundle_kind": "V14_H_RESEARCH_INPUT_BUNDLE",
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


def clone_bundle(bundle: dict[str, Any] | None = None, *, as_of_ms: int | None = None) -> dict[str, Any]:
    src = deepcopy(bundle) if bundle is not None else build_synthetic_research_bundle()
    if as_of_ms is not None:
        src["as_of_ms"] = as_of_ms
        for c in src.get("candidates") or []:
            c["as_of_ms"] = as_of_ms
    return src
