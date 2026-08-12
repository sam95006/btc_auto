"""Connect mechanism defs, Feature Lab, dynamic universe, cost, robustness, Qualification plans.

Sibling V14 modules may be absent in this worktree; connectors consume:
  - live V13 Feature Lab + Dynamic Universe APIs when importable
  - fixture contracts for mechanism / cost / robustness when siblings absent
  - blocked Qualification planning (plans only; never execute)
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_candidate_triage.constants import (
    CONNECTION_SURFACES,
    EVIDENCE_CLASS,
    PLAN_STATUS_PLANNED_NOT_EXECUTED,
    SCHEMA_ID,
)
from backend.nexus_candidate_triage.fixtures import clone_bundle


def _connect_feature_lab(candidate: dict[str, Any]) -> dict[str, Any]:
    feature_ids = list(candidate.get("feature_ids") or [])
    catalog_ids: list[str] = []
    catalog_version = None
    source = "fixture_feature_contract"
    try:
        from backend.nexus_micro_feature_lab.catalog import feature_catalog
        from backend.nexus_micro_feature_lab.constants import FEATURE_IDS

        catalog = feature_catalog()
        catalog_ids = sorted(FEATURE_IDS)
        catalog_version = catalog.get("catalog_version") or catalog.get("version")
        missing = [fid for fid in feature_ids if fid not in FEATURE_IDS]
        source = "nexus_micro_feature_lab"
        connected = len(missing) == 0 and len(feature_ids) > 0
        return {
            "surface": "feature_lab",
            "connected": connected,
            "source": source,
            "requested_feature_ids": feature_ids,
            "catalog_feature_count": len(catalog_ids),
            "catalog_version": catalog_version,
            "missing_feature_ids": missing,
            "fixture_only": True,
            "predictive_edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001 — fail-closed connection report
        return {
            "surface": "feature_lab",
            "connected": False,
            "source": source,
            "requested_feature_ids": feature_ids,
            "catalog_feature_count": 0,
            "catalog_version": None,
            "missing_feature_ids": feature_ids,
            "error": type(exc).__name__,
            "fixture_only": True,
            "predictive_edge_claimed": False,
        }


def _connect_dynamic_universe(candidate: dict[str, Any], *, as_of_ms: int) -> dict[str, Any]:
    symbols = list(candidate.get("universe_symbols") or [])
    try:
        from backend.nexus_dynamic_universe import (
            UNIVERSE_ID,
            normalize_instrument,
            point_in_time_membership,
        )

        # Fixture instruments — never call live Bybit from triage harness.
        ts = "1970-01-01T00:00:00Z"
        instruments = []
        for sym in symbols:
            row = {
                "symbol": sym,
                "baseCoin": sym.replace("USDT", "") or "SYN",
                "quoteCoin": "USDT",
                "settleCoin": "USDT",
                "status": "Trading",
                "contractType": "LinearPerpetual",
                "launchTime": str(as_of_ms - 365 * 86_400_000),
                "deliveryTime": "0",
                "priceFilter": {"tickSize": "0.1"},
                "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "minNotionalValue": "5"},
                "leverageFilter": {"maxLeverage": "50"},
            }
            instruments.append(normalize_instrument(row, snapshot_timestamp=ts).to_dict())
        snapshot = {
            "universe_id": UNIVERSE_ID,
            "instruments": instruments,
            "fixture_only": True,
            "source": "fixture_instruments_normalized_via_dynamic_universe",
        }
        pit = point_in_time_membership(snapshot, as_of_ms=as_of_ms)
        return {
            "surface": "dynamic_universe",
            "connected": True,
            "source": "nexus_dynamic_universe+fixture_instruments",
            "universe_id": UNIVERSE_ID,
            "requested_symbols": symbols,
            "pit_symbols": pit,
            "pit_membership_ok": all(s in pit for s in symbols),
            "fixture_only": True,
            "live_exchange_called": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "surface": "dynamic_universe",
            "connected": False,
            "source": "fixture_universe_contract",
            "requested_symbols": symbols,
            "pit_symbols": [],
            "pit_membership_ok": False,
            "error": type(exc).__name__,
            "fixture_only": True,
            "live_exchange_called": False,
        }


def _connect_mechanism(candidate: dict[str, Any]) -> dict[str, Any]:
    mech = dict(candidate.get("mechanism") or {})
    required = [
        "mechanism_semantic_id",
        "economic_rationale",
        "required_data",
        "pit_semantics",
        "entry_hypothesis",
        "exit_hypothesis",
        "failure_hypothesis",
        "invalidating_conditions",
    ]
    missing = [k for k in required if not mech.get(k)]
    return {
        "surface": "mechanism_definitions",
        "connected": len(missing) == 0,
        "source": "fixture_mechanism_contract_v14c_compatible",
        "mechanism_semantic_id": mech.get("mechanism_semantic_id"),
        "mechanism_family": mech.get("mechanism_family"),
        "missing_fields": missing,
        "deterministic": bool(mech.get("deterministic")),
        "fixture_only": True,
        "cosmetic_parameter_variant": False,
    }


def _connect_cost_sensitivity(candidate: dict[str, Any]) -> dict[str, Any]:
    cost = dict(candidate.get("cost_sensitivity") or {})
    required = [
        "gross_expectancy",
        "net_expectancy",
        "cost_destroyed",
        "break_even_cost",
        "fragility_score",
        "canonical_cost_authority_consumed",
    ]
    missing = [k for k in required if k not in cost]
    return {
        "surface": "cost_sensitivity",
        "connected": len(missing) == 0,
        "source": "fixture_cost_sensitivity_v14e_compatible",
        "gross_expectancy": cost.get("gross_expectancy"),
        "net_expectancy": cost.get("net_expectancy"),
        "cost_destroyed": bool(cost.get("cost_destroyed")),
        "canonical_cost_authority_consumed": bool(cost.get("canonical_cost_authority_consumed")),
        "missing_fields": missing,
        "fixture_only": True,
        "canonical_cost_formulas_modified": False,
    }


def _connect_robustness(candidate: dict[str, Any]) -> dict[str, Any]:
    rob = dict(candidate.get("robustness") or {})
    label = rob.get("label")
    allowed_labels = {
        "DEVELOPMENT_ROBUST",
        "DEVELOPMENT_FRAGILE",
        "MULTIPLE_TESTING_REJECTED",
        "INSUFFICIENT_SAMPLE",
        "COST_DESTROYED",
        "DATA_QUALITY_BLOCKED",
    }
    return {
        "surface": "robustness_results",
        "connected": label in allowed_labels,
        "source": "fixture_robustness_v14d_compatible",
        "label": label,
        "label_allowed": label in allowed_labels,
        "bootstrap_stable": bool(rob.get("bootstrap_stable")),
        "regime_stable": bool(rob.get("regime_stable")),
        "sample_sufficient": bool(rob.get("sample_sufficient")),
        "multiple_testing_rejected": bool(rob.get("multiple_testing_rejected")),
        "fixture_only": True,
        "qualification_claim": False,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
    }


def _blocked_qualification_plan(candidate: dict[str, Any], *, as_of_ms: int) -> dict[str, Any]:
    cid = candidate.get("candidate_id")
    interval = candidate.get("development_interval") or {}
    start = int(interval.get("start_ms") or (as_of_ms - 60 * 86_400_000))
    end = int(interval.get("end_ms") or (as_of_ms - 30 * 86_400_000))
    mid = start + (end - start) // 2
    return {
        "surface": "blocked_qualification_planning",
        "connected": True,
        "source": "v14_h_blocked_qualification_plans",
        "candidate_id": cid,
        "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
        "formal_qualification_status": "BLOCKED",
        "walk_forward_plan": {
            "plan_kind": "WALK_FORWARD",
            "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
            "formal_walk_forward_executed": False,
            "folds": [
                {"fold_id": "WF_FOLD_TRAIN", "start_ms": start, "end_ms": mid},
                {"fold_id": "WF_FOLD_TEST", "start_ms": mid + 1, "end_ms": end},
            ],
            "note": "Plan only; formal WF remains BLOCKED.",
        },
        "oos_reservation_plan": {
            "plan_kind": "OOS_RESERVATION",
            "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
            "oos_reservation_created": False,
            "oos_executed": False,
            "oos_consumed": False,
            "note": "Plan only; real OOS neither reserved nor consumed.",
        },
        "risk_review_plan": {
            "plan_kind": "RISK_REVIEW",
            "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
            "risk_review_executed": False,
        },
        "demo_eligibility_plan": {
            "plan_kind": "DEMO_ELIGIBILITY",
            "status": PLAN_STATUS_PLANNED_NOT_EXECUTED,
            "demo_eligibility_granted": False,
            "demo_order_count": 0,
        },
        "qualification_ready": False,
        "fixture_only": True,
    }


def connect_candidate(candidate: dict[str, Any], *, as_of_ms: int) -> dict[str, Any]:
    connections = {
        "mechanism_definitions": _connect_mechanism(candidate),
        "feature_lab": _connect_feature_lab(candidate),
        "dynamic_universe": _connect_dynamic_universe(candidate, as_of_ms=as_of_ms),
        "cost_sensitivity": _connect_cost_sensitivity(candidate),
        "robustness_results": _connect_robustness(candidate),
        "blocked_qualification_planning": _blocked_qualification_plan(
            candidate, as_of_ms=as_of_ms
        ),
    }
    all_connected = all(bool(connections[s].get("connected")) for s in CONNECTION_SURFACES)
    return {
        "candidate_id": candidate.get("candidate_id"),
        "connections": connections,
        "all_surfaces_connected": all_connected,
        "surface_order": list(CONNECTION_SURFACES),
        "evidence_class": EVIDENCE_CLASS,
    }


def ingest_research_bundle(bundle: dict[str, Any] | None = None, *, as_of_ms: int | None = None) -> dict[str, Any]:
    src = clone_bundle(bundle, as_of_ms=as_of_ms)
    as_of = int(src["as_of_ms"])
    connected = [connect_candidate(c, as_of_ms=as_of) for c in src["candidates"]]
    return {
        "schema": SCHEMA_ID,
        "bundle_checksum": src.get("bundle_checksum"),
        "as_of_ms": as_of,
        "evidence_class": EVIDENCE_CLASS,
        "fixture_only": True,
        "ingested_candidate_count": len(src["candidates"]),
        "qualification_ready_count": 0,
        "candidates": deepcopy(src["candidates"]),
        "connections": connected,
        "all_candidates_connected": all(c["all_surfaces_connected"] for c in connected),
        "selected_strategy": None,
        "promoted_strategy": None,
        "formal_walk_forward_executed": False,
        "oos_touched": False,
    }
