"""P2.1 durable learning closure — PostgreSQL-backed research path, no exchange writes."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_research_decision_path import research_decision_path
from backend.nexus_demo_execution.p2_run8_durable_loader import (
    load_run8_from_intents,
    reconstruct_original_decision_context,
    reject_placeholder_ids,
    source_evidence_hash,
)
from backend.nexus_demo_execution.p2_run8_learning_closure import (
    ARM_READY_HOLD,
    DurableDecisionMemory,
    PNL_PROVENANCE,
    RepeatMistakeGuard,
    certified_run8_snapshot,
    close_run8_durable_learning,
    close_run8_learning,
    load_run8_learning_input,
)


def _durable_run8_intents() -> list[dict]:
    return [
        {
            "order_intent_id": "p1ent_run8_durable",
            "decision_id": "p1dec_run8_real_aaaaaaaa",
            "trade_id": "p1trd_run8_real_bbbbbbbb",
            "campaign_id": P1_CAMPAIGN_ID,
            "order_link_id": "nx-entry-run8-real",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "requested_qty": "0.001",
            "reduce_only": False,
            "state": "CLOSED",
            "bybit_order_id": "entry-oid-run8-real",
            "filled_qty": "0.001",
            "parent_order_intent_id": None,
            "actual_entry_price": "64282.2",
            "actual_exit_price": "64282.2",
            "realized_demo_pnl": "-0.07071042",
            "pnl_provenance": PNL_PROVENANCE,
            "closed_at": "2026-08-18T07:05:00+00:00",
            "accounting_json": {
                "open_fee": "0.03535521",
                "close_fee": "0.03535521",
                "position_flat": True,
                "P1_PREFLIGHT_PASS": True,
                "RISK_ENGINE_FINAL_AUTHORITY_PASS": True,
                "P1_ENTRY_RECONCILIATION_PASS": True,
                "P1_CLOSE_RECONCILIATION_PASS": True,
            },
        },
        {
            "order_intent_id": "p1cls_run8_durable",
            "decision_id": "p1dec_run8_real_aaaaaaaa",
            "trade_id": "p1trd_run8_real_bbbbbbbb",
            "campaign_id": P1_CAMPAIGN_ID,
            "order_link_id": "nx-close-run8-real",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "requested_qty": "0.001",
            "reduce_only": True,
            "state": "CLOSED",
            "bybit_order_id": "close-oid-run8-real",
            "filled_qty": "0.001",
            "parent_order_intent_id": "p1ent_run8_durable",
            "avg_fill_price": "64282.2",
        },
    ]


def test_hardcoded_snapshot_cannot_be_authoritative_production_input():
    with pytest.raises(ValueError, match="durable_run8_input_required"):
        load_run8_learning_input()
    with pytest.raises(ValueError, match="hardcoded_snapshot_not_authoritative"):
        load_run8_learning_input(certified_run8_snapshot())
    with pytest.raises(ValueError, match="durable_run8_input_required"):
        close_run8_learning()


def test_placeholder_ids_rejected_on_durable_path():
    payload = certified_run8_snapshot()
    payload["fixture_only"] = False
    with pytest.raises(ValueError, match="placeholder_id_rejected"):
        reject_placeholder_ids(payload)


def test_real_ledger_run8_loader_returns_real_ids():
    case = load_run8_from_intents(_durable_run8_intents())
    assert case["source"] == "DURABLE_POSTGRES_LEDGER"
    assert case["fixture_only"] is False
    assert case["trade_id"] == "p1trd_run8_real_bbbbbbbb"
    assert case["decision_id"] == "p1dec_run8_real_aaaaaaaa"
    assert case["order_intent_id"] == "p1ent_run8_durable"
    assert case["entry_order_id"] == "entry-oid-run8-real"
    assert case["close_order_id"] == "close-oid-run8-real"
    assert case["candidate_count"] == 1
    assert case["source_evidence_hash"]
    assert case["run8_evidence_identity"] == case["source_evidence_hash"]
    assert "run8_certified" not in case["trade_id"]


def test_source_evidence_hash_is_deterministic():
    case = load_run8_from_intents(_durable_run8_intents())
    again = source_evidence_hash(case)
    assert again == case["source_evidence_hash"]
    assert len(again) == 64


def test_missing_historical_decision_fields_remain_unknown():
    case = load_run8_from_intents(_durable_run8_intents())
    ctx = case["original_decision_context"]
    assert ctx["confidence"] == "UNKNOWN"
    assert ctx["expected_gross_move_bps"] == "UNKNOWN"
    assert ctx["ai_direction_quality_proven"] is False
    assert ctx["qualification_execution_quality"] == "SEPARATE_FROM_AI_DIRECTION"


def test_process_valid_derived_not_hardcoded():
    case = load_run8_from_intents(_durable_run8_intents())
    assert case["process_assessment"]["process_valid_hardcoded"] is False
    assert case["process_assessment"]["process_valid"] is True
    incomplete = dict(case)
    incomplete["P1_PREFLIGHT_PASS"] = False
    incomplete["process_assessment"] = None
    from backend.nexus_demo_execution.p2_run8_durable_loader import derive_process_gates

    assessment = derive_process_gates(incomplete)
    assert assessment["process_valid"] is False


def test_durable_lesson_survives_process_restart(tmp_path: Path):
    sqlite_path = tmp_path / "p2_lessons.db"
    intents = _durable_run8_intents()
    store_a = DurableLessonStore(sqlite_path=sqlite_path)
    evidence_a = close_run8_durable_learning(store=store_a, intents=intents)
    store_a.close()

    store_b = DurableLessonStore(sqlite_path=sqlite_path)
    memory_b = DurableDecisionMemory(store_b)
    hits = memory_b.query_context(
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "expected_gross_pnl": "0",
            "round_trip_fee_estimate": "0.07071042",
            "confidence": 0.62,
        }
    )
    store_b.close()
    assert len(hits) == 1
    assert hits[0]["source_evidence_hash"] == evidence_a["source_evidence_hash"]
    assert hits[0]["policy_truth"] is False


def test_duplicate_run8_lesson_is_idempotent(tmp_path: Path):
    sqlite_path = tmp_path / "p2_lessons_dup.db"
    intents = _durable_run8_intents()
    store = DurableLessonStore(sqlite_path=sqlite_path)
    close_run8_durable_learning(store=store, intents=intents)
    close_run8_durable_learning(store=store, intents=intents)
    lessons = store.list_lessons()
    store.close()
    assert len(lessons) == 1


def test_symbol_side_alone_does_not_trigger_fee_drag_guard():
    snapshot = certified_run8_snapshot()
    evidence = close_run8_learning(snapshot, allow_test_fixture=True)
    from backend.nexus_demo_execution.p2_run8_learning_closure import DecisionMemory

    memory = DecisionMemory()
    memory._rows = list(evidence["decision_memory_hits"])
    guard = RepeatMistakeGuard(memory)
    result = guard.evaluate(
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "expected_gross_pnl": "5",
            "round_trip_fee_estimate": "0.07",
            "confidence": 0.7,
        }
    )
    assert result["decision_after_learning"] == "ALLOW"
    assert result["guard_after"] == "NONE"


def test_fee_dominated_similar_context_triggers_research_guard(tmp_path: Path):
    sqlite_path = tmp_path / "p2_guard.db"
    store = DurableLessonStore(sqlite_path=sqlite_path)
    evidence = close_run8_durable_learning(store=store, intents=_durable_run8_intents())
    store.close()
    assert evidence["decision_before_learning"] == "ALLOW"
    assert evidence["decision_after_learning"] == "SKIP"
    assert evidence["research_recommendation_before"] == "RESEARCH_ALLOW"
    assert evidence["research_recommendation_after"] == "RESEARCH_SKIP"
    assert evidence["behavior_change_demonstrated"] is True
    assert evidence["guard_after"] == "REPEAT_FEE_DRAG"


def test_unrelated_eth_context_unaffected_by_btc_fee_drag_lesson(tmp_path: Path):
    sqlite_path = tmp_path / "p2_eth.db"
    store = DurableLessonStore(sqlite_path=sqlite_path)
    close_run8_durable_learning(store=store, intents=_durable_run8_intents())
    memory = DurableDecisionMemory(store)
    eth = research_decision_path(
        {
            "symbol": "ETHUSDT",
            "side": "Buy",
            "expected_gross_pnl": "0",
            "round_trip_fee_estimate": "0.07",
            "confidence": 0.7,
        },
        memory=memory,
    )
    store.close()
    assert eth["research_recommendation"] == "RESEARCH_ALLOW"
    assert eth["guard"]["decision_after_learning"] == "ALLOW"


def test_one_case_does_not_become_policy_truth(tmp_path: Path):
    store = DurableLessonStore(sqlite_path=tmp_path / "p2_policy.db")
    evidence = close_run8_durable_learning(store=store, intents=_durable_run8_intents())
    lesson = store.get_by_evidence_hash(evidence["source_evidence_hash"])
    store.close()
    assert evidence["policy_truth"] is False
    assert lesson is not None
    assert lesson["policy_truth"] is False
    assert lesson["support_count"] == 1
    assert lesson["status"] == "candidate_only"


def test_durable_path_has_zero_exchange_writes_and_disarmed_flags(tmp_path: Path):
    store = DurableLessonStore(sqlite_path=tmp_path / "p2_safety.db")
    evidence = close_run8_durable_learning(store=store, intents=_durable_run8_intents())
    store.close()
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    assert evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] == ARM_READY_HOLD
    assert evidence["live_execution_veto"] is False
    assert os.environ.get("MAINNET", "").lower() == "false"
    assert os.environ.get("REAL_MONEY", "").lower() == "false"
    assert os.environ.get("EXCHANGE_WRITE", "").lower() == "false"
    assert os.environ.get("DEMO_AUTONOMOUS_ENABLED", "").lower() == "false"
    assert os.environ.get("AUTONOMOUS_SEND", "").lower() == "false"
