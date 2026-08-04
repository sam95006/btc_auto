"""Tests for quota-aware V2.3 Continuity V3: delivery metrics + provider split."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_edge_discovery.alpha_data_family_feasibility_v1 import audit_alpha_data_families
from backend.nexus_edge_discovery.blind_reflection_v23 import (
    build_calibration_set_v23,
    migrate_process_classification,
)
from backend.nexus_edge_discovery.conditional_vwap_confirmation import (
    build_vwap_taxonomy_correction_record,
)
from backend.nexus_edge_discovery.learning_prevention_proof import (
    run_good_process_loss_non_suppression_test,
    run_learning_prevention_proof,
)
from backend.nexus_edge_discovery.quota_aware_v23 import (
    build_delivery_metrics,
    build_initial_checkpoint,
    evaluate_quality,
    migrate_checkpoint_v2_to_v3,
    run_quota_aware_calibration,
    save_checkpoint,
)
from backend.nexus_edge_discovery.ratio_metrics import make_ratio


def _packets():
    rows = []
    for i in range(70):
        pnl = 1.0 if i % 2 == 0 else -0.9
        rows.append(
            {
                "symbol": ["BTCUSDT", "ETHUSDT", "SOLUSDT"][i % 3],
                "side": "Buy" if pnl > 0 else "Sell",
                "regime": ["TRENDING_UP", "RANGE", "TRENDING_DOWN"][i % 3],
                "entry_status": "ENTRY_FILLED",
                "entry_price": 100.0,
                "stop": 98.0 if pnl > 0 else 102.0,
                "take_profit": 104.0 if pnl > 0 else 96.0,
                "entry_ts": 1_750_000_000_000 + i * 900_000,
                "exit_price": 103.0 if pnl > 0 else 99.0,
                "exit_status": "TARGET" if pnl > 0 else "STOP",
                "gross_pnl": pnl,
                "net_pnl": pnl * 0.9,
                "fees": 0.05,
                "slippage": 0.02,
                "funding": 0.0,
                "holding_bars": 8,
                "mfe": abs(pnl) * 1.2,
                "mae": abs(pnl) * 0.4,
            }
        )
    hyps = [
        {
            "strategy_id": "V12_H01",
            "hypothesis_id": "V12_H01",
            "strategy_family": "TREND",
            "component_id": "TREND_CONTINUATION",
            "event_definition": "x",
            "stop_definition": "atr",
            "target_definition": "rr",
        }
    ]
    return build_calibration_set_v23(
        market_rows=rows,
        hypotheses=hyps,
        universe_snapshot_id="u",
        data_checksum="d",
    )


def test_zero_denominator_not_one():
    r = make_ratio(0, 0)
    assert r["status"] == "NOT_APPLICABLE"
    assert r["value"] is None
    assert r["denominator"] == 0


def test_constructible_not_provider_delivery_completion():
    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="x", model_id="m")
    # 10 completed with packet; 70 pending must not count as delivered
    for i, cid in enumerate(state["case_ids"][:10]):
        state["completed_case_ids"].append(cid)
        state["pending_case_ids"] = [x for x in state["pending_case_ids"] if x != cid]
        state["case_results"][cid] = {
            "reflection_prompt_with_packet": True,
            "evidence_packet_constructible": True,
            "evidence_sufficiency": "EVIDENCE_SUFFICIENT",
            "process_classification": "GOOD_PROCESS_WIN",
            "deterministic_expected": "GOOD_PROCESS_WIN",
        }
    state["transport"]["GROQ_REFLECTION_REASONER"]["attempt_count"] = 10
    state["reflection_prompt_with_packet_count"] = 10
    delivery = build_delivery_metrics(state)
    assert delivery["evidence_packet_constructible_ratio"]["value"] == 1.0
    assert delivery["reflection_prompt_delivery_ratio_on_attempts"]["value"] == 1.0
    assert delivery["full_calibration_completion_ratio"]["numerator"] == 10
    assert delivery["full_calibration_completion_ratio"]["denominator"] == 80
    assert delivery["full_calibration_completion_ratio"]["status"] == "INCOMPLETE_SAMPLE"
    # pending not delivered
    assert delivery["reflection_successful_case_count"] == 10
    q = evaluate_quality(state)
    assert q["provider_successful_response_count"] == 10
    assert q["quality_gates_evaluated"] is False


def test_sambanova_block_not_ordinary_valid_critic_ratio():
    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="x", model_id="m")
    state["completed_case_ids"] = state["case_ids"][:10]
    state["pending_case_ids"] = state["case_ids"][10:]
    state["critic_case_ids"] = state["case_ids"][:5]
    state["critic_pending_ids"] = list(state["critic_case_ids"])
    state["critic_resolved_ids"] = []
    state["sambanova_stage"] = "SAMBANOVA_CAPACITY_BLOCKED"
    state["transport"]["SAMBANOVA_INDEPENDENT_CRITIC"]["HTTP_429_count"] = 1
    state["transport"]["SAMBANOVA_INDEPENDENT_CRITIC"]["last_exit_reason"] = "PROVIDER_RATE_LIMITED"
    for cid in state["completed_case_ids"]:
        state["case_results"][cid] = {
            "reflection_prompt_with_packet": True,
            "evidence_sufficiency": "EVIDENCE_SUFFICIENT",
            "process_classification": "GOOD_PROCESS_WIN",
            "deterministic_expected": "BAD_PROCESS_WIN",
        }
    q = evaluate_quality(state)
    assert q["critic_resolution_status"] == "SAMBANOVA_PROVIDER_BLOCKED"
    assert q["critic_resolution_ratio"]["status"] == "SAMBANOVA_PROVIDER_BLOCKED"
    assert q["critic_resolution_ratio"]["value"] is None


def test_groq_sambanova_counters_independent(tmp_path: Path):
    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="ind", model_id="m")
    state["transport"]["GROQ_REFLECTION_REASONER"]["HTTP_429_count"] = 0
    state["transport"]["SAMBANOVA_INDEPENDENT_CRITIC"]["HTTP_429_count"] = 3
    assert state["transport"]["GROQ_REFLECTION_REASONER"]["HTTP_429_count"] != state["transport"][
        "SAMBANOVA_INDEPENDENT_CRITIC"
    ]["HTTP_429_count"]
    # migration: SambaNova block must not erase Groq completed
    v2 = {
        "schema_version": 2,
        "calibration_manifest_checksum": "ind",
        "case_ids": state["case_ids"],
        "completed_case_ids": state["case_ids"][:10],
        "pending_case_ids": state["case_ids"][10:],
        "critic_case_ids": state["case_ids"][:5],
        "critic_resolved_ids": [],
        "case_results": {},
        "provider_429_count": 0,
        "provider_attempt_counts": {"GROQ_REFLECTION_REASONER": 10},
        "provider_success_counts": {"GROQ_REFLECTION_REASONER": 10},
        "stage": "PROVIDER_CAPACITY_BLOCKED",
        "retry_after": 900,
        "next_resume_not_before": "2099-01-01T00:00:00Z",
    }
    migrated = migrate_checkpoint_v2_to_v3(v2, model_id="m")
    assert len(migrated["completed_case_ids"]) == 10
    assert migrated["transport"]["GROQ_REFLECTION_REASONER"]["HTTP_429_count"] == 0
    assert migrated["sambanova_stage"] == "SAMBANOVA_CAPACITY_BLOCKED"
    assert migrated["groq_stage"] == "GROQ_CALIBRATION_BATCH"
    assert migrated["transport"]["GROQ_REFLECTION_REASONER"]["next_resume_not_before"] is None


def test_batch_limit_not_rate_limit(tmp_path: Path):
    packets = _packets()
    out = run_quota_aware_calibration(
        root=tmp_path,
        packets=packets,
        manifest_checksum="batch_lim",
        use_real_ai=False,
        max_batches_this_invocation=1,
        run_critic=False,
    )
    assert out["state_summary"]["exit_reason"] in {
        "INVOCATION_BATCH_LIMIT_REACHED",
        None,
    } or out["state_summary"]["groq_stage"] in {
        "INVOCATION_BATCH_LIMIT_REACHED",
        "GROQ_CANARY",
        "GROQ_CALIBRATION_BATCH",
        "GROQ_COMPLETE",
    }
    # Must not invent Groq 429 from batch limit
    assert out["state_summary"]["transport"]["GROQ_REFLECTION_REASONER"]["HTTP_429_count"] == 0
    if out["state_summary"]["exit_reason"] == "INVOCATION_BATCH_LIMIT_REACHED":
        assert out["state_summary"]["transport"]["GROQ_REFLECTION_REASONER"][
            "HTTP_429_count"
        ] == 0


def test_completed_cases_not_repeated(tmp_path: Path):
    packets = _packets()
    out1 = run_quota_aware_calibration(
        root=tmp_path,
        packets=packets,
        manifest_checksum="norepeat",
        use_real_ai=False,
        max_batches_this_invocation=20,
    )
    n1 = out1["quality"]["reflection_successful_case_count"]
    assert n1 == 80
    groq_attempts_1 = out1["state_summary"]["transport"]["GROQ_REFLECTION_REASONER"]["attempt_count"]
    out2 = run_quota_aware_calibration(
        root=tmp_path,
        packets=packets,
        manifest_checksum="norepeat",
        use_real_ai=False,
        max_batches_this_invocation=2,
    )
    groq_attempts_2 = out2["state_summary"]["transport"]["GROQ_REFLECTION_REASONER"]["attempt_count"]
    assert out2["quality"]["reflection_successful_case_count"] == 80
    assert groq_attempts_2 == groq_attempts_1


def test_undetermined_migration_preserves_provenance():
    assert migrate_process_classification("UNDETERMINED_PROCESS") == "UNDETERMINED"


def test_quality_not_evaluated_before_denominators():
    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="x", model_id="m")
    q = evaluate_quality(state)
    assert q["quality_gates_evaluated"] is False
    assert q["quality_gates_passed"] is False


def test_disagreement_not_auto_ai_error():
    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="x", model_id="m")
    cid = state["case_ids"][0]
    state["completed_case_ids"] = [cid]
    state["pending_case_ids"] = state["case_ids"][1:]
    state["case_results"][cid] = {
        "reflection_prompt_with_packet": True,
        "evidence_sufficiency": "EVIDENCE_SUFFICIENT",
        "process_classification": "GOOD_PROCESS_WIN",
        "deterministic_expected": "BAD_PROCESS_WIN",
        "supporting_evidence_ids": ["e1"],
        "critic_verdict": None,
    }
    q = evaluate_quality(state)
    assert q["disagreement_case_count"] == 1
    assert q["AI_misclassification_count"] == 0
    assert q["critic_unresolved_count"] == 1


def test_vwap_positive_gross_negative_net_cost_destroyed():
    sealed = {
        "schema": "conditional_vwap_confirmation",
        "vwap_confirmation_status": "VWAP_DEVELOPMENT_COST_DESTROYED",
        "vwap_gross_expectancy": 0.2159585352891396,
        "vwap_net_expectancy": -0.8006843437658675,
        "vwap_net_profit_factor": 0.686771,
        "development_status": "DISCOVERY_NO_GROSS_EDGE",
    }
    corr = build_vwap_taxonomy_correction_record(sealed)
    assert corr["vwap_taxonomy_correction_status"] == "APPLIED"
    assert corr["vwap_canonical_interpretation"] == "VWAP_RAW_EDGE_PRESENT_BUT_COST_DESTROYED"
    assert corr["vwap_terminal_status"] == "VWAP_RESEARCH_LINE_TERMINAL_CURRENT_EXECUTION_MODEL"
    assert corr["vwap_formal_qualification_started"] is False
    assert corr["mutates_sealed_metrics"] is False


def test_alpha_feasibility_no_new_strategies_no_paid():
    alpha = audit_alpha_data_families()
    assert alpha["alpha_data_family_count_audited"] == 8
    assert alpha["selected_next_data_family_count"] <= 2
    assert alpha["paid_data_purchased"] is False
    assert alpha["prohibited_scraping_count"] == 0
    assert alpha["new_strategy_generated_count"] == 0
    assert alpha["fake_adapter_implemented"] is False
    assert set(alpha["selected_next_data_family_ids"]).issubset(
        {"LIQUIDATION_EVENTS", "AGGRESSIVE_TRADE_FLOW"}
    )


def test_control_proof_not_real_learning():
    packets = _packets()
    control = run_learning_prevention_proof(
        packets=packets, use_real_ai=False, proof_level="CONTROL_CHAIN_PROOF"
    )
    assert control["label"] == "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"
    assert control["misrepresented_as_real_learning"] is False
    assert control["control_chain_proof_status"] == "PASS"
    real = run_learning_prevention_proof(
        packets=packets, use_real_ai=False, proof_level="REAL_HISTORICAL_CHAIN_PROOF"
    )
    assert real["real_historical_chain_proof_status"] in {
        "PASS",
        "FAIL",
        "NO_ELIGIBLE_BAD_PROCESS_SOURCE",
    }
    assert real.get("misrepresented_as_real_learning") is not True


def test_gpl_and_hard_bans():
    packets = _packets()
    gpl = run_good_process_loss_non_suppression_test(packets)
    assert gpl["good_process_loss_non_suppression_status"] == "PASS"
    assert os.environ["EXCHANGE_WRITE"] == "false"
    assert os.environ["MAINNET"] == "false"
    assert os.environ["REAL_MONEY"] == "false"


def test_quota_aware_mock_completes(tmp_path: Path):
    packets = _packets()
    out = run_quota_aware_calibration(
        root=tmp_path,
        packets=packets,
        manifest_checksum="mock_manifest",
        use_real_ai=False,
        max_batches_this_invocation=20,
    )
    assert out["quality"]["reflection_successful_case_count"] == 80
    assert out["quality"]["evidence_packet_constructible_ratio"]["value"] == 1.0
    assert out["quality"]["full_calibration_completion_ratio"]["value"] == 1.0
    assert out["quality"]["quality_gates_evaluated"] is True


def test_vwap_independent_of_reflection_gate():
    from backend.nexus_edge_discovery.conditional_vwap_confirmation import (
        VWAP_INDEPENDENT_OF_REFLECTION_QUALITY,
        run_conditional_vwap_confirmation,
    )

    assert VWAP_INDEPENDENT_OF_REFLECTION_QUALITY is True
    root = Path(__file__).resolve().parents[1]
    out = run_conditional_vwap_confirmation(
        root=root,
        bundles=[],
        universe_snapshot_id="u",
        data_checksum="d",
        research_universe_snapshot_checksum="u",
        gates_passed=False,
        require_reflection_quality=False,
    )
    assert out["conditional_vwap_confirmation_executed"] is True
    assert out["vwap_confirmation_status"] != "VWAP_DEVELOPMENT_SKIPPED_GATES_FAILED"
