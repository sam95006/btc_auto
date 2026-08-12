"""Tests for Blind Reflection V2.3 evidence delivery and learning prevention."""
from __future__ import annotations

import os

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_edge_discovery.blind_reflection_v23 import (
    build_blind_prompt,
    build_calibration_set_v23,
    build_critic_prompt,
    build_sanitized_evidence_packet,
    migrate_process_classification,
    run_blind_reflection_v23,
    serialize_evidence_to_prompt,
)
from backend.nexus_edge_discovery.learning_prevention_proof import (
    run_good_process_loss_non_suppression_test,
    run_learning_prevention_proof,
)
from backend.nexus_strategy_engine.evidence_v2 import deterministic_process_baseline


def _hyps():
    return [
        {
            "strategy_id": "V12_H01_TREND_CONTINUATION",
            "hypothesis_id": "V12_H01_TREND_CONTINUATION",
            "strategy_family": "TREND",
            "component_id": "TREND_CONTINUATION",
            "event_definition": "break_prior_swing",
            "stop_definition": "atr_stop",
            "target_definition": "rr_target",
        }
    ]


def _rows():
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
    return rows


def test_blind_prompt_contains_sanitized_evidence_packet():
    packets = build_calibration_set_v23(
        market_rows=_rows(),
        hypotheses=_hyps(),
        universe_snapshot_id="u",
        data_checksum="d",
        real_count=60,
        control_count=20,
    )
    p = packets[0]
    san = build_sanitized_evidence_packet(p)
    ej, eh, n = serialize_evidence_to_prompt(san)
    prompt = build_blind_prompt(trade_id=str(p["trade_id"]), evidence_json=ej)
    assert "sanitized_evidence_packet_json=" in prompt
    assert '"net_pnl"' in ej
    assert '"cost_gate_status"' in ej
    assert '"entry_price"' in ej
    assert n >= 15
    assert len(eh) == 64


def test_blind_prompt_excludes_deterministic_and_expected():
    ej = '{"trade_id":"t1","net_pnl":-1,"missing_evidence":[]}'
    prompt = build_blind_prompt(trade_id="t1", evidence_json=ej)
    low = prompt.lower()
    assert "deterministic_baseline" not in low
    assert "expected classification" not in low
    assert "desired agreement" not in low
    assert "agreement target" not in low


def test_evidence_payload_nonempty_and_no_fabrication_requirement():
    packets = build_calibration_set_v23(
        market_rows=_rows(),
        hypotheses=_hyps(),
        universe_snapshot_id="u",
        data_checksum="d",
    )
    for p in packets[:5]:
        san = build_sanitized_evidence_packet(p)
        assert san["nonempty_evidence_field_count"] >= 15
        declared = set(san.get("missing_evidence") or [])
        # fixture may list missing fields; must not invent funding number when UNAVAILABLE
        if "funding_estimate" in declared:
            assert san.get("funding_estimate") in (None, "UNAVAILABLE", "MISSING", "UNKNOWN") or str(
                san.get("funding_estimate")
            ).upper() in {"UNAVAILABLE", "MISSING", "UNKNOWN"}


def test_critic_receives_full_evidence_after_groq_only():
    prompt = build_critic_prompt(
        evidence_json='{"trade_id":"t","net_pnl":-1,"cost_gate_status":"FAIL"}',
        groq_classification="BAD_PROCESS_LOSS",
        groq_citations=["ev1"],
        deterministic_classification="BAD_PROCESS_LOSS",
        deterministic_citations=["cost_gate_failed"],
    )
    low = prompt.lower()
    assert "sanitized_evidence_packet_json=" in prompt
    assert "prefer deterministic" not in low
    assert "prefer groq" not in low
    assert "groq_classification=" in prompt
    assert "deterministic_classification=" in prompt


def test_undetermined_migration():
    assert migrate_process_classification("UNDETERMINED_PROCESS") == "UNDETERMINED"
    assert migrate_process_classification("GOOD_PROCESS_LOSS") == "GOOD_PROCESS_LOSS"


def test_loss_not_auto_bad_and_win_not_auto_good():
    packets = build_calibration_set_v23(
        market_rows=_rows(),
        hypotheses=_hyps(),
        universe_snapshot_id="u",
        data_checksum="d",
    )
    compliant_loss = None
    for p in packets:
        base = deterministic_process_baseline(p)
        pnl = float(p.get("net_pnl") or 0)
        if base["deterministic_process_status"] == "PROCESS_COMPLIANT" and pnl < 0:
            compliant_loss = p
            break
    assert compliant_loss is not None
    assert deterministic_process_baseline(compliant_loss)["pnl_does_not_decide_process"] is True


def test_v23_mock_calibration_delivery_and_quality():
    out = run_blind_reflection_v23(
        market_rows=_rows(),
        hypotheses=_hyps(),
        universe_snapshot_id="u",
        data_checksum="d",
        use_real_ai=False,
    )
    assert out["evidence_packet_delivery_ratio"] == 1.0
    assert out["blind_reflection_v2_3_calibration_count"] >= 80
    assert out["real_trade_case_count"] >= 60
    assert out["control_fixture_count"] >= 20
    assert out["blind_valid_schema_ratio"] >= 0.95
    assert out["missing_evidence_invention_count"] == 0
    assert out["deterministic_answer_leak_count"] == 0
    assert out["secret_leak_count"] == 0
    assert out["quality_targets_met"] is True
    assert out["formal_walk_forward_executed"] is False
    assert out["oos_executed"] is False
    assert out["demo_order_count"] == 0
    assert out["deployment_started"] is False


def test_learning_prevention_and_gpl_non_suppression():
    packets = build_calibration_set_v23(
        market_rows=_rows(),
        hypotheses=_hyps(),
        universe_snapshot_id="u",
        data_checksum="d",
    )
    learning = run_learning_prevention_proof(
        packets=packets, use_real_ai=False, proof_level="CONTROL_CHAIN_PROOF"
    )
    assert learning["control_chain_proof_status"] == "PASS"
    assert learning["lesson_retrieved"] is True
    assert learning["lesson_cited_by_main_reasoner"] is True
    assert learning["same_error_repeated"] is False
    assert learning["hard_risk_override_test_status"] == "PASS"
    assert learning["permanent_policy_mutation"] is False
    assert learning["label"] == "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"
    gpl = run_good_process_loss_non_suppression_test(packets)
    assert gpl["good_process_loss_non_suppression_status"] == "PASS"
    assert gpl["auto_block_all_similar_valid_trades"] is False


def test_no_formal_paths():
    assert os.environ["EXCHANGE_WRITE"] == "false"
    assert os.environ["MAINNET"] == "false"
    assert os.environ["REAL_MONEY"] == "false"
