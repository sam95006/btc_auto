"""General multi-strategy research engine V1 + evidence V2 tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"
os.environ["NEXUS_AI_SMOKE_TREAT_MOCK_AS_PASS"] = "1"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_strategy_engine.components import COMPONENT_IDS, component_registry
from backend.nexus_strategy_engine.constants import MAX_DEVELOPMENT_HYPOTHESES, MIN_STRATEGY_FAMILIES
from backend.nexus_strategy_engine.eligibility import research_vs_demo_gates
from backend.nexus_strategy_engine.evidence_v2 import (
    build_evidence_from_sim_row,
    deterministic_process_baseline,
    empty_evidence_shell,
)
from backend.nexus_strategy_engine.hypotheses import default_hypothesis_drafts, preregister_hypotheses
from backend.nexus_strategy_engine.lesson_seal import lesson_may_influence_development, seal_integration_lessons
from backend.nexus_strategy_engine.strategy_spec import (
    compute_semantic_checksum,
    compute_strategy_checksum,
    freeze_spec,
    validate_spec,
)


def test_component_registry_complete_and_unvalidated():
    reg = component_registry()
    assert reg["component_count"] == len(COMPONENT_IDS) == 16
    assert reg["validated_strategies"] is False
    for c in reg["components"]:
        assert c["required_data"]
        assert "entry_event" in c


def test_strategy_checksum_stable():
    drafts = default_hypothesis_drafts()
    draft = dict(drafts[0])
    draft["preregistration_timestamp"] = "2026-07-30T00:00:00Z"
    a = freeze_spec(draft)
    b = freeze_spec(draft)
    assert a["strategy_checksum"] == b["strategy_checksum"] == compute_strategy_checksum(a)
    assert a["semantic_checksum"] == compute_semantic_checksum(a)
    assert validate_spec(a) == []


def test_max_12_hypotheses_min_four_families():
    pre = preregister_hypotheses()
    assert pre["preregistered_hypothesis_count"] <= MAX_DEVELOPMENT_HYPOTHESES
    assert pre["strategy_family_count"] >= MIN_STRATEGY_FAMILIES
    assert pre["created_before_execution"] is True
    assert pre["post_result_hypothesis_insertion_forbidden"] is True
    assert pre["formal_walk_forward_forbidden_in_this_task"] is True


def test_research_vs_demo_not_fleets():
    g = research_vs_demo_gates()
    assert g["fleet_architecture"] is False
    assert g["one_dynamic_universe"] is True
    assert g["demo_gates_not_weakened_for_research_count"] is True
    assert g["eligibility_not_based_on_backtest_results"] is True


def test_loss_not_automatically_noncompliant_win_not_compliant():
    loss = empty_evidence_shell(
        entry_price=100,
        stop_price=99,
        target_price=102,
        cost_gate_status="PASS",
        data_quality_status="OK",
        risk_gate_status="PASS",
        position_size_valid=True,
        liquidation_distance_valid=True,
        net_pnl=-5.0,
    )
    win = dict(loss)
    win["net_pnl"] = 5.0
    win["hard_block_reasons"] = ["spread_above_limit"]
    assert deterministic_process_baseline(loss)["deterministic_process_status"] == "PROCESS_COMPLIANT"
    assert deterministic_process_baseline(win)["deterministic_process_status"] == "PROCESS_NONCOMPLIANT"


def test_missing_evidence_remains_unknown():
    p = empty_evidence_shell()
    assert p["volume_context"] == "UNKNOWN"
    assert p["open_interest_context"] == "UNKNOWN"
    assert deterministic_process_baseline(p)["deterministic_process_status"] == "PROCESS_EVIDENCE_INSUFFICIENT"


def test_integration_lessons_cannot_affect_policy():
    assert lesson_may_influence_development("INTEGRATION_PROOF_ONLY") is False
    seal = seal_integration_lessons(
        learning_proof_path=ROOT
        / "artifacts/readiness/immutable/goal_alignment_real_ai_broad_data_v1/learning_loop_integration_proof.json"
    )
    if seal.get("status") != "NO_PRIOR_LEARNING_PROOF":
        assert seal["may_influence_qualified_policy"] is False
        assert seal["classification"] == "INTEGRATION_PROOF_ONLY"


def test_control_fixture_labeled():
    hyp = freeze_spec(default_hypothesis_drafts()[0])
    row = {
        "symbol": "BTCUSDT",
        "side": "Sell",
        "regime": "RANGE",
        "entry_status": "ENTRY_FILLED",
        "entry_price": 100,
        "stop": 102,
        "take_profit": 96,
        "entry_ts": 1,
        "net_pnl": -1,
        "gross_pnl": -1,
        "fees": 0.1,
        "slippage": 0,
        "funding": 0,
    }
    pkt = build_evidence_from_sim_row(
        row=row,
        hypothesis=hyp,
        trade_id="t",
        candidate_id="c",
        universe_snapshot_id="u",
        data_checksum="d",
        intentional_violation="stale_data",
    )
    assert pkt["control_fixture_label"] == "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
    assert deterministic_process_baseline(pkt)["deterministic_process_status"] == "PROCESS_NONCOMPLIANT"


def test_no_fleet_and_engine_stage_constants():
    from backend.nexus_strategy_engine.constants import ENGINE_STAGE

    assert "FLEET" not in ENGINE_STAGE
    assert ENGINE_STAGE == "GENERAL_MULTI_STRATEGY_RESEARCH_ENGINE_V1"
