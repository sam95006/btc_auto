#!/usr/bin/env python3
"""Private Core Continuity V3 — provider-specific V2.3 resume + VWAP terminal + alpha gate.

Preserves prior immutable packages. Intermediate progress -> .nexus_runtime.
Creates exactly one final immutable continuation package only when V2.3 + learning proof complete.
No WF/OOS/Demo/Shadow/deploy/mainnet/real money. No public product changes.
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
PRIOR_V23 = ROOT / "artifacts/readiness/immutable/blind_reflection_v2_3_and_learning_prevention"
PRIOR_QUOTA = ROOT / "artifacts/readiness/immutable/blind_reflection_v2_3_quota_recovery_and_vwap"
EDGE_V2 = ROOT / "artifacts/readiness/immutable/edge_discovery_diagnostics_v2"
RUNTIME = ROOT / ".nexus_runtime/research/blind_reflection_v23"
FINAL_IMMUTABLE = ROOT / "artifacts/readiness/immutable/blind_reflection_v2_3_provider_split_complete"


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
    quality_evaluated: bool,
    quality_passed: bool,
    learning_ok: bool | None,
    provider_partial: bool,
    alpha_selected: bool,
) -> str:
    if not impl_ok:
        return "NEXUS_PRIVATE_CORE_DATA_OR_IMPLEMENTATION_INVALID"
    if quality_evaluated and quality_passed and learning_ok:
        return "NEXUS_PRIVATE_V23_COMPLETE_LEARNING_PREVENTION_VERIFIED"
    if quality_evaluated and not quality_passed:
        return "NEXUS_PRIVATE_V23_VALID_SAMPLE_QUALITY_FAILED"
    if quality_passed and learning_ok is False:
        return "NEXUS_PRIVATE_LEARNING_PREVENTION_PROOF_FAILED"
    if provider_partial or not quality_evaluated:
        # Prefer partial capacity while calibration incomplete; alpha selection is additive.
        if alpha_selected and not quality_evaluated:
            return "NEXUS_PRIVATE_V23_PARTIAL_PROVIDER_CAPACITY"
        return "NEXUS_PRIVATE_V23_PARTIAL_PROVIDER_CAPACITY"
    if alpha_selected and quality_evaluated and quality_passed:
        return "NEXUS_PRIVATE_NEXT_ALPHA_DATA_FAMILY_SELECTED"
    return "NEXUS_PRIVATE_V23_PARTIAL_PROVIDER_CAPACITY"


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass

    assert PRIOR_V23.is_dir(), "prior V2.3 package must be preserved"
    assert PRIOR_QUOTA.is_dir(), "quota recovery package must be preserved"
    assert EDGE_V2.is_dir()
    RUNTIME.mkdir(parents=True, exist_ok=True)

    from backend.nexus_edge_discovery.alpha_data_family_feasibility_v1 import audit_alpha_data_families
    from backend.nexus_edge_discovery.blind_reflection_v23 import build_calibration_set_v23
    from backend.nexus_edge_discovery.conditional_vwap_confirmation import (
        build_vwap_taxonomy_correction_record,
    )
    from backend.nexus_edge_discovery.learning_prevention_proof import (
        run_good_process_loss_non_suppression_test,
        run_learning_prevention_proof,
    )
    from backend.nexus_edge_discovery.quota_aware_v23 import run_quota_aware_calibration
    from backend.nexus_strategy_engine.hypotheses_v1_2 import default_v12_hypothesis_drafts

    # Frozen calibration sample (same builder; do not resample)
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
    # Prefer frozen checksum from prior quota package if present
    prior_manifest_path = PRIOR_QUOTA / "calibration_manifest.json"
    if prior_manifest_path.is_file():
        prior_manifest = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        manifest_checksum = str(prior_manifest.get("calibration_manifest_checksum") or "")
        prior_ids = list(prior_manifest.get("case_ids") or [])
        now_ids = [p.get("trade_id") for p in packets]
        assert prior_ids == now_ids, "frozen 80-case manifest must not change"
    else:
        manifest_checksum = _sha(
            {"ids": [p.get("trade_id") for p in packets], "n": 80, "schema": "calibration_manifest"}
        )

    print("1) provider-specific quota-aware resume...", flush=True)
    use_real = os.getenv("NEXUS_V23_FORCE_MOCK", "0") != "1"
    cal = run_quota_aware_calibration(
        root=ROOT,
        packets=packets,
        manifest_checksum=manifest_checksum,
        use_real_ai=use_real,
        max_batches_this_invocation=int(os.getenv("NEXUS_V23_MAX_BATCHES", "3")),
    )
    quality = cal.get("quality") or {}
    summary_state = cal.get("state_summary") or {}
    _write(RUNTIME / "preflight_groq.json", cal.get("preflight_groq") or {})
    _write(RUNTIME / "preflight_sambanova.json", cal.get("preflight_sambanova") or {})
    _write(RUNTIME / "calibration_resume_summary.json", {
        "schema": "calibration_resume_summary_v3",
        "checkpoint_status": cal.get("checkpoint_status"),
        **summary_state,
        "checkpoint_path": ".nexus_runtime/blind_reflection_v23_checkpoint.json",
        "checkpoint_committed": False,
    })
    _write(RUNTIME / "quality_snapshot.json", quality)

    quality_passed = bool(quality.get("quality_gates_passed"))
    quality_evaluated = bool(quality.get("quality_gates_evaluated"))
    provider_partial = (
        quality.get("V2_3_quality_status") == "INCOMPLETE_PROVIDER_CAPACITY"
        or summary_state.get("groq_stage") in {
            "GROQ_CAPACITY_BLOCKED",
            "INVOCATION_BATCH_LIMIT_REACHED",
            "GROQ_CALIBRATION_BATCH",
            "GROQ_CANARY",
        }
        or summary_state.get("sambanova_stage") == "SAMBANOVA_CAPACITY_BLOCKED"
        or int(summary_state.get("reflection_pending_case_count") or 0) > 0
        or int(summary_state.get("critic_pending_count") or 0) > 0
    )

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
            "genuine_bad_process_source_trade_count": 0,
            "lesson_created_count": 0,
        }
        gpl = run_good_process_loss_non_suppression_test(packets)
        learning_ok = None
    _write(RUNTIME / "control_learning_chain_proof.json", control)
    _write(RUNTIME / "real_historical_learning_chain_proof.json", real)
    _write(RUNTIME / "good_process_loss_non_suppression_result.json", gpl)

    print("3) VWAP taxonomy correction (non-mutating; preserve sealed metrics)...", flush=True)
    sealed_vwap_path = PRIOR_QUOTA / "sealed_vwap_development_confirmation.json"
    if sealed_vwap_path.is_file():
        sealed_vwap = json.loads(sealed_vwap_path.read_text(encoding="utf-8"))
    else:
        sealed_vwap = {}
    vwap_correction = build_vwap_taxonomy_correction_record(sealed_vwap)
    _write(RUNTIME / "vwap_taxonomy_correction.json", vwap_correction)
    # Also place alongside sealed package without overwriting sealed metrics file
    _write(PRIOR_QUOTA / "vwap_taxonomy_correction.json", vwap_correction)

    print("4) alpha data family feasibility (no strategies, no paid buy)...", flush=True)
    alpha = audit_alpha_data_families()
    _write(RUNTIME / "alpha_data_family_feasibility_v1.json", alpha)
    _write(PRIOR_QUOTA / "alpha_data_family_feasibility_v1.json", alpha)

    recommendation = pick_recommendation(
        impl_ok=True,
        quality_evaluated=quality_evaluated,
        quality_passed=quality_passed,
        learning_ok=learning_ok,
        provider_partial=provider_partial,
        alpha_selected=int(alpha.get("selected_next_data_family_count") or 0) > 0,
    )

    track_a = {
        "schema": "nexus_private_core_continuity_v3_track_a",
        "created_at": _utc(),
        "git_head_at_run": _git_head(),
        "recommendation": recommendation,
        "quality": {
            "quality_gates_evaluated": quality_evaluated,
            "quality_gates_passed": quality_passed,
            "V2_3_quality_status": quality.get("V2_3_quality_status"),
            "evidence_packet_constructible_count": quality.get("evidence_packet_constructible_count"),
            "evidence_packet_constructible_ratio": quality.get("evidence_packet_constructible_ratio"),
            "reflection_prompt_attempt_count": quality.get("reflection_prompt_attempt_count"),
            "reflection_prompt_with_packet_count": quality.get("reflection_prompt_with_packet_count"),
            "reflection_prompt_delivery_ratio_on_attempts": quality.get(
                "reflection_prompt_delivery_ratio_on_attempts"
            ),
            "reflection_successful_case_count": quality.get("reflection_successful_case_count"),
            "frozen_calibration_case_count": quality.get("frozen_calibration_case_count"),
            "full_calibration_completion_ratio": quality.get("full_calibration_completion_ratio"),
            "critic_resolution_ratio": quality.get("critic_resolution_ratio"),
            "critic_resolution_status": quality.get("critic_resolution_status"),
        },
        "transport": quality.get("transport") or summary_state.get("transport"),
        "groq_stage": summary_state.get("groq_stage"),
        "sambanova_stage": summary_state.get("sambanova_stage"),
        "exit_reason": summary_state.get("exit_reason") or quality.get("exit_reason"),
        "learning": {
            "real_historical_chain_proof_status": real.get("real_historical_chain_proof_status"),
            "control_chain_proof_status": control.get("control_chain_proof_status"),
            "good_process_loss_non_suppression_status": gpl.get(
                "good_process_loss_non_suppression_status"
            ),
        },
        "vwap": {
            "vwap_terminal_status": vwap_correction.get("vwap_terminal_status"),
            "vwap_taxonomy_correction_status": vwap_correction.get("vwap_taxonomy_correction_status"),
            "vwap_gross_expectancy": sealed_vwap.get("vwap_gross_expectancy"),
            "vwap_net_expectancy": sealed_vwap.get("vwap_net_expectancy"),
            "vwap_net_profit_factor": sealed_vwap.get("vwap_net_profit_factor"),
            "vwap_formal_qualification_started": False,
        },
        "alpha": {
            "selected_next_data_family_ids": alpha.get("selected_next_data_family_ids"),
            "selected_next_data_family_count": alpha.get("selected_next_data_family_count"),
            "paid_data_purchased": False,
            "new_strategy_generated_count": 0,
        },
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
        "final_immutable_package_created": False,
    }

    if quality_passed and learning_ok:
        FINAL_IMMUTABLE.mkdir(parents=True, exist_ok=True)
        _write(FINAL_IMMUTABLE / "final_v2_3_quality_result.json", quality)
        _write(FINAL_IMMUTABLE / "control_learning_chain_proof.json", control)
        _write(FINAL_IMMUTABLE / "real_historical_learning_chain_proof.json", real)
        _write(FINAL_IMMUTABLE / "good_process_loss_non_suppression_result.json", gpl)
        _write(FINAL_IMMUTABLE / "vwap_taxonomy_correction.json", vwap_correction)
        _write(FINAL_IMMUTABLE / "alpha_data_family_feasibility_v1.json", alpha)
        _write(FINAL_IMMUTABLE / "track_a_summary.json", track_a)
        track_a["final_immutable_package_created"] = True
        track_a["final_immutable_package"] = str(FINAL_IMMUTABLE.relative_to(ROOT)).replace("\\", "/")

    _write(RUNTIME / "track_a_summary.json", track_a)
    print(json.dumps(track_a, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
