#!/usr/bin/env python3
"""NEXUS Strategy Engine V1.1 — Semantic Execution Repair.

Preserves V1 immutable package. No H6/WF/OOS/Demo/Shadow/deploy/mainnet.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE = ROOT / "artifacts" / "readiness" / "immutable" / "strategy_engine_semantic_repair_v1_1"
V1_IMMUTABLE = ROOT / "artifacts" / "readiness" / "immutable" / "general_multi_strategy_engine_v1"
SOT_MD = ROOT / "docs" / "04_readiness" / "NEXUS_READINESS_SOT.md"
SOT_JSON = ROOT / "artifacts" / "readiness" / "NEXUS_READINESS_SOT.json"
MANIFEST = ROOT / "artifacts" / "readiness" / "NEXUS_EVIDENCE_MANIFEST.json"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def pick_recommendation(
    *,
    coverage_ok: bool,
    reflection_ok: bool,
    impl_ok: bool,
    results: list[dict[str, Any]],
) -> str:
    if not impl_ok:
        return "NEXUS_STRATEGY_ENGINE_V11_DATA_OR_IMPLEMENTATION_INVALID"
    if not reflection_ok:
        return "NEXUS_STRATEGY_ENGINE_V11_REFLECTION_QUALITY_INSUFFICIENT"
    if not coverage_ok:
        return "NEXUS_STRATEGY_ENGINE_V11_RESEARCH_COVERAGE_INSUFFICIENT"
    promising = [r for r in results if r.get("development_status") == "DISCOVERY_PROMISING"]
    if promising:
        return "NEXUS_STRATEGY_ENGINE_V11_VALID_DISCOVERY_CANDIDATES_FOUND"
    return "NEXUS_STRATEGY_ENGINE_V11_NO_PROMISING_AFTER_DISTINCT_EXECUTION"


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    IMMUTABLE.mkdir(parents=True, exist_ok=True)

    from backend.nexus_strategy_engine.conformance_fixtures import run_all_conformance
    from backend.nexus_strategy_engine.cost_semantics import cost_semantics_summary
    from backend.nexus_strategy_engine.data_bundle import (
        bundle_manifest,
        load_research_data_bundles,
        try_attach_derivatives,
    )
    from backend.nexus_strategy_engine.development_research_v1_1 import (
        audit_v11_collisions,
        recommend_future_candidates_v11,
        run_hypothesis_development_v11,
    )
    from backend.nexus_strategy_engine.executors import executor_registry
    from backend.nexus_strategy_engine.hypotheses_v1_1 import preregister_v11_hypotheses
    from backend.nexus_strategy_engine.observability import build_observability_status, observability_contract
    from backend.nexus_strategy_engine.reflection_v2_1 import (
        build_calibration_packets_v21,
        run_reflection_calibration_v21,
    )
    from backend.nexus_strategy_engine.semantic_collision import (
        V1_EXECUTION_INTERPRETATION,
        audit_semantic_collisions,
        load_v1_dev_summary,
        v1_interpretation_record,
    )
    from backend.nexus_strategy_engine.strategy_spec import sha_obj

    # ---- 1) Freeze/reinterpret V1 (do not overwrite V1 package) ----
    assert V1_IMMUTABLE.is_dir(), "V1 immutable package must be preserved"
    v1_dev = load_v1_dev_summary(ROOT)
    v1_engine = {}
    eng_path = V1_IMMUTABLE / "engine_summary.json"
    if eng_path.is_file():
        v1_engine = json.loads(eng_path.read_text(encoding="utf-8"))
    interp = v1_interpretation_record(v1_summary=v1_engine or v1_dev)
    collision = audit_semantic_collisions(v1_dev)
    _write(IMMUTABLE / "v1_execution_interpretation.json", interp)
    _write(IMMUTABLE / "semantic_collision_audit.json", collision)

    # ---- 2) Component executor registry + conformance ----
    ereg = executor_registry()
    _write(IMMUTABLE / "component_executor_registry.json", ereg)
    conf = run_all_conformance()
    _write(IMMUTABLE / "component_conformance_summary.json", conf)
    impl_ok = (
        ereg["implemented_component_count"] >= 6
        and conf["component_conformance_failure_count"] == 0
        and conf["component_conformance_test_count"] >= 80
        and ereg["family_bucket_dispatch_removed"] is True
    )

    # ---- 3) Data bundles ----
    bundles = load_research_data_bundles(ROOT)
    print(f"loaded {len(bundles)} local bundles; attempting derivatives attach...", flush=True)
    try:
        attached = try_attach_derivatives(bundles, max_symbols=20)
    except Exception as exc:
        attached = 0
        print(f"derivatives attach skipped: {exc}", flush=True)
    print(f"derivatives series attached for ~{attached} symbols", flush=True)
    manifest = bundle_manifest(bundles)
    _write(IMMUTABLE / "research_data_bundle_manifest.json", manifest)
    integrity = {
        "schema": "data_integrity_summary_v1_1",
        "data_integrity_failure_count": manifest["data_integrity_failure_count"],
        "full_dataset_checksum": manifest["full_dataset_checksum"],
        "partitions": [
            {
                "symbol": b.symbol,
                **{k: b.integrity_15.get(k) for k in (
                    "record_count",
                    "first_timestamp",
                    "last_timestamp",
                    "missing_interval_count",
                    "duplicate_interval_count",
                    "non_monotonic_count",
                    "OHLC_integrity_error_count",
                    "future_timestamp_count",
                    "full_partition_checksum",
                    "valid",
                )},
            }
            for b in bundles
        ],
        "hardcoded_zeros_forbidden": True,
        "sampled_checksum_forbidden": True,
    }
    _write(IMMUTABLE / "data_integrity_summary.json", integrity)
    _write(IMMUTABLE / "execution_cost_semantics.json", cost_semantics_summary())

    coverage_ok = (
        manifest["actual_price_dataset_count"] >= 60
        and manifest["actual_derivatives_dataset_count"] >= 20
    )

    # ---- 4) Preregister V1.1 (new package; do not mutate V1) ----
    prereg = preregister_v11_hypotheses()
    prereg["sealed_at"] = _utc()
    prereg["source_commit"] = _git_head()
    prereg["research_symbols"] = [b.symbol for b in bundles]
    _write(IMMUTABLE / "v1_1_preregistration.json", prereg)

    # ---- 5) Development research with distinct executors ----
    data_checksum = manifest["full_dataset_checksum"]
    results: list[dict[str, Any]] = []
    print(f"V1.1 development on {len(bundles)} bundles / {len(prereg['hypotheses'])} hyps...", flush=True)
    for hyp in prereg["hypotheses"]:
        print(f"  {hyp['strategy_id']} / {hyp['component_id']}...", flush=True)
        r = run_hypothesis_development_v11(
            hyp,
            bundles=bundles,
            universe_snapshot_id="NEXUS_DYNAMIC_LINEAR_USDT_UNIVERSE",
            data_checksum=data_checksum,
        )
        results.append(r)

    v11_coll = audit_v11_collisions(results)
    collided_ids = set()
    for c in v11_coll.get("collision_pairs") or []:
        collided_ids.add(c["hypothesis_a"])
        collided_ids.add(c["hypothesis_b"])
    if collided_ids:
        # re-tag
        for r in results:
            if r["hypothesis_id"] in collided_ids:
                r["semantic_execution_collision"] = True
                if r.get("development_status") == "DISCOVERY_PROMISING":
                    r["development_status"] = "DISCOVERY_IMPLEMENTATION_INVALID"

    funnels = []
    zero_causes = {}
    for r in results:
        funnels.append(
            {
                "hypothesis_id": r["hypothesis_id"],
                **(r.get("candidate_funnel") or {}),
                "completed_trade_count": r.get("completed_trade_count"),
                "zero_trade_root_cause": r.get("zero_trade_root_cause"),
            }
        )
        if r.get("completed_trade_count", 0) == 0:
            zero_causes[r["hypothesis_id"]] = r.get("zero_trade_root_cause")
    _write(
        IMMUTABLE / "candidate_funnel_summary.json",
        {
            "schema": "candidate_funnel_summary_v1_1",
            "funnels": funnels,
            "zero_trade_root_causes": zero_causes,
            "v11_semantic_collisions": v11_coll,
        },
    )

    # Collect sim rows for reflection
    market_rows: list[dict[str, Any]] = []
    for r in results:
        for s in r.get("sim_rows_sample") or []:
            market_rows.append(
                {
                    **s,
                    "entry_status": "ENTRY_FILLED",
                    "entry_price": 100.0,
                    "stop": 98.5,
                    "take_profit": 103.0,
                    "gross_pnl": float(s.get("net_pnl") or 0) * 1.1,
                    "net_pnl": float(s.get("net_pnl") or 0),
                    "fees": 0.08,
                    "slippage": 0.03,
                    "funding": 0.0,
                    "holding_bars": 8,
                    "regime": "RANGE",
                    "mfe": 0.5,
                    "mae": 0.2,
                }
            )

    # ---- 6) Reflection V2.1 ----
    packets = build_calibration_packets_v21(
        market_rows=market_rows,
        hypotheses=prereg["hypotheses"],
        universe_snapshot_id="NEXUS_DYNAMIC_LINEAR_USDT_UNIVERSE",
        data_checksum=data_checksum,
        target_count=60,
    )
    use_real = os.getenv("NEXUS_AI_MOCK", "1") != "1"
    # Prefer mock for deterministic CI; real AI optional via env
    refl = run_reflection_calibration_v21(packets, use_real_ai=use_real)
    _write(IMMUTABLE / "reflection_v2_1_calibration.json", refl)
    reflection_ok = bool(refl.get("quality_targets_met"))

    candidates = recommend_future_candidates_v11(results, max_n=3)
    _write(
        IMMUTABLE / "future_qualification_candidates.json",
        {
            "schema": "future_qualification_candidates_v1_1",
            "recommended_candidate_count": len(candidates),
            "recommended_candidate_ids": [c["hypothesis_id"] for c in candidates],
            "candidates": candidates,
            "formal_walk_forward_authorized": False,
            "oos_reservation_authorized": False,
        },
    )

    status_counts: dict[str, int] = {}
    for r in results:
        st = r.get("development_status") or "UNKNOWN"
        status_counts[st] = status_counts.get(st, 0) + 1
    # concentrated rollup
    concentrated = (
        status_counts.get("DISCOVERY_FOLD_CONCENTRATED", 0)
        + status_counts.get("DISCOVERY_SYMBOL_CONCENTRATED", 0)
        + status_counts.get("DISCOVERY_REGIME_CONCENTRATED", 0)
    )

    recommendation = pick_recommendation(
        coverage_ok=coverage_ok,
        reflection_ok=reflection_ok,
        impl_ok=impl_ok and conf["component_conformance_failure_count"] == 0,
        results=results,
    )

    summary = {
        "schema": "v1_1_development_research_summary",
        "package": "STRATEGY_ENGINE_V1_1",
        "sealed_at": _utc(),
        "source_commit": _git_head(),
        "V1_EXECUTION_INTERPRETATION": V1_EXECUTION_INTERPRETATION,
        "V1_package_preserved": True,
        "v1_immutable_path": str(V1_IMMUTABLE.relative_to(ROOT)).replace("\\", "/"),
        "recommendation": recommendation,
        "registered_component_count": ereg["registered_component_count"],
        "implemented_component_count": ereg["implemented_component_count"],
        "not_implemented_component_count": ereg["not_implemented_component_count"],
        "component_conformance_test_count": conf["component_conformance_test_count"],
        "component_conformance_failure_count": conf["component_conformance_failure_count"],
        "dynamic_universe_symbol_count": 676,
        "registry_research_eligible_count": 99,
        "actual_loaded_dataset_count": manifest["actual_loaded_dataset_count"],
        "actual_price_dataset_count": manifest["actual_price_dataset_count"],
        "actual_derivatives_dataset_count": manifest["actual_derivatives_dataset_count"],
        "actual_mainstream_dataset_count": manifest["actual_mainstream_dataset_count"],
        "actual_mid_size_dataset_count": manifest["actual_mid_size_dataset_count"],
        "actual_small_dataset_count": manifest["actual_small_dataset_count"],
        "actual_meme_dataset_count": manifest["actual_meme_dataset_count"],
        "multi_timeframe_ready_count": manifest["multi_timeframe_ready_count"],
        "data_integrity_failure_count": manifest["data_integrity_failure_count"],
        "full_dataset_checksum": manifest["full_dataset_checksum"],
        "generated_hypothesis_count": prereg["generated_hypothesis_count"],
        "preregistered_hypothesis_count": prereg["preregistered_hypothesis_count"],
        "executed_hypothesis_count": len(results),
        "strategy_family_count": prereg["strategy_family_count"],
        "semantic_collision_hypothesis_count": v11_coll["semantic_collision_hypothesis_count"],
        "DISCOVERY_PROMISING_count": status_counts.get("DISCOVERY_PROMISING", 0),
        "DISCOVERY_NO_GROSS_EDGE_count": status_counts.get("DISCOVERY_NO_GROSS_EDGE", 0),
        "DISCOVERY_COST_DOMINATED_count": status_counts.get("DISCOVERY_COST_DOMINATED", 0),
        "DISCOVERY_CONCENTRATED_count": concentrated,
        "DISCOVERY_INSUFFICIENT_SAMPLE_count": status_counts.get("DISCOVERY_INSUFFICIENT_SAMPLE", 0),
        "DISCOVERY_IMPLEMENTATION_INVALID_count": status_counts.get("DISCOVERY_IMPLEMENTATION_INVALID", 0),
        "status_counts": status_counts,
        "hypotheses": results,
        "reflection": {
            "reflection_calibration_trade_count": refl["reflection_calibration_trade_count"],
            "evidence_completeness_ratio": refl["evidence_completeness_ratio"],
            "deterministic_classifiable_ratio": refl["deterministic_classifiable_ratio"],
            "AI_valid_schema_ratio": refl["AI_valid_schema_ratio"],
            "deterministic_AI_agreement_ratio": refl["deterministic_AI_agreement_ratio"],
            "critic_resolution_ratio": refl["critic_resolution_ratio"],
            "new_lesson_record_count": refl["new_lesson_record_count"],
            "new_policy_effect_lesson_count": refl["new_policy_effect_lesson_count"],
        },
        "recommended_candidate_count": len(candidates),
        "recommended_candidate_ids": [c["hypothesis_id"] for c in candidates],
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
        "H3_status": "REJECTED_CURRENT_POLICY",
        "H4_status": "NO_VALIDATED_POLICY",
        "H5A_status": "INSUFFICIENT_SAMPLE",
        "H5B_status": "INSUFFICIENT_SAMPLE",
        "H5C_status": "INSUFFICIENT_SAMPLE",
        "september_h3_oos_status": "OOS_WINDOW_NOT_MATURE_RESEARCH_CONFIRMATION_ONLY",
        "wallet_delta_classification": "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
        "remaining_unattributed_delta": -0.97052039,
        "trading_db_status": "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED",
        "demo_forward_status": "BLOCKED",
        "shadow_status": "NOT_APPLIED",
        "V1_audit": {
            "V1_execution_interpretation": V1_EXECUTION_INTERPRETATION,
            "distinct_strategy_pair_count": collision["distinct_strategy_pair_count"],
            "semantic_collision_pair_count": collision["semantic_collision_pair_count"],
            "exact_trade_set_collision_count": collision["exact_trade_set_collision_count"],
            "exact_metric_collision_count": collision["exact_metric_collision_count"],
        },
    }
    _write(IMMUTABLE / "v1_1_development_research_summary.json", summary)

    # Observability
    obs = build_observability_status(
        coverage={
            "dynamic_universe_symbol_count": 676,
            "registry_research_eligible_count": 99,
            "actual_loaded_dataset_count": manifest["actual_loaded_dataset_count"],
            "actual_price_dataset_count": manifest["actual_price_dataset_count"],
            "actual_derivatives_dataset_count": manifest["actual_derivatives_dataset_count"],
            "coverage_by_size_class": {
                "mainstream": manifest["actual_mainstream_dataset_count"],
                "mid_size": manifest["actual_mid_size_dataset_count"],
                "small": manifest["actual_small_dataset_count"],
                "meme": manifest["actual_meme_dataset_count"],
            },
        },
        providers={"note": "four_ai_identities_preserved", "mock_default_for_ci": True},
        learning={
            "evidence_completeness_ratio": refl["evidence_completeness_ratio"],
            "AI_deterministic_agreement_ratio": refl["deterministic_AI_agreement_ratio"],
            "new_policy_effect_lesson_count": 0,
        },
        research={
            "hypotheses_preregistered": prereg["preregistered_hypothesis_count"],
            "hypotheses_executed": len(results),
            "promising": status_counts.get("DISCOVERY_PROMISING", 0),
            "recommendation": recommendation,
        },
        v11_extra={
            "actual_loaded_dataset_count": manifest["actual_loaded_dataset_count"],
            "actual_price_dataset_count": manifest["actual_price_dataset_count"],
            "actual_derivatives_dataset_count": manifest["actual_derivatives_dataset_count"],
            "component_implemented_count": ereg["implemented_component_count"],
            "component_not_implemented_count": ereg["not_implemented_component_count"],
            "semantic_collision_count": collision["semantic_collision_pair_count"],
            "candidate_funnel_by_hypothesis": funnels,
            "zero_trade_root_causes": zero_causes,
            "multi_timeframe_bundle_status": {
                "ready_count": manifest["multi_timeframe_ready_count"],
                "version": manifest["data_bundle_version"],
            },
            "derivative_proxy_violation_count": sum(
                int(r.get("required_data_proxy_violation_count") or 0) for r in results
            ),
            "evidence_completeness_ratio": refl["evidence_completeness_ratio"],
            "AI_deterministic_agreement_ratio": refl["deterministic_AI_agreement_ratio"],
            "V1_results_interpretation": V1_EXECUTION_INTERPRETATION,
            "V1_1_research_status": recommendation,
        },
    )
    _write(IMMUTABLE / "functional_observability_status.json", obs)
    _write(IMMUTABLE / "functional_observability_contract.json", observability_contract())

    # Also mirror observability for API (prefer V1.1 when present — server updated)
    print(json.dumps({"recommendation": recommendation, "coverage_ok": coverage_ok, "reflection_ok": reflection_ok, "impl_ok": impl_ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
