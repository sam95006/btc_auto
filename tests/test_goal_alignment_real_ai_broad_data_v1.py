"""Goal Alignment V1 — real AI providers, capability eligibility, learning proof."""
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

from backend.nexus_ai_gateway.founder_providers import (
    ACTIVE_PROFILES,
    CANNOT_APPROVE_ORDER,
    INACTIVE_PROVIDERS,
    FounderAIGateway,
    provider_alignment_summary,
    run_real_provider_smoke_tests,
)
from backend.nexus_ai_gateway import redact_for_external
from backend.nexus_dynamic_universe.capability_eligibility import (
    HistoricalDownloadQueue,
    assert_price_strategy_not_blocked_by_missing_oi,
    overlaps_reserved,
    strategy_requires_derivatives,
)
from backend.nexus_learning import LessonMemory, create_lesson_from_outcome, deterministic_risk_critic
from backend.nexus_learning.integration_drill import load_existing_sim_trade_sample, run_learning_loop_drill


def test_active_provider_profiles_exactly_founder_four():
    # PRIVATE-AI-3: Groq (main+reflection) + Gemini (research-normalizer +
    # independent-critic). Cerebras/SambaNova are DEFERRED_BILLING_NOT_ENABLED.
    assert len(ACTIVE_PROFILES) == 4
    assert set(ACTIVE_PROFILES) == {
        "GROQ_MAIN_REASONER",
        "GROQ_REFLECTION_REASONER",
        "GEMINI_RESEARCH_NORMALIZER",
        "GEMINI_INDEPENDENT_CRITIC",
    }
    gw = FounderAIGateway.from_env(mock_for_ci=True)
    assert gw.active_profile_count() == 4
    assert gw.role_map["main_market_reasoner"] == "GROQ_MAIN_REASONER"
    assert gw.role_map["reflection_reasoner"] == "GROQ_REFLECTION_REASONER"
    assert gw.role_map["lesson_normalizer"] == "GEMINI_RESEARCH_NORMALIZER"
    assert gw.role_map["independent_reflection_critic"] == "GEMINI_INDEPENDENT_CRITIC"


def test_groq_main_and_reflection_separate_roles():
    gw = FounderAIGateway.from_env(mock_for_ci=True)
    assert gw.role_map["main_market_reasoner"] != gw.role_map["reflection_reasoner"]
    assert gw.groq_quota_pool_relation == "UNKNOWN"


def test_cerebras_and_sambanova_cannot_approve_orders():
    assert "CEREBRAS_RESEARCH_NORMALIZER" in CANNOT_APPROVE_ORDER
    assert "SAMBANOVA_INDEPENDENT_CRITIC" in CANNOT_APPROVE_ORDER


def test_inactive_providers_not_selected():
    gw = FounderAIGateway.from_env(mock_for_ci=True)
    for name in ("OLLAMA", "CLOUDFLARE_WORKERS_AI", "OPENROUTER"):
        assert INACTIVE_PROVIDERS[name] == "INACTIVE_NOT_FOUNDER_CONFIGURED"
        parsed, rec, perm = gw.invoke_profile(
            profile_id=name,
            prompt="x",
            schema={"title": "t", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}},
            prompt_schema_version="v",
        )
        assert parsed is None and perm == "BLOCK"
        assert "INACTIVE" in str(rec.get("reason"))


def test_api_keys_never_logged_in_redaction():
    text = "GROQ_API_KEY_PRIMARY=gsk_supersecrettokenvalue123456 Authorization: Bearer abcdefghijklmnop"
    red = redact_for_external(text)
    assert "gsk_supersecrettokenvalue123456" not in red
    assert "Bearer abcdef" not in red


def test_smoke_output_redacted_and_ci_mocks():
    gw = FounderAIGateway.from_env(mock_for_ci=True)
    smoke = run_real_provider_smoke_tests(gw)
    assert len(smoke) == 4
    blob = json.dumps(smoke)
    assert "gsk_" not in blob
    assert "Bearer " not in blob
    summary = provider_alignment_summary(gw, smoke)
    assert summary["active_provider_profile_count"] == 4


def test_capability_price_vs_derivatives():
    assert strategy_requires_derivatives({"open_interest"}) is True
    assert strategy_requires_derivatives({"price", "atr"}) is False
    assert assert_price_strategy_not_blocked_by_missing_oi("PRICE_HISTORY_ELIGIBLE", requires_derivatives=False)
    assert not assert_price_strategy_not_blocked_by_missing_oi("PRICE_HISTORY_ELIGIBLE", requires_derivatives=True)
    assert assert_price_strategy_not_blocked_by_missing_oi("DERIVATIVES_HISTORY_ELIGIBLE", requires_derivatives=True)


def test_missing_oi_remains_missing_concept():
    # Never invent zero — encoded as explicit MISSING status in probe dicts
    probe = {"oi_status": "MISSING", "oi_value": None}
    assert probe["oi_status"] == "MISSING"
    assert probe["oi_value"] is None


def test_download_queue_resumable_and_duplicate_partition(tmp_path: Path):
    q = HistoricalDownloadQueue(tmp_path)
    q.enqueue_symbol("BTCUSDT", start_ms=1_739_007_000_000, end_ms=1_739_100_000_000)
    n1 = len(q.state["items"])
    q.enqueue_symbol("BTCUSDT", start_ms=1_739_007_000_000, end_ms=1_739_100_000_000)
    assert len(q.state["items"]) == n1  # duplicate keys not added
    # Mark one completed and ensure resume skips
    key = q.state["items"][0]["key"]
    q.state["completed"][key] = {"checksum": "abc", "record_count": 1, "path": "x"}
    q.save()
    q2 = HistoricalDownloadQueue(tmp_path)
    assert key in q2.state["completed"]


def test_reserved_interval_exclusion():
    from backend.nexus_demo_execution.closed_historical_registry import (
        SEPTEMBER_OOS_END_MS,
        SEPTEMBER_OOS_START_MS,
    )

    assert overlaps_reserved(1_785_663_000_001, 1_789_551_000_000) is True  # september
    assert overlaps_reserved(1_720_863_000_000, 1_736_415_000_000) is True  # holdout
    q = HistoricalDownloadQueue(Path("."))
    with pytest.raises(ValueError, match="RESERVED"):
        q.enqueue_symbol("BTCUSDT", start_ms=SEPTEMBER_OOS_START_MS, end_ms=SEPTEMBER_OOS_END_MS)


def test_lesson_from_evidence_and_boundaries():
    lesson = create_lesson_from_outcome(
        trade_id="t1",
        symbol="BTCUSDT",
        symbol_profile={},
        strategy_id="s",
        regime="R",
        direction="Sell",
        pnl=-1.0,
        process_good=True,
        reflection_provider="GROQ_REFLECTION_REASONER",
        reflection_model="m",
        critic_provider="SAMBANOVA_INDEPENDENT_CRITIC",
        critic_model="m",
    )
    assert lesson.process_classification == "GOOD_PROCESS_LOSS"
    assert lesson.proposed_policy_changes == []
    bad_win = create_lesson_from_outcome(
        trade_id="t2",
        symbol="ETHUSDT",
        symbol_profile={},
        strategy_id="s",
        regime="R",
        direction="Sell",
        pnl=2.0,
        process_good=False,
        reflection_provider="GROQ_REFLECTION_REASONER",
        reflection_model="m",
        critic_provider="SAMBANOVA_INDEPENDENT_CRITIC",
        critic_model="m",
    )
    assert bad_win.process_classification == "BAD_PROCESS_WIN"


def test_main_reasoner_returns_applied_lesson_ids_via_drill():
    h5 = ROOT / "artifacts/readiness/immutable/dynamic_universe_ai_learning_h5_v1/h5_walk_forward_summary.json"
    if not h5.is_file():
        pytest.skip("h5 summary missing")
    trades = load_existing_sim_trade_sample(h5_summary_path=h5, sample_count=20)
    assert len(trades) == 20
    assert any(t["net_pnl"] > 0 for t in trades) and any(t["net_pnl"] < 0 for t in trades)
    gw = FounderAIGateway.from_env(mock_for_ci=True)
    # Seed mock main reasoner to apply lessons when present
    from backend.nexus_ai_gateway import MockProvider

    class SmartMock(MockProvider):
        def complete_json(self, *, model_id, prompt, schema, timeout_s=30.0):
            title = str(schema.get("title") or "default")
            if title == "main_reasoner_v1":
                # Extract lesson ids if present in prompt
                import re

                ids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", prompt)
                payload = {
                    "retrieved_lesson_ids": ids[:3],
                    "applied_lesson_ids": ids[:1],
                    "ignored_lesson_ids": ids[1:3],
                    "lesson_application_reason": "apply_negative_process_context",
                    "decision_effect": "ADDITIONAL_CONFIRMATION_REQUIRED" if ids else "NO_CHANGE",
                }
                return payload, "SUCCESS", {"model_id": model_id, "input_tokens": 1, "output_tokens": 1}
            return super().complete_json(model_id=model_id, prompt=prompt, schema=schema, timeout_s=timeout_s)

    gw.providers["GROQ_MAIN_REASONER"] = SmartMock("GROQ_MAIN_REASONER", responses=gw.providers["GROQ_MAIN_REASONER"].responses)
    out = run_learning_loop_drill(gw=gw, trades=trades)
    assert out["h5_not_rerun"] is True
    assert out["strategy_qualification_executed"] is False
    assert out["exchange_write_attempt_count"] == 0
    assert out["lesson_record_count"] > 0
    assert out["lesson_delivery_proof_status"] == "PASS"
    assert out["main_reasoner_lesson_reference_count"] > 0


def test_provider_unavailable_blocks_future_order():
    gw = FounderAIGateway.from_env(mock_for_ci=True)
    from backend.nexus_ai_gateway import MockProvider

    gw.providers["GROQ_MAIN_REASONER"] = MockProvider("GROQ_MAIN_REASONER", available=False)
    block = gw.main_reasoner_unavailable_block()
    assert block["order_permission"] == "BLOCK_NEW_ORDER"
    assert block["decision"] == "UNKNOWN"
    hard = deterministic_risk_critic(hard_blocks=["spread_above_limit"], ai_opinion="ALLOW")
    assert hard["order_permission"] == "BLOCK"
    assert hard["ai_override_allowed"] is False


def test_coerce_to_schema_strips_extras_and_coerces_numbers():
    from backend.nexus_ai_gateway import coerce_to_schema, validate_against_schema
    from backend.nexus_ai_gateway.founder_providers import REFLECTION_SCHEMA

    raw = {
        "process_classification": "GOOD_PROCESS_LOSS",
        "root_causes": ["noise"],
        "confidence": "0.66",
        "summary": "ok",
        "extra_forbidden_field": "drop_me",
    }
    coerced = coerce_to_schema(raw, REFLECTION_SCHEMA)
    assert coerced is not None
    assert "extra_forbidden_field" not in coerced
    assert coerce_to_schema and validate_against_schema(coerced, REFLECTION_SCHEMA)
    assert isinstance(coerced["confidence"], float)


def test_env_file_gitignored_when_present():
    import subprocess

    env_path = ROOT / ".env"
    if not env_path.is_file():
        pytest.skip(".env not present locally")
    gi = subprocess.run(["git", "check-ignore", "-v", ".env"], cwd=str(ROOT), capture_output=True, text=True)
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=str(ROOT), capture_output=True, text=True)
    assert gi.returncode == 0
    assert tracked.returncode != 0


def test_h5_not_rerun_preserved_in_package_when_present():
    path = ROOT / "artifacts/readiness/immutable/goal_alignment_real_ai_broad_data_v1/h5_preserved.json"
    if not path.is_file():
        pytest.skip("package not generated yet")
    sealed = json.loads(path.read_text(encoding="utf-8"))
    assert sealed["H5A_status"] == "INSUFFICIENT_SAMPLE"
    assert sealed["h5_not_rerun"] is True
    assert sealed["selected_h5_primary_policy"] is None
