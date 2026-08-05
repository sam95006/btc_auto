"""Discovery output ingest for V13-F (synthetic / development fixtures only).

Connects Strategy Discovery (V13-C shaped) and Market Discovery (V13-D shaped)
outputs into blocked-only Qualification dry-run control. Never qualifies,
selects, or promotes candidates.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_qualification.dryrun_v13.checksums import sha_obj, stamp_all_checksums
from backend.nexus_qualification.dryrun_v13.constants import (
    ALLOWED_DISCOVERY_LABELS,
    DISCOVERY_BUNDLE_SCHEMA,
)

AS_OF_MS_DEFAULT = 1_700_000_000_000


def synthetic_market_discovery(*, as_of_ms: int = AS_OF_MS_DEFAULT) -> dict[str, Any]:
    """V13-D shaped universe discovery fixture (Point-in-Time, synthetic)."""
    eligible = [
        {
            "symbol": "SYNTHUSDT",
            "listing_timestamp_ms": as_of_ms - 365 * 86_400_000,
            "delisting_state": "active",
            "liquidity_ok": True,
            "data_completeness_ok": True,
            "staleness_ok": True,
            "fixture_only": True,
        },
        {
            "symbol": "SYNTHBTC",
            "listing_timestamp_ms": as_of_ms - 200 * 86_400_000,
            "delisting_state": "active",
            "liquidity_ok": True,
            "data_completeness_ok": True,
            "staleness_ok": True,
            "fixture_only": True,
        },
    ]
    rejected = [
        {
            "symbol": "FUTURELISTED",
            "rejection_reason": "listing_after_as_of",
            "listing_timestamp_ms": as_of_ms + 86_400_000,
            "fixture_only": True,
        }
    ]
    availability_ts = as_of_ms - 6 * 86_400_000
    retrieval_ts = as_of_ms - 5 * 86_400_000
    body = {
        "eligible_universe": eligible,
        "rejected_universe": rejected,
        "as_of_ms": as_of_ms,
        "availability_timestamp_ms": availability_ts,
        "retrieval_timestamp_ms": retrieval_ts,
        "real_market_data": False,
        "fixture_only": True,
    }
    body["universe_checksum"] = sha_obj(
        {
            "eligible": [e["symbol"] for e in eligible],
            "rejected": [r["symbol"] for r in rejected],
            "as_of_ms": as_of_ms,
            "availability_timestamp_ms": availability_ts,
        }
    )
    body["lineage"] = {
        "source": "synthetic_market_discovery_v13_f",
        "mode": "fixture_only",
        "pit_bound": True,
    }
    return body


def synthetic_strategy_discovery(*, as_of_ms: int = AS_OF_MS_DEFAULT) -> dict[str, Any]:
    """V13-C shaped strategy discovery factory outputs (development fixtures)."""
    candidates = [
        {
            "candidate_id": "SYN_V13F_DISC_001",
            "candidate_label": "synthetic_order_flow_imbalance",
            "semantic_mechanism_id": "order_flow_imbalance",
            "strategy_family": "ORDER_FLOW_IMBALANCE",
            "economic_mechanism": "aggressive_buy_sell_imbalance_response",
            "discovery_label": "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
            "required_data_capabilities": ["trades", "orderbook_l2_sanitized"],
            "eligible_symbol_profile": ["SYNTHUSDT"],
            "eligible_regimes": ["synthetic_trend", "synthetic_chop"],
            "parameter_source": "synthetic_discovery_factory_v3",
            "factory_version": "v3_synthetic_fixture",
            "cost_model_version": "founder-conservative-v1-1-fixture",
            "code_ref": "backend/nexus_qualification/dryrun_v13",
            "implementation_fingerprint": "synthetic_impl_ofi_v13f",
            "dataset_ref": "SYNTHETIC_DEV_DATASET_V13F",
            "dataset_lineage": {
                "dataset_id": "SYNTHETIC_DEV_DATASET_V13F",
                "source": "synthetic_fixture_generator",
                "real_market_data": False,
            },
            "development_interval": {
                "start_ms": as_of_ms - 60 * 86_400_000,
                "end_ms": as_of_ms - 30 * 86_400_000,
                "category": "development",
            },
            "parameters": {
                "lookback_bars": 24,
                "imbalance_threshold": 0.35,
                "fixture_marker": True,
            },
            "gross_result": None,
            "net_result": None,
            "trade_count": 0,
            "multiple_comparison_metadata": {"family_wise": True, "fixture": True},
            "failure_reasons": [],
            "qualified": False,
            "selected": False,
            "promoted": False,
            "fixture_only": True,
            "preregistration_timestamp": "2026-01-01T00:00:00Z",
            "as_of_ms": as_of_ms,
        },
        {
            "candidate_id": "SYN_V13F_DISC_002",
            "candidate_label": "synthetic_funding_dislocation",
            "semantic_mechanism_id": "funding_dislocation",
            "strategy_family": "FUNDING_DISLOCATION",
            "economic_mechanism": "funding_rate_dislocation_mean_reversion",
            "discovery_label": "RAW_EDGE_PRESENT_BUT_COST_DESTROYED",
            "required_data_capabilities": ["funding", "ohlcv_1h"],
            "eligible_symbol_profile": ["SYNTHBTC"],
            "eligible_regimes": ["synthetic_funding_stress"],
            "parameter_source": "synthetic_discovery_factory_v3",
            "factory_version": "v3_synthetic_fixture",
            "cost_model_version": "founder-conservative-v1-1-fixture",
            "code_ref": "backend/nexus_qualification/dryrun_v13",
            "implementation_fingerprint": "synthetic_impl_funding_v13f",
            "dataset_ref": "SYNTHETIC_DEV_DATASET_V13F",
            "dataset_lineage": {
                "dataset_id": "SYNTHETIC_DEV_DATASET_V13F",
                "source": "synthetic_fixture_generator",
                "real_market_data": False,
            },
            "development_interval": {
                "start_ms": as_of_ms - 55 * 86_400_000,
                "end_ms": as_of_ms - 25 * 86_400_000,
                "category": "development",
            },
            "parameters": {
                "funding_z_entry": 2.0,
                "hold_hours": 8,
                "fixture_marker": True,
            },
            "gross_result": None,
            "net_result": None,
            "trade_count": 0,
            "multiple_comparison_metadata": {"family_wise": True, "fixture": True},
            "failure_reasons": ["cost_destroyed_edge"],
            "qualified": False,
            "selected": False,
            "promoted": False,
            "fixture_only": True,
            "preregistration_timestamp": "2026-01-01T00:00:00Z",
            "as_of_ms": as_of_ms,
        },
        {
            "candidate_id": "SYN_V13F_DISC_003",
            "candidate_label": "synthetic_rejected_cosmetic",
            "semantic_mechanism_id": "cosmetic_variation_rejected",
            "strategy_family": "REJECTED_COSMETIC",
            "economic_mechanism": "duplicate_mechanism_variant",
            "discovery_label": "REJECTED",
            "required_data_capabilities": ["ohlcv_1h"],
            "eligible_symbol_profile": ["SYNTHUSDT"],
            "eligible_regimes": ["synthetic_chop"],
            "parameter_source": "synthetic_discovery_factory_v3",
            "factory_version": "v3_synthetic_fixture",
            "cost_model_version": "founder-conservative-v1-1-fixture",
            "code_ref": "backend/nexus_qualification/dryrun_v13",
            "implementation_fingerprint": "synthetic_impl_reject_v13f",
            "dataset_ref": "SYNTHETIC_DEV_DATASET_V13F",
            "dataset_lineage": {
                "dataset_id": "SYNTHETIC_DEV_DATASET_V13F",
                "source": "synthetic_fixture_generator",
                "real_market_data": False,
            },
            "development_interval": {
                "start_ms": as_of_ms - 40 * 86_400_000,
                "end_ms": as_of_ms - 20 * 86_400_000,
                "category": "development",
            },
            "parameters": {"lookback_bars": 12, "fixture_marker": True},
            "gross_result": None,
            "net_result": None,
            "trade_count": 0,
            "multiple_comparison_metadata": {"family_wise": True, "fixture": True},
            "failure_reasons": ["cosmetic_duplicate_mechanism"],
            "qualified": False,
            "selected": False,
            "promoted": False,
            "fixture_only": True,
            "preregistration_timestamp": "2026-01-01T00:00:00Z",
            "as_of_ms": as_of_ms,
        },
    ]
    return {
        "factory_version": "v3_synthetic_fixture",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "qualified_count": 0,
        "oos_consumed": False,
        "formal_walk_forward_executed": False,
        "fixture_only": True,
        "as_of_ms": as_of_ms,
    }


def build_synthetic_discovery_bundle(*, as_of_ms: int = AS_OF_MS_DEFAULT) -> dict[str, Any]:
    market = synthetic_market_discovery(as_of_ms=as_of_ms)
    strategy = synthetic_strategy_discovery(as_of_ms=as_of_ms)
    return {
        "schema": DISCOVERY_BUNDLE_SCHEMA,
        "fixture_only": True,
        "real_oos_touched": False,
        "strategy_discovery": strategy,
        "market_discovery": market,
        "as_of_ms": as_of_ms,
        "bundle_checksum": sha_obj(
            {
                "strategy_candidate_ids": [c["candidate_id"] for c in strategy["candidates"]],
                "universe_checksum": market["universe_checksum"],
                "as_of_ms": as_of_ms,
            }
        ),
    }


def validate_discovery_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if bundle.get("schema") != DISCOVERY_BUNDLE_SCHEMA:
        errors.append("invalid_discovery_bundle_schema")
    if bundle.get("fixture_only") is not True:
        errors.append("discovery_bundle_must_be_fixture_only")
    if bundle.get("real_oos_touched") is True:
        errors.append("real_oos_touched_forbidden")

    strategy = bundle.get("strategy_discovery") or {}
    market = bundle.get("market_discovery") or {}
    if not isinstance(strategy.get("candidates"), list):
        errors.append("strategy_candidates_missing")
        return errors
    if strategy.get("qualified_count", 0) != 0:
        errors.append("discovery_qualified_count_must_be_zero")
    if strategy.get("oos_consumed") is True:
        errors.append("discovery_oos_consumed_forbidden")
    if strategy.get("formal_walk_forward_executed") is True:
        errors.append("discovery_formal_wf_forbidden")

    for cand in strategy["candidates"]:
        label = cand.get("discovery_label")
        if label not in ALLOWED_DISCOVERY_LABELS:
            errors.append(f"invalid_discovery_label:{cand.get('candidate_id')}:{label}")
        if cand.get("qualified") is True:
            errors.append(f"candidate_marked_qualified:{cand.get('candidate_id')}")
        if cand.get("selected") is True:
            errors.append(f"candidate_selected:{cand.get('candidate_id')}")
        if cand.get("promoted") is True:
            errors.append(f"candidate_promoted:{cand.get('candidate_id')}")
        if cand.get("fixture_only") is not True:
            errors.append(f"candidate_not_fixture_only:{cand.get('candidate_id')}")

    if not market.get("universe_checksum"):
        errors.append("market_universe_checksum_missing")
    if market.get("as_of_ms") is None:
        errors.append("market_as_of_ms_missing")
    # Point-in-time: rejected future listings must not enter eligible
    as_of = int(market.get("as_of_ms") or 0)
    for e in market.get("eligible_universe") or []:
        listing = int(e.get("listing_timestamp_ms") or 0)
        if listing > as_of:
            errors.append(f"future_listed_in_eligible:{e.get('symbol')}")
    return errors


def ingest_discovery_bundle(bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate Discovery outputs and stamp qualification checksums. No selection."""
    src = deepcopy(bundle) if bundle is not None else build_synthetic_discovery_bundle()
    errors = validate_discovery_bundle(src)
    if errors:
        raise ValueError(f"discovery_bundle_invalid:{errors}")

    market = src["market_discovery"]
    stamped_candidates: list[dict[str, Any]] = []
    for cand in src["strategy_discovery"]["candidates"]:
        stamped = stamp_all_checksums(cand, market=market)
        stamped["qualified"] = False
        stamped["selected"] = False
        stamped["promoted"] = False
        stamped_candidates.append(stamped)

    return {
        "schema": DISCOVERY_BUNDLE_SCHEMA,
        "fixture_only": True,
        "as_of_ms": src["as_of_ms"],
        "bundle_checksum": src.get("bundle_checksum"),
        "market_discovery": deepcopy(market),
        "strategy_discovery": {
            **deepcopy(src["strategy_discovery"]),
            "candidates": stamped_candidates,
            "candidate_count": len(stamped_candidates),
            "qualified_count": 0,
        },
        "ingested_candidate_count": len(stamped_candidates),
        "qualification_ready_count": 0,
        "selected_strategy": None,
        "validation_errors": [],
    }
