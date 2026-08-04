"""Deterministic V2.3 provider transport tests — no live providers required."""
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_edge_discovery.blind_reflection_v23 import build_calibration_set_v23
from backend.nexus_edge_discovery.provider_transport_v23 import (
    CircuitBreaker,
    ProviderTransportController,
    ReplayFixtureStore,
    TokenBucket,
    dedupe_pending_against_success,
    detect_checkpoint_corruption,
    exponential_backoff_with_jitter,
    is_ai_quality_failure,
    is_transport_failure,
    parse_quota_reset_at,
    parse_retry_after,
    repair_checkpoint_overlap,
    validate_terminal_denominators,
)
from backend.nexus_edge_discovery.quota_aware_v23 import (
    build_initial_checkpoint,
    evaluate_quality,
    load_checkpoint,
    migrate_checkpoint_v2_to_v3,
    run_quota_aware_calibration,
    save_checkpoint,
)
from backend.nexus_edge_discovery.ratio_metrics import make_ratio

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "artifacts" / "readiness" / "fixtures" / "blind_reflection_v23_transport"


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


def test_parse_retry_after_seconds_and_http_date():
    assert parse_retry_after({"Retry-After": "12"}) == 12.0
    assert parse_retry_after({"retry-after": "3.5"}) == 3.5
    now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
    future = now + timedelta(seconds=90)
    http_date = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    wait = parse_retry_after({"Retry-After": http_date}, now=now)
    assert 89.0 <= wait <= 91.0


def test_parse_retry_after_ratelimit_reset_and_body():
    now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
    epoch = now.timestamp() + 45
    assert parse_retry_after({"x-ratelimit-reset": str(epoch)}, now=now) == pytest.approx(45.0, abs=0.5)
    assert parse_retry_after({"x-ratelimit-reset-requests": "30"}, now=now) == 30.0
    wait = parse_retry_after({}, body='{"error":{"message":"Rate limit. Please try again in 12.5s."}}')
    assert wait == 12.5
    assert parse_retry_after({}) == 900.0


def test_quota_reset_handling():
    now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
    reset = parse_quota_reset_at({"x-ratelimit-reset": "60"}, now=now)
    assert reset == now + timedelta(seconds=60)
    ctrl = ProviderTransportController(profile_id="GROQ_REFLECTION_REASONER")
    wait = ctrl.apply_rate_limit({"retry-after": "25", "x-ratelimit-reset": "25"}, now=now)
    assert wait == 25.0
    assert ctrl.quota_reset_at is not None
    assert ctrl.next_resume_not_before == now + timedelta(seconds=25)
    ok, reason = ctrl.can_invoke(now=now + timedelta(seconds=1))
    assert ok is False
    assert reason in {"QUOTA_RESET_WAIT", "TOKEN_BUCKET_WAIT", "CIRCUIT_OPEN"}


def test_token_bucket_provider_specific():
    a = TokenBucket(capacity=2, refill_per_s=0.0, tokens=2, profile_id="GROQ_REFLECTION_REASONER")
    b = TokenBucket(capacity=2, refill_per_s=0.0, tokens=2, profile_id="SAMBANOVA_INDEPENDENT_CRITIC")
    assert a.try_acquire()
    assert a.try_acquire()
    assert not a.try_acquire()
    assert b.try_acquire()  # independent


def test_exponential_backoff_with_jitter_deterministic():
    rng = random.Random(7)
    waits = [exponential_backoff_with_jitter(i, base_s=1.0, rng=rng) for i in range(5)]
    assert waits[0] >= 0
    assert waits[4] > waits[0]
    assert all(w <= 120.0 for w in waits)
    rng2 = random.Random(7)
    waits2 = [exponential_backoff_with_jitter(i, base_s=1.0, rng=rng2) for i in range(5)]
    assert waits == waits2


def test_circuit_breaker_opens_on_429_and_timeouts():
    cb = CircuitBreaker(failure_threshold=3, cooldown_s=10.0)
    assert cb.allow()
    cb.record_failure("TIMEOUT", now=100.0)
    cb.record_failure("TIMEOUT", now=101.0)
    assert cb.state == "CLOSED"
    cb.record_failure("TIMEOUT", now=102.0)
    assert cb.state == "OPEN"
    assert not cb.allow(now=105.0)
    assert cb.allow(now=113.0)  # half-open
    cb.record_success()
    assert cb.state == "CLOSED"
    cb.record_failure("RATE_LIMITED", now=200.0)
    assert cb.state == "OPEN"


def test_429_never_ai_quality_failure():
    assert is_transport_failure("RATE_LIMITED")
    assert not is_ai_quality_failure("RATE_LIMITED")
    assert not is_ai_quality_failure("TIMEOUT")
    assert not is_ai_quality_failure("CIRCUIT_OPEN")
    assert is_ai_quality_failure("INVALID_SCHEMA")


def test_successful_case_deduplication():
    pending = dedupe_pending_against_success(
        case_ids=["a", "b", "c", "d"],
        completed_case_ids=["a", "c"],
        pending_case_ids=["a", "b", "b", "d"],
    )
    assert pending == ["b", "d"]


def test_resume_scheduling_skips_completed(tmp_path: Path):
    packets = _packets()
    out1 = run_quota_aware_calibration(
        root=tmp_path,
        packets=packets,
        manifest_checksum="resume_dedupe",
        use_real_ai=False,
        max_batches_this_invocation=20,
        run_critic=False,
    )
    attempts1 = out1["state_summary"]["transport"]["GROQ_REFLECTION_REASONER"]["attempt_count"]
    assert out1["quality"]["reflection_successful_case_count"] == 80
    out2 = run_quota_aware_calibration(
        root=tmp_path,
        packets=packets,
        manifest_checksum="resume_dedupe",
        use_real_ai=False,
        max_batches_this_invocation=3,
        run_critic=False,
    )
    attempts2 = out2["state_summary"]["transport"]["GROQ_REFLECTION_REASONER"]["attempt_count"]
    assert attempts2 == attempts1
    assert out2["quality"]["reflection_successful_case_count"] == 80


def test_provider_response_replay_fixtures():
    store = ReplayFixtureStore.from_dir(FIXTURE_DIR)
    body, rec = store.invoke(profile_id="GROQ_REFLECTION_REASONER", trade_id="RATE_LIMITED")
    assert body is None
    assert rec["result_status"] == "RATE_LIMITED"
    assert rec["replay"] is True
    assert not is_ai_quality_failure(rec["result_status"])

    body2, rec2 = store.invoke(profile_id="GROQ_REFLECTION_REASONER", trade_id="TIMEOUT")
    assert body2 is None
    assert rec2["result_status"] == "TIMEOUT"

    body3, rec3 = store.invoke(profile_id="GROQ_REFLECTION_REASONER", trade_id="INVALID_SCHEMA")
    assert body3 is None
    assert rec3["result_status"] == "INVALID_SCHEMA"
    assert is_ai_quality_failure(rec3["result_status"])

    body4, rec4 = store.invoke(profile_id="GROQ_REFLECTION_REASONER", trade_id="SUCCESS_SAMPLE")
    assert body4 is not None
    assert rec4["result_status"] == "SUCCESS"
    assert "api_key" not in json.dumps(body4)


def test_replay_rate_limit_sets_retry_after(tmp_path: Path):
    packets = _packets()
    # Seed canary fixtures keyed by actual case ids for first pending case
    store = ReplayFixtureStore()
    first = str(packets[0]["trade_id"])
    store.fixtures[f"GROQ_REFLECTION_REASONER:{first}:blind_reflection_v2_3"] = {
        "fixture_key": f"GROQ_REFLECTION_REASONER:{first}",
        "result_status": "RATE_LIMITED",
        "headers": {"retry-after": "33"},
        "http_status": 429,
        "body": None,
    }
    out = run_quota_aware_calibration(
        root=tmp_path,
        packets=packets,
        manifest_checksum="replay_429",
        use_real_ai=False,
        max_batches_this_invocation=1,
        run_critic=False,
        replay_fixtures=store,
    )
    groq = out["state_summary"]["transport"]["GROQ_REFLECTION_REASONER"]
    assert groq["HTTP_429_count"] >= 1
    assert groq["retry_after"] == 33.0 or float(groq["retry_after"]) == 33.0
    assert out["quality"]["V2_3_TERMINAL_STATUS"] in {
        "INCOMPLETE_PROVIDER_CAPACITY",
        "INCOMPLETE",
    }
    assert out["quality"]["quality_gates_evaluated"] is False
    # 429 must not be labeled as AI quality failure terminal
    assert out["quality"]["V2_3_TERMINAL_STATUS"] != "VALID_SAMPLE_QUALITY_FAILED"
    assert out["quality"]["http_429_never_ai_quality_failure"] is True


def test_checkpoint_corruption_detection_and_migration(tmp_path: Path):
    packets = _packets()
    good = build_initial_checkpoint(packets=packets, manifest_checksum="c1", model_id="m")
    good["completed_case_ids"] = good["case_ids"][:3]
    good["pending_case_ids"] = good["case_ids"][:5]  # overlap corruption
    for cid in good["completed_case_ids"]:
        good["case_results"][cid] = {"transport_status": "SUCCESS"}
    report = detect_checkpoint_corruption(good)
    assert report["corrupt"] is True
    assert "completed_pending_overlap" in report["issues"]
    repaired = repair_checkpoint_overlap(good)
    assert set(repaired["completed_case_ids"]).isdisjoint(set(repaired["pending_case_ids"]))

    # Unreadable / wrong type
    bad = detect_checkpoint_corruption("not-json")
    assert bad["corrupt"] is True
    assert bad["recommended_action"] == "REBUILD_FROM_MANIFEST"

    # Persist corrupt file and ensure load + rebuild path does not crash
    path = tmp_path / ".nexus_runtime" / "blind_reflection_v23_checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    loaded = load_checkpoint(tmp_path)
    assert loaded is not None
    assert loaded.get("_checkpoint_load_error")

    v2 = {
        "schema_version": 2,
        "calibration_manifest_checksum": "mig",
        "case_ids": good["case_ids"],
        "completed_case_ids": good["case_ids"][:2],
        "pending_case_ids": good["case_ids"][2:],
        "critic_case_ids": [],
        "critic_resolved_ids": [],
        "case_results": {cid: {"transport_status": "SUCCESS"} for cid in good["case_ids"][:2]},
        "provider_429_count": 0,
        "provider_attempt_counts": {"GROQ_REFLECTION_REASONER": 2},
        "provider_success_counts": {"GROQ_REFLECTION_REASONER": 2},
        "stage": "GROQ_CALIBRATION_BATCH",
    }
    migrated = migrate_checkpoint_v2_to_v3(v2, model_id="m")
    assert migrated["schema_version"] == 3
    assert "GROQ_REFLECTION_REASONER" in migrated["transport"]


def test_terminal_denominator_validation():
    bad = {
        "evidence_packet_constructible_ratio": make_ratio(0, 0),
        "reflection_prompt_delivery_ratio_on_attempts": {"numerator": 0, "denominator": 0, "value": 1.0, "status": "NOT_APPLICABLE"},
        "full_calibration_completion_ratio": make_ratio(10, 80, status_override="INCOMPLETE_SAMPLE"),
        "blind_valid_schema_ratio": make_ratio(0, 0),
        "informative_classification_ratio_overall": make_ratio(0, 0),
        "informative_classification_ratio_on_sufficient_cases": make_ratio(0, 0),
        "blind_agreement_ratio_on_sufficient_cases": make_ratio(0, 0),
        "critic_resolution_ratio": {
            "numerator": 0,
            "denominator": 5,
            "value": None,
            "status": "SAMBANOVA_PROVIDER_BLOCKED",
        },
        "quality_gates_passed": False,
        "V2_3_TERMINAL_STATUS": "INCOMPLETE_PROVIDER_CAPACITY",
        "transport": {
            "GROQ_REFLECTION_REASONER": {"HTTP_429_count": 3},
        },
    }
    # Force a zero-denom value=1.0 issue
    check = validate_terminal_denominators(bad)
    assert check["valid"] is False
    assert any("zero_denom_nonzero_value" in i or "blocked_status_has_value" in i for i in check["issues"])

    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="term", model_id="m")
    q = evaluate_quality(state)
    assert q["terminal_denominator_validation"]["valid"] is True
    assert q["quality_gates_evaluated"] is False


def test_independent_provider_queues_not_coupled():
    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="ind", model_id="m")
    state["transport"]["GROQ_REFLECTION_REASONER"]["HTTP_429_count"] = 0
    state["transport"]["SAMBANOVA_INDEPENDENT_CRITIC"]["HTTP_429_count"] = 9
    state["transport"]["CEREBRAS_RESEARCH_NORMALIZER"]["HTTP_429_count"] = 0
    state["transport"]["GROQ_MAIN_REASONER"]["HTTP_429_count"] = 0
    assert (
        state["transport"]["GROQ_REFLECTION_REASONER"]["HTTP_429_count"]
        != state["transport"]["SAMBANOVA_INDEPENDENT_CRITIC"]["HTTP_429_count"]
    )
    # Samba blocked must not invent Groq 429
    state["completed_case_ids"] = state["case_ids"][:10]
    state["pending_case_ids"] = state["case_ids"][10:]
    state["critic_case_ids"] = state["case_ids"][:4]
    state["critic_pending_ids"] = list(state["critic_case_ids"])
    state["sambanova_stage"] = "SAMBANOVA_CAPACITY_BLOCKED"
    for cid in state["completed_case_ids"]:
        state["case_results"][cid] = {
            "reflection_prompt_with_packet": True,
            "evidence_sufficiency": "EVIDENCE_SUFFICIENT",
            "process_classification": "GOOD_PROCESS_WIN",
            "deterministic_expected": "BAD_PROCESS_WIN",
        }
    q = evaluate_quality(state)
    assert q["critic_resolution_status"] == "SAMBANOVA_PROVIDER_BLOCKED"
    assert q["transport"]["GROQ_REFLECTION_REASONER"]["HTTP_429_count"] == 0


def test_save_checkpoint_strips_secrets(tmp_path: Path):
    packets = _packets()
    state = build_initial_checkpoint(packets=packets, manifest_checksum="sec", model_id="m")
    state["api_key"] = "SHOULD_NOT_PERSIST"
    state["raw_prompt"] = "secret prompt"
    save_checkpoint(tmp_path, state)
    loaded = json.loads(
        (tmp_path / ".nexus_runtime" / "blind_reflection_v23_checkpoint.json").read_text(encoding="utf-8")
    )
    assert "api_key" not in loaded
    assert "raw_prompt" not in loaded
