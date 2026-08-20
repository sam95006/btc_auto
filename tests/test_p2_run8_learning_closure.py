"""P2 learning closure from certified Run #8 — research-only, no exchange writes."""
from __future__ import annotations

import os
from copy import deepcopy

import pytest

from backend.nexus_demo_execution.p2_run8_learning_closure import (
    ARM_READY_HOLD,
    MISTAKE_TAXONOMY,
    MIN_SUPPORT_FOR_POLICY,
    PNL_PROVENANCE,
    PROTECTED_POLICY_FIELDS,
    RepeatMistakeGuard,
    certified_run8_snapshot,
    close_run8_learning,
    load_run8_learning_input,
)
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP


REQUIRED_MISTAKE_LABELS = {
    "ENTRY_TIMING",
    "DIRECTION",
    "SIGNAL_QUALITY",
    "MARKET_REGIME",
    "FEE_DRAG",
    "RISK_SIZING",
    "NO_MISTAKE",
    "VALID_DECISION_BAD_OUTCOME",
}


def test_certified_run8_learning_input_is_exchange_and_ledger_grounded():
    case = load_run8_learning_input(allow_test_fixture=True)
    assert case["ledger_final_state"] == "CLOSED"
    assert case["pnl_provenance"] == PNL_PROVENANCE
    assert case["candidate_count"] == 1
    assert case["create_order_calls"] == 0
    assert case["exchange_write_call_count"] == 0
    assert case["actual_entry_price"] == "64282.2"
    assert case["actual_exit_price"] == "64282.2"
    assert case["realized_demo_pnl"] == "-0.07071042"


def test_non_closed_or_write_contaminated_input_is_rejected():
    dirty = certified_run8_snapshot()
    dirty["ledger_final_state"] = "FILLED"
    with pytest.raises(ValueError, match="ledger_not_closed"):
        load_run8_learning_input(dirty, allow_test_fixture=True)
    writes = certified_run8_snapshot()
    writes["create_order_calls"] = 1
    with pytest.raises(ValueError, match="exchange_write_not_zero"):
        load_run8_learning_input(writes, allow_test_fixture=True)


def test_run8_pipeline_closes_learning_without_exchange_writes(tmp_path):
    artifact = tmp_path / "p2.json"
    evidence = close_run8_learning(
        write_artifact=lambda _path, payload: artifact.write_text("ok") or True,
        allow_test_fixture=True,
    )
    assert evidence["P2_RUN8_LEARNING_CLOSURE"] == "COMPLETE"
    assert evidence["run8_certified_learning_input_ready"] is True
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    assert evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] == ARM_READY_HOLD
    assert os.environ.get("MAINNET", "").lower() == "false"
    assert os.environ.get("REAL_MONEY", "").lower() == "false"
    assert os.environ.get("EXCHANGE_WRITE", "").lower() == "false"
    assert os.environ.get("DEMO_AUTONOMOUS_ENABLED", "").lower() == "false"
    assert os.environ.get("AUTONOMOUS_SEND", "").lower() == "false"


def test_reflection_separates_bad_outcome_from_valid_decision():
    evidence = close_run8_learning(allow_test_fixture=True)
    reflection = evidence["reflection"]
    assert reflection["outcome_quality"] == "BAD_NET_PNL"
    assert reflection["decision_quality"] == "VALID_PROCESS_INSUFFICIENT_EDGE_VS_COST"
    assert reflection["distinction"] == "BAD_OUTCOME_FROM_FEE_DRAG_NOT_DIRECTIONAL_ERROR"
    assert reflection["price_path"] == "UNCHANGED"
    assert reflection["pnl_is_not_process"] is True
    assert reflection["process_valid"] is True
    assert reflection["process_valid_hardcoded"] is False


def test_mistake_taxonomy_and_fee_drag_classification():
    evidence = close_run8_learning(allow_test_fixture=True)
    mistakes = evidence["mistakes"]
    assert REQUIRED_MISTAKE_LABELS.issubset(set(mistakes["taxonomy"]))
    assert set(MISTAKE_TAXONOMY) == REQUIRED_MISTAKE_LABELS
    assert mistakes["primary_mistake"] == "FEE_DRAG"
    assert "VALID_DECISION_BAD_OUTCOME" in mistakes["labels"]
    assert mistakes["direction_error"] is False
    assert mistakes["one_loss_is_not_policy"] is True


def test_counterfactuals_are_research_only():
    evidence = close_run8_learning(allow_test_fixture=True)
    kinds = {item["kind"] for item in evidence["counterfactuals"]}
    assert {"SKIP", "delayed_entry", "alternative_threshold", "reduced_confidence_or_size"} <= kinds
    assert all(item["research_only"] is True for item in evidence["counterfactuals"])
    assert all(item.get("live_trade_generated") is False for item in evidence["counterfactuals"])
    skip = next(item for item in evidence["counterfactuals"] if item["kind"] == "SKIP")
    assert skip["hypothetical_net_pnl"] == "0"
    delayed = next(item for item in evidence["counterfactuals"] if item["kind"] == "delayed_entry")
    assert delayed["hypothetical_net_pnl"] is None


def test_lesson_candidate_is_linked_and_not_policy_truth():
    evidence = close_run8_learning(allow_test_fixture=True)
    lesson = evidence["lesson_candidate"]
    assert lesson["lesson_id"] == evidence["lesson_id"]
    assert lesson["trade_id"] == "run8_certified_trade"
    assert lesson["decision_id"] == "run8_certified_decision"
    assert lesson["run8_evidence_identity"] == "run8_certified_lifecycle"
    assert lesson["status"] == "candidate_only"
    assert lesson["policy_truth"] is False
    assert lesson["active"] is False
    assert lesson["support_count"] == 1
    assert lesson["min_support_for_policy"] == MIN_SUPPORT_FOR_POLICY
    assert lesson["support_count"] < lesson["min_support_for_policy"]
    assert lesson["revalidation_required"] is True
    assert lesson["ttl_trades"] == 20
    assert set(PROTECTED_POLICY_FIELDS).issubset(set(lesson["forbidden_mutations"]))
    assert evidence["lesson_is_not_policy_truth"] is True


def test_decision_memory_is_queryable_by_future_candidate_context():
    evidence = close_run8_learning(allow_test_fixture=True)
    hits = evidence["decision_memory_hits"]
    assert evidence["decision_memory_queryable"] is True
    assert len(hits) == 1
    assert hits[0]["symbol"] == "BTCUSDT"
    assert hits[0]["side"] == "Buy"
    assert hits[0]["lesson_id"] == evidence["lesson_id"]
    assert hits[0]["trade_id"] == "run8_certified_trade"


def test_repeat_mistake_guard_changes_similar_candidate_behavior():
    evidence = close_run8_learning(allow_test_fixture=True)
    assert evidence["decision_before_learning"] == "ALLOW"
    assert evidence["decision_after_learning"] == "SKIP"
    assert evidence["confidence_before"] == 0.62
    assert evidence["confidence_after"] < evidence["confidence_before"]
    assert evidence["guard_before"] == "NONE"
    assert evidence["guard_after"] == "REPEAT_FEE_DRAG"
    assert evidence["reason_for_change"]
    assert evidence["behavior_change_demonstrated"] is True
    assert evidence["repeat_mistake_guard"]["policy_mutated"] is False


def test_unrelated_candidate_is_not_skipped():
    first = close_run8_learning(allow_test_fixture=True)
    memory_hits = first["decision_memory_hits"]
    from backend.nexus_demo_execution.p2_run8_learning_closure import DecisionMemory

    memory = DecisionMemory()
    memory._rows = list(memory_hits)
    guard = RepeatMistakeGuard(memory)
    other = guard.evaluate(
        {
            "symbol": "ETHUSDT",
            "side": "Buy",
            "expected_gross_pnl": "12",
            "round_trip_fee_estimate": "0.07",
            "confidence": 0.7,
        }
    )
    assert other["decision_after_learning"] == "ALLOW"
    assert other["guard_after"] == "NONE"


def test_hard_safety_policy_is_not_mutated():
    before_leverage = FIXED_LEVERAGE
    before_cap = MARGIN_PER_TRADE_CAP
    evidence = close_run8_learning(allow_test_fixture=True)
    assert FIXED_LEVERAGE == before_leverage == 25
    assert MARGIN_PER_TRADE_CAP == before_cap
    assert evidence["hard_leverage"] == 25
    assert "FIXED_LEVERAGE" in evidence["protected_policy_fields"]
    assert evidence["repeat_mistake_guard"]["policy_mutated"] is False


def test_pipeline_does_not_invent_a_new_qualification_trade():
    snapshot = certified_run8_snapshot()
    evidence = close_run8_learning(deepcopy(snapshot), allow_test_fixture=True)
    assert evidence["trade_id"] == snapshot["trade_id"]
    assert evidence["decision_id"] == snapshot["decision_id"]
    assert evidence["run8_evidence_identity"] == snapshot["run8_evidence_identity"]
    assert evidence["create_order_calls"] == 0
