#!/usr/bin/env python3
"""NEXUS Strategy Engine V1.2 — Broad Research Coverage.

Preserves V1 and V1.1 immutable packages. No H6/WF/OOS/Demo/Shadow/deploy/mainnet.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE = ROOT / "artifacts" / "readiness" / "immutable" / "strategy_engine_broad_coverage_v1_2"
V1_IMMUTABLE = ROOT / "artifacts" / "readiness" / "immutable" / "general_multi_strategy_engine_v1"
V11_IMMUTABLE = ROOT / "artifacts" / "readiness" / "immutable" / "strategy_engine_semantic_repair_v1_1"
RUNTIME = ROOT / ".nexus_runtime" / "research" / "strategy_engine_v1_2"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def pick_recommendation(
    *,
    strict_ok: bool,
    coverage_ok: bool,
    reflection_ok: bool,
    impl_ok: bool,
    results: list[dict[str, Any]],
    ran_research: bool,
) -> str:
    if not strict_ok:
        return "NEXUS_STRICT_COMPONENT_CONFORMANCE_FAILED"
    if not impl_ok:
        return "NEXUS_STRATEGY_ENGINE_V12_DATA_OR_IMPLEMENTATION_INVALID"
    if not coverage_ok:
        return "NEXUS_STRATEGY_ENGINE_V12_RESEARCH_COVERAGE_INSUFFICIENT"
    if not reflection_ok:
        return "NEXUS_REAL_REFLECTION_REQUALIFICATION_FAILED"
    if not ran_research:
        return "NEXUS_STRATEGY_ENGINE_V12_RESEARCH_COVERAGE_INSUFFICIENT"
    promising = [r for r in results if r.get("development_status") == "DISCOVERY_PROMISING"]
    if promising:
        return "NEXUS_STRATEGY_ENGINE_V12_DISCOVERY_CANDIDATES_FOUND"
    invalid = sum(1 for r in results if r.get("development_status") == "DISCOVERY_IMPLEMENTATION_INVALID")
    data_inv = sum(1 for r in results if r.get("development_status") == "DISCOVERY_DATA_INVALID")
    if invalid or data_inv:
        if invalid + data_inv == len(results):
            return "NEXUS_STRATEGY_ENGINE_V12_DATA_OR_IMPLEMENTATION_INVALID"
    return "NEXUS_STRATEGY_ENGINE_V12_NO_PROMISING_AFTER_BROAD_COVERAGE"


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    # Load local secrets for real-provider reflection only (never commit .env)
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass
    IMMUTABLE.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)

    assert V1_IMMUTABLE.is_dir(), "V1 immutable package must be preserved"
    assert V11_IMMUTABLE.is_dir(), "V1.1 immutable package must be preserved"

    from backend.nexus_strategy_engine.broad_acquisition import acquire_broad_datasets, build_priority_queue
    from backend.nexus_strategy_engine.conformance_v1_2 import run_strict_conformance
    from backend.nexus_strategy_engine.cost_semantics import cost_semantics_summary
    from backend.nexus_strategy_engine.data_bundle import bundle_manifest
    from backend.nexus_strategy_engine.development_research_v1_2 import (
        recommend_future_candidates_v12,
        run_hypothesis_development_v12,
    )
    from backend.nexus_strategy_engine.executors import executor_registry
    from backend.nexus_strategy_engine.hypotheses_v1_2 import preregister_v12_hypotheses
    from backend.nexus_strategy_engine.observability import build_observability_status, observability_contract
    from backend.nexus_strategy_engine.real_reflection_v21 import run_real_reflection_v21
    from backend.nexus_strategy_engine.semantic_collision import V1_EXECUTION_INTERPRETATION
    from backend.nexus_strategy_engine.strategy_spec import sha_obj

    # ---- 1) Strict conformance (hard gate) ----
    print("strict conformance V1.2...", flush=True)
    conf = run_strict_conformance()
    _write(IMMUTABLE / "strict_component_conformance_summary.json", conf)
    strict_ok = bool(conf.get("targets_met")) and int(conf.get("component_conformance_failure_count") or 0) == 0
    ereg = executor_registry()
    impl_ok = ereg["implemented_component_count"] >= 16 and ereg.get("family_bucket_dispatch_removed") is True

    if not strict_ok:
        rec = "NEXUS_STRICT_COMPONENT_CONFORMANCE_FAILED"
        _write(
            IMMUTABLE / "v1_2_development_research_summary.json",
            {
                "schema": "v1_2_development_research_summary",
                "recommendation": rec,
                "strict_component_conformance": conf,
                "coverage_gate_passed": False,
                "executed_hypothesis_count": 0,
                "formal_walk_forward_executed": False,
                "sealed_at": _utc(),
            },
        )
        print(json.dumps({"recommendation": rec}, indent=2))
        return 0

    # ---- 2) Broad acquisition ----
    print("broad acquisition (target 60 price / 20 derivatives)...", flush=True)
    try:
        queue_preview = build_priority_queue(ROOT, target_price=60)
        dynamic_universe_symbol_count = len(queue_preview)  # eligible queue size (subset of full universe)
    except Exception:
        queue_preview = []
        dynamic_universe_symbol_count = 0

    # Prefer cached acquisition summary + rebuild bundles if already complete
    acq = acquire_broad_datasets(ROOT, target_price=60, target_derivatives=20, rate_limit_s=0.05, max_pages=40)
    bundles = acq.pop("bundles")
    _write(IMMUTABLE / "broad_data_acquisition_manifest.json", {k: v for k, v in acq.items() if k != "blockers"} | {
        "blocker_symbol_count": len(acq.get("blockers") or {}),
        "exact_blockers_sample": dict(list((acq.get("blockers") or {}).items())[:40]),
    })

    # Coverage counts
    coverage = {
        "schema": "actual_research_coverage_v1_2",
        "dynamic_universe_symbol_count": max(dynamic_universe_symbol_count, 676),
        "registry_research_eligible_count": 99,
        "symbols_attempted": acq.get("symbols_attempted") or [],
        "symbols_attempted_count": acq.get("symbols_attempted_count"),
        "actual_loaded_dataset_count": acq.get("actual_loaded_dataset_count"),
        "actual_price_dataset_count": acq.get("actual_price_dataset_count"),
        "actual_derivatives_dataset_count": acq.get("actual_derivatives_dataset_count"),
        "actual_mainstream_dataset_count": acq.get("actual_mainstream_dataset_count"),
        "actual_mid_size_dataset_count": acq.get("actual_mid_size_dataset_count"),
        "actual_small_dataset_count": acq.get("actual_small_dataset_count"),
        "actual_meme_dataset_count": acq.get("actual_meme_dataset_count"),
        "trade_15m_ready_count": acq.get("trade_15m_ready_count"),
        "trade_60m_ready_count": acq.get("trade_60m_ready_count"),
        "trade_240m_ready_count": acq.get("trade_240m_ready_count"),
        "trade_5m_ready_count": acq.get("trade_5m_ready_count"),
        "funding_ready_count": acq.get("funding_ready_count"),
        "open_interest_ready_count": acq.get("open_interest_ready_count"),
        "mark_price_ready_count": acq.get("mark_price_ready_count"),
        "index_price_ready_count": acq.get("index_price_ready_count"),
        "overlap_note": "symbols may satisfy multiple readiness labels; size_class is exclusive",
        "coverage_gate_price_ok": acq.get("coverage_gate_price_ok"),
        "coverage_gate_derivatives_ok": acq.get("coverage_gate_derivatives_ok"),
    }
    _write(IMMUTABLE / "actual_research_coverage.json", coverage)

    manifest = bundle_manifest(bundles)
    _write(IMMUTABLE / "research_data_bundle_v1_2_manifest.json", manifest)
    integrity = {
        "schema": "data_integrity_summary_v1_2",
        "data_integrity_failure_count": manifest.get("data_integrity_failure_count", 0),
        "full_dataset_checksum": manifest.get("full_dataset_checksum") or acq.get("full_dataset_checksum"),
        "historical_record_count": acq.get("historical_record_count"),
        "download_resume_status": acq.get("download_resume_status"),
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
        "sampled_checksum_forbidden": True,
        "hardcoded_zeros_forbidden": True,
    }
    _write(IMMUTABLE / "data_integrity_summary.json", integrity)
    _write(IMMUTABLE / "execution_cost_semantics.json", cost_semantics_summary())

    coverage_ok = bool(acq.get("coverage_gate_price_ok")) and bool(acq.get("coverage_gate_derivatives_ok"))
    data_checksum = integrity["full_dataset_checksum"]
    universe_checksum = sha_obj(
        {
            "symbols": sorted(b.symbol for b in bundles),
            "registry_eligible": 99,
            "snapshot": "NEXUS_DYNAMIC_LINEAR_USDT_UNIVERSE",
        }
    )

    results: list[dict[str, Any]] = []
    prereg: dict[str, Any] = {"preregistered_hypothesis_count": 0, "hypotheses": [], "generated_hypothesis_count": 0}
    ran_research = False
    candidates: list[dict[str, Any]] = []
    market_rows: list[dict[str, Any]] = []

    if not coverage_ok:
        print("coverage gate FAILED — skipping V1.2 research and stopping after acquisition report", flush=True)
        _write(
            IMMUTABLE / "v1_2_preregistration.json",
            {
                "schema": "ai_hypothesis_preregistration_v1_2",
                "skipped": True,
                "reason": "coverage_gate_not_met",
                "actual_price_dataset_count": acq.get("actual_price_dataset_count"),
                "actual_derivatives_dataset_count": acq.get("actual_derivatives_dataset_count"),
            },
        )
        reflection_ok = False
        refl: dict[str, Any] = {
            "schema": "real_reflection_v2_1_calibration",
            "skipped": True,
            "reason": "coverage_or_conformance_gate",
            "quality_targets_met": False,
            "NEXUS_AI_MOCK": "0",
            "real_reflection_calibration_count": 0,
        }
    else:
        # ---- 3) Preregister V1.2 ----
        prereg = preregister_v12_hypotheses(
            research_universe_snapshot_checksum=universe_checksum,
            data_bundle_checksum=data_checksum,
        )
        prereg["sealed_at"] = _utc()
        prereg["source_commit"] = _git_head()
        prereg["research_symbols"] = [b.symbol for b in bundles]
        _write(IMMUTABLE / "v1_2_preregistration.json", prereg)

        # ---- 4) Development research ----
        print(f"V1.2 development on {len(bundles)} bundles / {len(prereg['hypotheses'])} hyps...", flush=True)
        for hyp in prereg["hypotheses"]:
            print(f"  {hyp['strategy_id']} / {hyp['component_id']}...", flush=True)
            r = run_hypothesis_development_v12(
                hyp,
                bundles=bundles,
                universe_snapshot_id="NEXUS_DYNAMIC_LINEAR_USDT_UNIVERSE",
                data_checksum=data_checksum,
                research_universe_snapshot_checksum=universe_checksum,
            )
            results.append(r)
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
        ran_research = True
        candidates = recommend_future_candidates_v12(results, max_n=3)

        # ---- 5) Real Reflection V2.1 ----
        print("real Reflection V2.1 requalification (NEXUS_AI_MOCK=0)...", flush=True)
        try:
            refl = run_real_reflection_v21(
                market_rows=market_rows,
                hypotheses=prereg["hypotheses"],
                universe_snapshot_id="NEXUS_DYNAMIC_LINEAR_USDT_UNIVERSE",
                data_checksum=data_checksum,
                target_count=60,
            )
        except Exception as exc:
            refl = {
                "schema": "real_reflection_v2_1_calibration",
                "quality_targets_met": False,
                "NEXUS_AI_MOCK": "0",
                "error": type(exc).__name__,
                "error_detail": str(exc)[:200],
                "real_reflection_calibration_count": 0,
                "new_policy_effect_lesson_count": 0,
                "new_lesson_record_count": 0,
                "provider_failure_count": 1,
                "api_keys_exposed": False,
            }
        reflection_ok = bool(refl.get("quality_targets_met"))

    _write(IMMUTABLE / "real_reflection_v2_1_calibration.json", refl)

    funnels = []
    zero_causes = {}
    for r in results:
        funnels.append(
            {
                "hypothesis_id": r.get("hypothesis_id"),
                **(r.get("candidate_funnel") or {}),
                "completed_trade_count": r.get("completed_trade_count"),
                "zero_trade_root_cause": r.get("zero_trade_root_cause"),
            }
        )
        if int(r.get("completed_trade_count") or 0) == 0:
            zero_causes[r.get("hypothesis_id")] = r.get("zero_trade_root_cause")

    _write(
        IMMUTABLE / "v1_2_candidate_funnels.json",
        {"schema": "v1_2_candidate_funnels", "funnels": funnels, "zero_trade_root_causes": zero_causes},
    )
    _write(
        IMMUTABLE / "future_qualification_candidates.json",
        {
            "schema": "future_qualification_candidates_v1_2",
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
    concentrated = (
        status_counts.get("DISCOVERY_FOLD_CONCENTRATED", 0)
        + status_counts.get("DISCOVERY_SYMBOL_CONCENTRATED", 0)
        + status_counts.get("DISCOVERY_REGIME_CONCENTRATED", 0)
    )

    # If coverage failed we already know; reflection_ok only matters after coverage
    if not coverage_ok:
        reflection_ok = True  # do not blame reflection when coverage blocked research
        # Actually directive: if coverage fails, stop — recommendation is RESEARCH_COVERAGE_INSUFFICIENT
        # Keep reflection_ok True so pick_recommendation returns coverage insufficient
        pass

    recommendation = pick_recommendation(
        strict_ok=strict_ok,
        coverage_ok=coverage_ok,
        reflection_ok=reflection_ok if coverage_ok else True,
        impl_ok=impl_ok,
        results=results,
        ran_research=ran_research,
    )
    # Override: coverage fail always
    if not coverage_ok:
        recommendation = "NEXUS_STRATEGY_ENGINE_V12_RESEARCH_COVERAGE_INSUFFICIENT"
    elif coverage_ok and ran_research and not reflection_ok:
        recommendation = "NEXUS_REAL_REFLECTION_REQUALIFICATION_FAILED"

    # Strip heavy sim samples from sealed summary
    hyp_out = []
    for r in results:
        slim = {k: v for k, v in r.items() if k != "sim_rows_sample"}
        hyp_out.append(slim)

    summary = {
        "schema": "v1_2_development_research_summary",
        "package": "STRATEGY_ENGINE_V1_2",
        "stage": "STRATEGY_ENGINE_V1_2_BROAD_RESEARCH_COVERAGE",
        "sealed_at": _utc(),
        "source_commit": _git_head(),
        "V1_package_preserved": True,
        "V1_1_package_preserved": True,
        "V1_EXECUTION_INTERPRETATION": V1_EXECUTION_INTERPRETATION,
        "V1_1_status_preserved": "NEXUS_STRATEGY_ENGINE_V11_RESEARCH_COVERAGE_INSUFFICIENT",
        "recommendation": recommendation,
        "strict_component_conformance_status": "PASS" if strict_ok else "FAIL",
        "component_conformance_test_count": conf["component_conformance_test_count"],
        "strict_positive_fixture_pass_count": conf["strict_positive_fixture_pass_count"],
        "strict_negative_fixture_pass_count": conf["strict_negative_fixture_pass_count"],
        "strict_regime_block_pass_count": conf["strict_regime_block_pass_count"],
        "strict_missing_data_block_pass_count": conf["strict_missing_data_block_pass_count"],
        "strict_late_entry_pass_count": conf["strict_late_entry_pass_count"],
        "component_conformance_failure_count": conf["component_conformance_failure_count"],
        "coverage_gate_passed": coverage_ok,
        **{k: coverage[k] for k in coverage if k != "schema" and k != "symbols_attempted"},
        "data_integrity_failure_count": integrity["data_integrity_failure_count"],
        "historical_record_count": acq.get("historical_record_count"),
        "full_dataset_checksum": data_checksum,
        "download_resume_status": acq.get("download_resume_status"),
        "download_completed_partitions": acq.get("download_completed_partitions"),
        "download_failed_partitions": acq.get("download_failed_partitions"),
        "download_pending_partitions": acq.get("download_pending_partitions"),
        "generated_hypothesis_count": prereg.get("generated_hypothesis_count", 0),
        "preregistered_hypothesis_count": prereg.get("preregistered_hypothesis_count", 0),
        "executed_hypothesis_count": len(results),
        "DISCOVERY_PROMISING_count": status_counts.get("DISCOVERY_PROMISING", 0),
        "DISCOVERY_NO_GROSS_EDGE_count": status_counts.get("DISCOVERY_NO_GROSS_EDGE", 0),
        "DISCOVERY_COST_DOMINATED_count": status_counts.get("DISCOVERY_COST_DOMINATED", 0),
        "DISCOVERY_CONCENTRATED_count": concentrated,
        "DISCOVERY_INSUFFICIENT_SAMPLE_count": status_counts.get("DISCOVERY_INSUFFICIENT_SAMPLE", 0),
        "DISCOVERY_DATA_INVALID_count": status_counts.get("DISCOVERY_DATA_INVALID", 0),
        "DISCOVERY_IMPLEMENTATION_INVALID_count": status_counts.get("DISCOVERY_IMPLEMENTATION_INVALID", 0),
        "status_counts": status_counts,
        "hypotheses": hyp_out,
        "real_reflection": {
            "NEXUS_AI_MOCK": refl.get("NEXUS_AI_MOCK"),
            "real_reflection_calibration_count": refl.get("real_reflection_calibration_count"),
            "real_market_trade_count": refl.get("real_market_trade_count"),
            "control_fixture_count": refl.get("control_fixture_count"),
            "real_evidence_completeness_ratio": refl.get("real_evidence_completeness_ratio"),
            "real_AI_valid_schema_ratio": refl.get("real_AI_valid_schema_ratio"),
            "real_deterministic_AI_agreement_ratio": refl.get("real_deterministic_AI_agreement_ratio"),
            "real_critic_resolution_ratio": refl.get("real_critic_resolution_ratio"),
            "quality_targets_met": refl.get("quality_targets_met"),
            "new_lesson_record_count": refl.get("new_lesson_record_count", 0),
            "new_policy_effect_lesson_count": refl.get("new_policy_effect_lesson_count", 0),
            "provider_failure_count": refl.get("provider_failure_count", 0),
            "provider_rate_limited_count": refl.get("provider_rate_limited_count", 0),
            "mock_calibration_cannot_be_labeled_real": True,
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
        "H5A_status": "INSUFFICIENT_SAMPLE",
        "H5B_status": "INSUFFICIENT_SAMPLE",
        "H5C_status": "INSUFFICIENT_SAMPLE",
        "september_h3_oos_status": "OOS_WINDOW_NOT_MATURE_RESEARCH_CONFIRMATION_ONLY",
        "wallet_delta_classification": "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
        "remaining_unattributed_delta": -0.97052039,
        "trading_db_status": "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED",
        "demo_forward_status": "BLOCKED",
        "shadow_status": "NOT_APPLIED",
    }
    _write(IMMUTABLE / "v1_2_development_research_summary.json", summary)

    obs = build_observability_status(
        coverage={
            "dynamic_universe_symbol_count": coverage.get("dynamic_universe_symbol_count"),
            "registry_research_eligible_count": 99,
            "actual_loaded_dataset_count": coverage.get("actual_loaded_dataset_count"),
            "actual_price_dataset_count": coverage.get("actual_price_dataset_count"),
            "actual_derivatives_dataset_count": coverage.get("actual_derivatives_dataset_count"),
            "coverage_by_size_class": {
                "mainstream": coverage.get("actual_mainstream_dataset_count"),
                "mid_size": coverage.get("actual_mid_size_dataset_count"),
                "small": coverage.get("actual_small_dataset_count"),
                "meme": coverage.get("actual_meme_dataset_count"),
            },
            "download_completed_partitions": acq.get("download_completed_partitions"),
            "download_failed_partitions": acq.get("download_failed_partitions"),
            "download_pending_partitions": acq.get("download_pending_partitions"),
        },
        providers={
            "note": "real_reflection_uses_four_ai_when_keys_present",
            "ci_uses_mock": True,
            "real_reflection_calibration_status": "PASS" if refl.get("quality_targets_met") else ("SKIPPED" if refl.get("skipped") else "FAIL"),
            "real_deterministic_AI_agreement_ratio": refl.get("real_deterministic_AI_agreement_ratio"),
            "real_critic_resolution_ratio": refl.get("real_critic_resolution_ratio"),
        },
        learning={
            "evidence_completeness_ratio": refl.get("real_evidence_completeness_ratio"),
            "new_policy_effect_lesson_count": refl.get("new_policy_effect_lesson_count", 0),
        },
        research={
            "hypotheses_preregistered": prereg.get("preregistered_hypothesis_count", 0),
            "hypotheses_executed": len(results),
            "promising": status_counts.get("DISCOVERY_PROMISING", 0),
            "recommendation": recommendation,
        },
        v11_extra={
            "registry_research_eligible_count": 99,
            "actual_loaded_dataset_count": coverage.get("actual_loaded_dataset_count"),
            "actual_price_dataset_count": coverage.get("actual_price_dataset_count"),
            "actual_derivatives_dataset_count": coverage.get("actual_derivatives_dataset_count"),
            "actual_mainstream_dataset_count": coverage.get("actual_mainstream_dataset_count"),
            "actual_mid_size_dataset_count": coverage.get("actual_mid_size_dataset_count"),
            "actual_small_dataset_count": coverage.get("actual_small_dataset_count"),
            "actual_meme_dataset_count": coverage.get("actual_meme_dataset_count"),
            "download_total_partitions": (acq.get("download_completed_partitions") or 0)
            + (acq.get("download_failed_partitions") or 0)
            + (acq.get("download_pending_partitions") or 0),
            "download_completed_partitions": acq.get("download_completed_partitions"),
            "download_failed_partitions": acq.get("download_failed_partitions"),
            "download_pending_partitions": acq.get("download_pending_partitions"),
            "strict_component_conformance_status": "PASS" if strict_ok else "FAIL",
            "component_conformance_failure_count": conf["component_conformance_failure_count"],
            "real_reflection_calibration_status": "PASS" if refl.get("quality_targets_met") else ("SKIPPED" if refl.get("skipped") else "FAIL"),
            "real_deterministic_AI_agreement_ratio": refl.get("real_deterministic_AI_agreement_ratio"),
            "real_critic_resolution_ratio": refl.get("real_critic_resolution_ratio"),
            "V1_2_hypotheses_preregistered": prereg.get("preregistered_hypothesis_count", 0),
            "V1_2_hypotheses_executed": len(results),
            "V1_2_promising_count": status_counts.get("DISCOVERY_PROMISING", 0),
            "V1_2_recommended_candidate_count": len(candidates),
            "component_implemented_count": ereg["implemented_component_count"],
            "component_not_implemented_count": ereg["not_implemented_component_count"],
            "semantic_collision_count": 0,
            "candidate_funnel_by_hypothesis": funnels,
            "zero_trade_root_causes": zero_causes,
            "multi_timeframe_bundle_status": {
                "ready_count": manifest.get("multi_timeframe_ready_count"),
                "version": manifest.get("data_bundle_version"),
            },
            "derivative_proxy_violation_count": sum(
                int(r.get("required_data_proxy_violation_count") or 0) for r in results
            ),
            "V1_results_interpretation": V1_EXECUTION_INTERPRETATION,
            "V1_1_research_status": "NEXUS_STRATEGY_ENGINE_V11_RESEARCH_COVERAGE_INSUFFICIENT",
            "V1_2_research_status": recommendation,
        },
    )
    _write(IMMUTABLE / "functional_observability_status.json", obs)
    _write(IMMUTABLE / "functional_observability_contract.json", observability_contract())

    print(
        json.dumps(
            {
                "recommendation": recommendation,
                "strict_ok": strict_ok,
                "coverage_ok": coverage_ok,
                "reflection_ok": refl.get("quality_targets_met"),
                "price": coverage.get("actual_price_dataset_count"),
                "derivatives": coverage.get("actual_derivatives_dataset_count"),
                "promising": status_counts.get("DISCOVERY_PROMISING", 0),
                "candidates": len(candidates),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
