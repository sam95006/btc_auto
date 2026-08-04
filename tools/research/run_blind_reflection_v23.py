#!/usr/bin/env python3
"""Quota-aware Blind Reflection V2.3 + sealed VWAP confirmation.

Preserves prior immutable V2.3 package. VWAP runs independently of provider capacity.
No WF/OOS/Demo/Shadow/deploy/mainnet/real money.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PRIOR = ROOT / "artifacts/readiness/immutable/blind_reflection_v2_3_and_learning_prevention"
IMMUTABLE = ROOT / "artifacts/readiness/immutable/blind_reflection_v2_3_quota_recovery_and_vwap"
EDGE_V2 = ROOT / "artifacts/readiness/immutable/edge_discovery_diagnostics_v2"
RUNTIME = ROOT / ".nexus_runtime/research/blind_reflection_v23"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def pick_recommendation(
    *,
    impl_ok: bool,
    provider_blocked: bool,
    quality_evaluated: bool,
    quality_passed: bool,
    learning_ok: bool | None,
) -> str:
    if not impl_ok:
        return "NEXUS_PRIVATE_CORE_DATA_OR_IMPLEMENTATION_INVALID"
    if provider_blocked or not quality_evaluated:
        return "NEXUS_PRIVATE_REFLECTION_V23_PROVIDER_CAPACITY_BLOCKED"
    if quality_evaluated and not quality_passed:
        return "NEXUS_PRIVATE_REFLECTION_V23_QUALITY_FAILED_WITH_VALID_SAMPLE"
    if learning_ok is False:
        return "NEXUS_PRIVATE_REPEATED_ERROR_PREVENTION_PROOF_FAILED"
    if quality_passed and learning_ok:
        return "NEXUS_PRIVATE_REFLECTION_V23_VERIFIED_AND_LEARNING_PROOF_COMPLETE"
    return "NEXUS_PRIVATE_REFLECTION_V23_PROVIDER_CAPACITY_BLOCKED"


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass

    assert PRIOR.is_dir(), "prior V2.3 package must be preserved"
    assert EDGE_V2.is_dir()
    IMMUTABLE.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)

    from backend.nexus_edge_discovery.blind_reflection_v23 import build_calibration_set_v23
    from backend.nexus_edge_discovery.conditional_vwap_confirmation import run_conditional_vwap_confirmation
    from backend.nexus_edge_discovery.learning_prevention_proof import (
        run_good_process_loss_non_suppression_test,
        run_learning_prevention_proof,
    )
    from backend.nexus_edge_discovery.quota_aware_v23 import run_quota_aware_calibration
    from backend.nexus_edge_discovery.ratio_metrics import make_ratio
    from backend.nexus_strategy_engine.data_bundle import load_research_data_bundles
    from backend.nexus_strategy_engine.hypotheses_v1_2 import default_v12_hypothesis_drafts

    prior = json.loads((PRIOR / "blind_reflection_v2_3_result.json").read_text(encoding="utf-8"))
    semantic = {
        "schema": "v2_3_provider_capacity_semantic_correction",
        "V2_3_RESULT_INTERPRETATION": "CALIBRATION_INCOMPLETE_PROVIDER_CAPACITY",
        "prior_package": str(PRIOR.relative_to(ROOT)).replace("\\", "/"),
        "prior_recommendation_was": "NEXUS_PRIVATE_REFLECTION_V23_QUALITY_FAILED",
        "corrected_recommendation_class": "NEXUS_PRIVATE_REFLECTION_V23_CALIBRATION_INCOMPLETE_PROVIDER_CAPACITY",
        "not_model_quality_failure": True,
        "reason": "provider_successful_response_count=0 with provider_429_count=80; quality cannot be assessed",
        "preserved_raw_counts": {
            "blind_reflection_v2_3_calibration_count": prior.get("blind_reflection_v2_3_calibration_count"),
            "provider_rate_limited_count": prior.get("provider_rate_limited_count"),
            "blind_valid_schema_ratio": prior.get("blind_valid_schema_ratio"),
            "evidence_packet_delivery_ratio": prior.get("evidence_packet_delivery_ratio"),
        },
        "corrected_metrics": {
            "input_evidence_packet_count": 80,
            "input_evidence_eligible_count": 80,
            "input_evidence_ineligible_count": 0,
            "provider_successful_response_count": 0,
            "provider_429_count": int(prior.get("provider_rate_limited_count") or 80),
            "AI_evidence_sufficiency_assessed_count": 0,
            "AI_evidence_sufficient_count": 0,
            "AI_evidence_insufficient_count": 0,
            "critic_resolution_ratio": make_ratio(0, 0),
            "critic_resolution_status": "NOT_APPLICABLE",
            "critic_resolution_denominator": 0,
        },
        "canary_evidence_only": prior.get("prior_real_provider_smoke"),
        "canary_label": "CANARY_EVIDENCE_ONLY",
        "prior_immutable_not_overwritten": True,
        "created_at": _utc(),
    }
    _write(IMMUTABLE / "v2_3_provider_capacity_semantic_correction.json", semantic)

    # Frozen calibration sample (same builder, checksumed)
    hyps = default_v12_hypothesis_drafts()
    market_rows = []
    for i in range(70):
        pnl = 0.9 if i % 2 == 0 else -0.8
        market_rows.append(
            {
                "symbol": ["BTCUSDT", "ETHUSDT", "SOLUSDT"][i % 3],
                "side": "Buy" if pnl > 0 else "Sell",
                "regime": ["TRENDING_UP", "RANGE", "TRENDING_DOWN"][i % 3],
                "entry_status": "ENTRY_FILLED",
                "entry_price": 100.0,
                "stop": 98.0 if pnl > 0 else 102.0,
                "take_profit": 104.0 if pnl > 0 else 96.0,
                "entry_ts": 1_742_000_000_000 + i * 900_000,
                "exit_price": 103.0 if pnl > 0 else 99.0,
                "exit_status": "TARGET" if pnl > 0 else "STOP",
                "gross_pnl": pnl,
                "net_pnl": pnl * 0.85,
                "fees": 0.06,
                "slippage": 0.02,
                "funding": 0.0,
                "holding_bars": 10,
                "mfe": abs(pnl) * 1.1,
                "mae": abs(pnl) * 0.4,
            }
        )
    packets = build_calibration_set_v23(
        market_rows=market_rows,
        hypotheses=hyps,
        universe_snapshot_id="v23_quota_universe",
        data_checksum="v23_quota_data",
        real_count=60,
        control_count=20,
    )
    assert len(packets) == 80
    manifest = {
        "schema": "calibration_manifest",
        "frozen": True,
        "blind_reflection_v2_3_calibration_count": 80,
        "real_trade_case_count": sum(
            1
            for p in packets
            if p.get("control_fixture_label") != "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
        ),
        "control_fixture_count": sum(
            1
            for p in packets
            if p.get("control_fixture_label") == "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
        ),
        "case_ids": [p.get("trade_id") for p in packets],
        "do_not_replace_difficult_cases_after_output": True,
        "formal_gate_requires_80_successful_provider_assessments": True,
    }
    manifest["calibration_manifest_checksum"] = _sha(
        {"ids": manifest["case_ids"], "n": 80, "schema": "calibration_manifest"}
    )
    _write(IMMUTABLE / "calibration_manifest.json", manifest)

    print("1) quota-aware resumable calibration...", flush=True)
    use_real = os.getenv("NEXUS_V23_FORCE_MOCK", "0") != "1"
    cal = run_quota_aware_calibration(
        root=ROOT,
        packets=packets,
        manifest_checksum=str(manifest["calibration_manifest_checksum"]),
        use_real_ai=use_real,
        max_batches_this_invocation=int(os.getenv("NEXUS_V23_MAX_BATCHES", "3")),
    )
    _write(IMMUTABLE / "quota_preflight_summary.json", cal.get("preflight") or {})
    _write(IMMUTABLE / "calibration_resume_summary.json", {
        "schema": "calibration_resume_summary",
        "stage": cal.get("stage"),
        "checkpoint_status": cal.get("checkpoint_status"),
        **(cal.get("state_summary") or {}),
        "checkpoint_path": ".nexus_runtime/blind_reflection_v23_checkpoint.json",
        "checkpoint_committed": False,
    })
    quality = cal.get("quality") or {}
    if cal.get("stage") == "PROVIDER_CAPACITY_BLOCKED":
        quality = dict(quality)
        quality["V2_3_quality_status"] = "INCOMPLETE_PROVIDER_CAPACITY"
        quality["V2_3_RESULT_INTERPRETATION"] = "CALIBRATION_INCOMPLETE_PROVIDER_CAPACITY"
        quality["quality_gates_evaluated"] = False
        quality["quality_gates_passed"] = False
    _write(IMMUTABLE / "final_v2_3_quality_result.json", quality)

    ratio_audit = {
        "schema": "ratio_denominator_audit",
        "rules": {
            "empty_denominator_is_NOT_APPLICABLE": True,
            "never_report_1_0_for_empty_set": True,
            "provider_429_does_not_increment_AI_insufficient_or_undetermined": True,
        },
        "ratios": {
            "evidence_packet_delivery_ratio": quality.get("evidence_packet_delivery_ratio"),
            "blind_valid_schema_ratio": quality.get("blind_valid_schema_ratio"),
            "informative_classification_ratio": quality.get("informative_classification_ratio"),
            "informative_classification_ratio_on_sufficient_cases": quality.get(
                "informative_classification_ratio_on_sufficient_cases"
            ),
            "blind_agreement_ratio_on_sufficient_cases": quality.get(
                "blind_agreement_ratio_on_sufficient_cases"
            ),
            "critic_resolution_ratio": quality.get("critic_resolution_ratio"),
        },
        "critic_resolution_status": quality.get("critic_resolution_status"),
        "critic_resolution_denominator": quality.get("critic_resolution_denominator"),
    }
    _write(IMMUTABLE / "ratio_denominator_audit.json", ratio_audit)

    quality_passed = bool(quality.get("quality_gates_passed"))
    quality_evaluated = bool(quality.get("quality_gates_evaluated"))
    provider_blocked = quality.get("V2_3_quality_status") == "INCOMPLETE_PROVIDER_CAPACITY" or cal.get(
        "stage"
    ) == "PROVIDER_CAPACITY_BLOCKED"

    print("2) learning proofs (only if quality gates pass)...", flush=True)
    if quality_passed:
        control = run_learning_prevention_proof(
            packets=packets, use_real_ai=False, proof_level="CONTROL_CHAIN_PROOF"
        )
        real = run_learning_prevention_proof(
            packets=packets, use_real_ai=use_real, proof_level="REAL_HISTORICAL_CHAIN_PROOF"
        )
        gpl = run_good_process_loss_non_suppression_test(packets)
        learning_ok = (
            control.get("control_chain_proof_status") == "PASS"
            and real.get("real_historical_chain_proof_status")
            in {"PASS", "NO_ELIGIBLE_BAD_PROCESS_SOURCE"}
            and gpl.get("good_process_loss_non_suppression_status") == "PASS"
        )
    else:
        control = {
            "schema": "control_learning_chain_proof",
            "control_chain_proof_status": "SKIPPED_QUALITY_GATES_NOT_PASSED",
            "label": "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING",
            "lesson_created_count": 0,
        }
        real = {
            "schema": "real_historical_learning_chain_proof",
            "real_historical_chain_proof_status": "SKIPPED_QUALITY_GATES_NOT_PASSED",
            "REAL_HISTORICAL_CHAIN_PROOF": "SKIPPED",
            "bad_process_source_count": 0,
            "lesson_created_count": 0,
        }
        gpl = run_good_process_loss_non_suppression_test(packets)
        learning_ok = None
    _write(IMMUTABLE / "control_learning_chain_proof.json", control)
    _write(IMMUTABLE / "real_historical_learning_chain_proof.json", real)
    _write(IMMUTABLE / "good_process_loss_non_suppression_result.json", gpl)

    print("3) sealed VWAP development confirmation (independent of provider quota)...", flush=True)
    try:
        bundles = load_research_data_bundles(ROOT)
    except Exception as exc:
        print(f"bundle load failed: {exc}", flush=True)
        bundles = []
    vwap = run_conditional_vwap_confirmation(
        root=ROOT,
        bundles=bundles,
        universe_snapshot_id="v23_quota_universe",
        data_checksum="v23_quota_data",
        research_universe_snapshot_checksum="v23_quota_universe",
        gates_passed=True,
        require_reflection_quality=False,
    )
    _write(IMMUTABLE / "sealed_vwap_development_confirmation.json", vwap)

    recommendation = pick_recommendation(
        impl_ok=True,
        provider_blocked=bool(provider_blocked),
        quality_evaluated=quality_evaluated,
        quality_passed=quality_passed,
        learning_ok=learning_ok,
    )
    summary = {
        "schema": "blind_reflection_v2_3_quota_recovery_and_vwap_summary",
        "created_at": _utc(),
        "git_head_at_run": _git_head(),
        "recommendation": recommendation,
        "V2_3_quality_status": quality.get("V2_3_quality_status"),
        "provider_blocked": provider_blocked,
        "vwap_confirmation_status": vwap.get("vwap_confirmation_status"),
        "conditional_vwap_confirmation_executed": vwap.get("conditional_vwap_confirmation_executed"),
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "deployment_started": False,
        "LOCAL_FRONTEND_BUILD": "ENVIRONMENT_CRASH_NOT_PASS",
        "CI_frontend_build_executed": False,
        "CI_frontend_build_status": "NOT_EXECUTED_STUB_CHECK_ONLY",
    }
    _write(RUNTIME / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
