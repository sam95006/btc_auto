"""Tests for Agent C provider packages (nexus_provider / nexus_ai / nexus_reflection)."""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_ai.idempotency import SuccessfulCallDeduper, make_idempotency_key
from backend.nexus_ai.profiles import (
    CEREBRAS_RESEARCH_NORMALIZER,
    GROQ_MAIN_REASONER,
    GROQ_REFLECTION_REASONER,
    SAMBANOVA_INDEPENDENT_CRITIC,
)
from backend.nexus_ai.scheduler import ProviderScheduler
from backend.nexus_edge_discovery.blind_reflection_v23 import build_calibration_set_v23
from backend.nexus_provider.circuit_breaker import ProviderCircuitBreaker
from backend.nexus_provider.retry_policy import backoff_with_jitter, parse_rate_limit_reset, parse_retry_after
from backend.nexus_provider.token_bucket import TokenBucket
from backend.nexus_provider.transport_status import (
    assert_429_not_quality_failure,
    classify_transport_status,
    is_quality_neutral_transport,
)
from backend.nexus_reflection.checkpoint import (
    build_initial_checkpoint,
    detect_corruption,
    load_checkpoint,
    save_checkpoint,
)
from backend.nexus_reflection.lesson_gate import apply_lesson_gate
from backend.nexus_reflection.orchestrator import run_provider_hardening_pass, simulate_provider_transport
from backend.nexus_reflection.terminal_eval import evaluate_terminal, validate_terminal_denominators


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
                "entry_ts": 1_750_100_000_000 + i * 900_000,
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
        universe_snapshot_id="u2",
        data_checksum="d2",
    )


def test_token_bucket_and_retry_after():
    b = TokenBucket(capacity=2, refill_rate=100.0)
    assert b.try_acquire()
    assert b.try_acquire()
    assert not b.try_acquire()
    assert parse_retry_after({"Retry-After": "15"}) == 15.0
    assert parse_rate_limit_reset({"x-ratelimit-reset": "40"}) == 40.0
    rng = random.Random(1)
    w = [backoff_with_jitter(i, rng=rng) for i in range(4)]
    assert w[0] >= 0 and w[-1] >= w[0]


def test_circuit_breaker_and_429_not_quality():
    cb = ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=30.0)
    assert cb.record_failure(GROQ_REFLECTION_REASONER) is False
    assert cb.record_failure(GROQ_REFLECTION_REASONER) is True
    st = cb.status(GROQ_REFLECTION_REASONER)
    assert st["state"] == "OPEN"
    assert is_quality_neutral_transport("RATE_LIMITED")
    assert classify_transport_status(http_status=429) == "RATE_LIMITED"
    assert_429_not_quality_failure(
        "RATE_LIMITED",
        {"process_classification": None, "evidence_sufficiency": None},
    )


def test_scheduler_isolates_providers_and_dedupes():
    sch = ProviderScheduler()
    sch.enqueue(GROQ_REFLECTION_REASONER, ["a", "b"])
    sch.enqueue(SAMBANOVA_INDEPENDENT_CRITIC, ["c"])
    groq = simulate_provider_transport(
        sch, profile_id=GROQ_REFLECTION_REASONER, case_id="a", http_status=429, headers={"Retry-After": "9"}
    )
    sn = simulate_provider_transport(
        sch,
        profile_id=SAMBANOVA_INDEPENDENT_CRITIC,
        case_id="c",
        result_status="SUCCESS",
        response_hash="h1",
    )
    assert groq["transport_status"] == "RATE_LIMITED"
    assert sn["transport_status"] == "SUCCESS"
    d = SuccessfulCallDeduper()
    key = make_idempotency_key(
        profile_id=GROQ_REFLECTION_REASONER,
        case_id="a",
        prompt_hash="p",
        schema_version="s",
    )
    d.mark_completed(GROQ_REFLECTION_REASONER, "a", response_hash="rh", idempotency_key=key)
    assert d.already_completed(GROQ_REFLECTION_REASONER, "a")


def test_hardening_pass_fixture_no_fabricated_metrics(tmp_path: Path):
    out = run_provider_hardening_pass(root=tmp_path, allow_real_resume=False)
    assert out["fixture_only"] is True
    assert out["real_ai_quality_claimed"] is False
    assert out["quality_gates_evaluated"] is False
    assert out["V2_3_terminal_status"] == "INCOMPLETE_PROVIDER_CAPACITY"
    assert out["provider_isolation_ok"] is True
    assert out["groq_success_count"] is None
    lesson = apply_lesson_gate(terminal_status=out["V2_3_terminal_status"])
    assert lesson["new_policy_effect_lesson_count"] == 0


def test_checkpoint_corruption_and_terminal_denominators(tmp_path: Path):
    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="h1", model_id="m")
    save_checkpoint(tmp_path, state)
    loaded = load_checkpoint(tmp_path, expected_manifest="h1", migrate=True, model_id="m")
    assert loaded.get("ok") is True
    bad = detect_corruption("{not-json", expected_manifest="h1")
    assert bad["ok"] is False
    assert bad["checkpoint_integrity_status"] == "TRUNCATED_OR_CORRUPT_JSON"

    q = evaluate_terminal(state)
    assert q["quality_gates_evaluated"] is False
    assert q["V2_3_TERMINAL_STATUS"] == "INCOMPLETE_PROVIDER_CAPACITY"
    denom = validate_terminal_denominators(
        {
            "x": {"numerator": 0, "denominator": 0, "value": 1.0, "status": "NOT_APPLICABLE"},
        }
    )
    assert denom["terminal_denominator_validation"] == "FAIL"
    # empty missing file
    empty = detect_corruption(None)
    assert empty["ok"] is False


def test_independent_profile_constants():
    assert GROQ_REFLECTION_REASONER != SAMBANOVA_INDEPENDENT_CRITIC
    assert CEREBRAS_RESEARCH_NORMALIZER != GROQ_MAIN_REASONER
    assert json.dumps({"k": 1})  # sanitizer smoke
