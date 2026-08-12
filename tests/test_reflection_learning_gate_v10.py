"""Tests for V10 Reflection Learning Gate — fail-closed, no live providers required."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_edge_discovery.blind_reflection_v23 import build_calibration_set_v23
from backend.nexus_reflection.checkpoint import build_initial_checkpoint, save_checkpoint
from backend.nexus_reflection.learning_gate_v10 import (
    LEARNING_BLOCKED_FAILED,
    LEARNING_BLOCKED_INCOMPLETE,
    LEARNING_SCAFFOLDED,
    evaluate_learning_gate,
    scaffold_historical_lesson_prevention_proof,
)
from backend.nexus_reflection.v23_resume_v10 import (
    ensure_runtime_checkpoint,
    resume_v23,
    summarize_checkpoint,
)

ROOT = Path(__file__).resolve().parents[1]


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


def test_learning_gate_blocks_when_incomplete():
    gate = evaluate_learning_gate(
        terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        quality_gates_passed=False,
    )
    assert gate["learning_prevention_status"] == LEARNING_BLOCKED_INCOMPLETE
    assert gate["policy_effect_lesson_allowed"] is False
    assert gate["new_policy_effect_lesson_count"] == 0
    assert gate["risk_limits_changed"] is False
    assert gate["leverage_changed"] is False
    assert gate["profitability_claimed"] is False
    assert gate["false_learning_claim"] is False


def test_learning_gate_blocks_when_quality_failed():
    gate = evaluate_learning_gate(
        terminal_status="VALID_SAMPLE_QUALITY_FAILED",
        quality_gates_passed=False,
    )
    assert gate["learning_prevention_status"] == LEARNING_BLOCKED_FAILED
    assert gate["policy_effect_lesson_allowed"] is False


def test_learning_gate_blocks_verified_without_quality_pass():
    gate = evaluate_learning_gate(terminal_status="VERIFIED", quality_gates_passed=False)
    assert gate["policy_effect_lesson_allowed"] is False
    assert gate["new_policy_effect_lesson_count"] == 0


def test_scaffold_blocked_when_incomplete():
    out = scaffold_historical_lesson_prevention_proof(
        terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        quality_gates_passed=False,
        packets=_packets(),
        execute=True,
    )
    assert out["learning_prevention_status"] == LEARNING_BLOCKED_INCOMPLETE
    assert out["proof_scaffold"]["status"] == "NOT_EXECUTED"
    assert out["new_policy_effect_lesson_count"] == 0
    assert out["profitability_claimed"] is False


def test_scaffold_when_verified_no_execute():
    out = scaffold_historical_lesson_prevention_proof(
        terminal_status="VERIFIED",
        quality_gates_passed=True,
        packets=_packets(),
        execute=False,
    )
    assert out["learning_prevention_status"] == LEARNING_SCAFFOLDED
    assert out["proof_scaffold"]["status"] == "SCAFFOLDED"
    assert out["proof_scaffold"]["claims"]["profitability"] is False
    assert out["policy_effect_lesson_allowed"] is True


def test_scaffold_execute_control_path_when_verified(tmp_path: Path):
    packets = _packets()
    out = scaffold_historical_lesson_prevention_proof(
        terminal_status="VERIFIED",
        quality_gates_passed=True,
        packets=packets,
        execute=True,
        use_real_ai=False,
    )
    assert out["profitability_claimed"] is False
    assert out["risk_limits_changed"] is False
    assert out["leverage_changed"] is False
    assert out["false_learning_claim"] is False
    assert out["learning_prevention_status"] in {
        LEARNING_SCAFFOLDED,
        "HISTORICAL_LESSON_PREVENTION_PROOF_EXECUTED",
        "HISTORICAL_PROOF_NO_ELIGIBLE_SOURCE",
    }
    # REAL_HISTORICAL excludes control fixtures → may be no eligible source
    if out["learning_prevention_status"] == "HISTORICAL_PROOF_NO_ELIGIBLE_SOURCE":
        assert out["new_policy_effect_lesson_count"] == 0


def test_ensure_copies_checkpoint(tmp_path: Path):
    src = tmp_path / "src" / "blind_reflection_v23_checkpoint.json"
    src.parent.mkdir(parents=True)
    src.write_text(json.dumps({"schema": "test", "case_ids": []}), encoding="utf-8")
    root = tmp_path / "wt"
    root.mkdir()
    first = ensure_runtime_checkpoint(root, source=src)
    assert first["checkpoint_present"] is True
    assert first["checkpoint_copied"] is True
    assert (root / ".nexus_runtime" / "blind_reflection_v23_checkpoint.json").is_file()
    second = ensure_runtime_checkpoint(root, source=src)
    assert second["checkpoint_copied"] is False


def test_resume_without_fabricating_when_no_real(tmp_path: Path):
    packets = _packets()
    manifest = "test_manifest_checksum_v10"
    state = build_initial_checkpoint(packets=packets, manifest_checksum=manifest, model_id="fixture")
    # Partial progress must be preserved, not rebuilt from summaries
    state["completed_case_ids"] = list(state["case_ids"][:10])
    state["pending_case_ids"] = list(state["case_ids"][10:])
    state["transport"]["GROQ_REFLECTION_REASONER"]["success_count"] = 10
    save_checkpoint(tmp_path, state)

    # Point PRIOR manifest away — resume will use builder checksum path;
    # force allow_real_resume False so we only verify load/summarize path.
    out = resume_v23(root=tmp_path, allow_real_resume=False, max_batches=0)
    # Without matching prior immutable manifest, may fail integrity/manifest —
    # still must not claim rebuilt metrics progress.
    assert out["rebuilt_from_summary_metrics"] is False
    assert out["real_resume_executed"] is False


def test_summarize_checkpoint_counts():
    state = {
        "case_ids": ["a"] * 80,
        "completed_case_ids": ["a"] * 53,
        "pending_case_ids": ["a"] * 27,
        "pending_critic_case_ids": ["c"] * 10,
        "transport": {
            "GROQ_REFLECTION_REASONER": {
                "success_count": 53,
                "HTTP_429_count": 2,
                "retry_after": 900,
                "next_resume_not_before": "2026-08-05T12:00:00Z",
                "last_exit_reason": "PROVIDER_RATE_LIMITED",
            },
            "SAMBANOVA_INDEPENDENT_CRITIC": {
                "success_count": 16,
                "HTTP_429_count": 1,
                "retry_after": 60,
                "last_exit_reason": "PROVIDER_RATE_LIMITED",
            },
        },
    }
    s = summarize_checkpoint(state)
    assert s["groq_success_count"] == 53
    assert s["groq_pending_count"] == 27
    assert s["sambanova_success_count"] == 16
    assert s["sambanova_pending_count"] == 10
