"""Tests for V18-E AI Gateway and Tool Sandbox."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.nexus_ai_gateway_tool_sandbox.adapters import (
    BaseAdapter,
    build_default_adapters,
)
from backend.nexus_ai_gateway_tool_sandbox.budget import BudgetPolicy
from backend.nexus_ai_gateway_tool_sandbox.constants import (
    ALLOWED_TOOLS,
    BANNED_TOOLS,
    CAPACITY_STATUS,
    HARD_BANS,
    MAX_PROVIDER_ATTEMPTS_PER_REQUEST,
    PIPELINE_CONTINUE,
    PROVIDER_IDS,
    ROUTE_ROLES,
)
from backend.nexus_ai_gateway_tool_sandbox.contracts import (
    GATEWAY_RESPONSE_SCHEMA,
    ToolCallRequest,
)
from backend.nexus_ai_gateway_tool_sandbox.fixtures import (
    build_fixture_gateway,
    fixture_catalog,
    run_fixture,
)
from backend.nexus_ai_gateway_tool_sandbox.gateway import UnifiedAIGateway
from backend.nexus_ai_gateway_tool_sandbox.hard_bans import hard_ban_probe_matrix
from backend.nexus_ai_gateway_tool_sandbox.routing import classify_role
from backend.nexus_ai_gateway_tool_sandbox.tools import ToolSandbox, canonicalize_tool_id

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_provider_ids_cover_founder_set() -> None:
    assert PROVIDER_IDS == (
        "LOCAL",
        "OPENAI_COMPATIBLE",
        "GROQ",
        "SAMBANOVA",
        "OTHER_APPROVED_PROVIDER",
        "DETERMINISTIC_FALLBACK",
    )
    adapters = build_default_adapters(mock=True)
    assert set(adapters) == set(PROVIDER_IDS)


def test_all_adapters_share_typed_contract() -> None:
    adapters = build_default_adapters(mock=True)
    from backend.nexus_ai_gateway_tool_sandbox.contracts import GatewayRequest
    import uuid

    req = GatewayRequest(
        request_id=str(uuid.uuid4()),
        role="SIMPLE",
        prompt="ping",
        payload={"simple": True, "suggested_decision": "WAIT", "confidence": 0.5},
        schema=GATEWAY_RESPONSE_SCHEMA,
        prompt_schema_version="v18_e_gateway_prompt_v1",
    )
    for pid, adapter in adapters.items():
        health = adapter.health()
        assert "available" in health and "status" in health
        parsed, status, meta = adapter.complete(req)
        assert isinstance(status, str)
        assert isinstance(meta, dict)
        if status == "SUCCESS":
            assert isinstance(parsed, dict)
            assert "decision" in parsed
            assert parsed.get("provider_id") == pid or pid == "DETERMINISTIC_FALLBACK"


def test_allowed_tools_match_founder_list() -> None:
    expected = {
        "market_snapshot",
        "candidate",
        "evidence",
        "counter_evidence",
        "regime",
        "data_trust",
        "decision_memory",
        "public_news_context",
        "historical_similar_cases",
        "capture_health",
    }
    assert ALLOWED_TOOLS == frozenset(expected)


def test_banned_tools_match_founder_list() -> None:
    expected = {
        "exchange_write",
        "account_access",
        "wallet_access",
        "api_secret_access",
        "risk_override",
        "leverage_override",
        "lesson_activation",
        "strategy_deployment",
        "code_deployment",
    }
    assert BANNED_TOOLS == frozenset(expected)
    sandbox = ToolSandbox()
    for tool in expected:
        ok, reason = sandbox.authorize(tool)
        assert ok is False
        assert reason == "BANNED_TOOL"


def test_tool_aliases_canonicalize() -> None:
    assert canonicalize_tool_id("market snapshot") == "market_snapshot"
    assert canonicalize_tool_id("Data Trust") == "data_trust"
    assert canonicalize_tool_id("exchange write") == "exchange_write"


def test_routing_simple_candidate_critic() -> None:
    assert classify_role({"simple": True}) == "SIMPLE"
    assert classify_role({"candidate": {"symbol": "BTCUSDT"}}) == "CANDIDATE_INTERPRETATION"
    assert classify_role({"major_contradiction": True}) == "MAJOR_CONTRADICTION_CRITIC"
    assert set(ROUTE_ROLES) == {
        "SIMPLE",
        "CANDIDATE_INTERPRETATION",
        "MAJOR_CONTRADICTION_CRITIC",
    }


def test_simple_routes_to_deterministic() -> None:
    gw = UnifiedAIGateway.from_env(mock=True)
    resp = gw.invoke(
        prompt="simple",
        payload={"simple": True, "suggested_decision": "WAIT", "confidence": 0.4},
        role="SIMPLE",
    )
    assert resp.result_status == "SUCCESS"
    assert resp.provider_id == "DETERMINISTIC_FALLBACK"
    assert resp.busy_loop_count == 0


def test_candidate_routes_to_primary_groq() -> None:
    gw = UnifiedAIGateway.from_env(mock=True)
    resp = gw.invoke(
        prompt="interpret",
        payload={
            "candidate": {"symbol": "BTCUSDT"},
            "suggested_decision": "LONG",
            "confidence": 0.7,
        },
        role="CANDIDATE_INTERPRETATION",
    )
    assert resp.result_status == "SUCCESS"
    assert resp.provider_id == "GROQ"


def test_contradiction_routes_to_critic_sambanova() -> None:
    gw = UnifiedAIGateway.from_env(mock=True)
    resp = gw.invoke(
        prompt="critic",
        payload={
            "major_contradiction": True,
            "critic_decision": "ABSTAIN",
            "critic_confidence": 0.3,
        },
        role="MAJOR_CONTRADICTION_CRITIC",
    )
    assert resp.result_status == "SUCCESS"
    assert resp.provider_id == "SAMBANOVA"


def test_all_providers_down_continue_without_ai() -> None:
    """Founder: status=PROVIDER_CAPACITY_BLOCKED, pipeline=CONTINUE_WITHOUT_AI."""
    unavailable = set(PROVIDER_IDS) - {"DETERMINISTIC_FALLBACK"}
    gw = build_fixture_gateway(
        unavailable=unavailable,
        disable_fallback=True,
    )
    # Also mark DETERMINISTIC unavailable via disable + empty chain effect
    resp = gw.invoke(
        prompt="down",
        payload={"candidate": {"symbol": "ETHUSDT"}, "suggested_decision": "LONG"},
        role="CANDIDATE_INTERPRETATION",
        capacity_decision="WAIT",
    )
    assert resp.result_status == CAPACITY_STATUS
    assert resp.pipeline == PIPELINE_CONTINUE
    assert resp.decision == "WAIT"
    assert resp.capacity_status == CAPACITY_STATUS
    assert resp.busy_loop_count == 0


def test_capacity_abstain_option() -> None:
    gw = build_fixture_gateway(
        unavailable=set(PROVIDER_IDS) - {"DETERMINISTIC_FALLBACK"},
        disable_fallback=True,
    )
    resp = gw.invoke(
        prompt="down",
        payload={"candidate": {"symbol": "SOLUSDT"}},
        capacity_decision="ABSTAIN",
    )
    assert resp.decision == "ABSTAIN"
    assert resp.pipeline == PIPELINE_CONTINUE


def test_timeout_falls_through_chain() -> None:
    adapters = build_default_adapters(mock=True)
    adapters["GROQ"].force_status = "TIMEOUT"
    adapters["OPENAI_COMPATIBLE"].force_status = "TIMEOUT"
    adapters["LOCAL"].force_status = "TIMEOUT"
    # DETERMINISTIC_FALLBACK remains healthy
    gw = UnifiedAIGateway(adapters=adapters)
    resp = gw.invoke(
        prompt="timeout path",
        payload={"candidate": {"symbol": "BTCUSDT"}, "suggested_decision": "WAIT"},
        role="CANDIDATE_INTERPRETATION",
    )
    assert resp.result_status == "SUCCESS"
    assert resp.provider_id == "DETERMINISTIC_FALLBACK"
    assert any(a.result_status == "TIMEOUT" for a in resp.attempts)


def test_budget_policy_blocks_without_busy_loop() -> None:
    gw = UnifiedAIGateway.from_env(mock=True)
    gw.budget = BudgetPolicy(max_tokens=100, max_calls=0)
    resp = gw.invoke(
        prompt="budget",
        payload={"candidate": {"symbol": "BTCUSDT"}},
    )
    assert resp.result_status == "BUDGET_EXCEEDED"
    assert resp.pipeline == PIPELINE_CONTINUE
    assert resp.busy_loop_count == 0


def test_cache_and_dedupe() -> None:
    gw = UnifiedAIGateway.from_env(mock=True)
    payload = {"simple": True, "suggested_decision": "WAIT", "confidence": 0.41}
    first = gw.invoke(prompt="cache-me", payload=payload, role="SIMPLE")
    second = gw.invoke(prompt="cache-me", payload=payload, role="SIMPLE")
    assert first.result_status == "SUCCESS"
    assert second.cache_hit is True
    assert gw.cache.hits >= 1


def test_inflight_dedupe_no_redispatch() -> None:
    gw = UnifiedAIGateway.from_env(mock=True)
    fp_owner = "synthetic"
    # Manually mark inflight
    gw.dedupe._inflight[fp_owner] = None
    # Simulate begin seeing inflight
    state = gw.dedupe.begin(fp_owner)
    assert state is True
    assert gw.dedupe.hits >= 1


def test_audit_records_requests() -> None:
    gw = UnifiedAIGateway.from_env(mock=True)
    gw.invoke(prompt="audit", payload={"simple": True}, role="SIMPLE")
    assert len(gw.audit.events) == 1
    assert gw.audit.events[0].audit_id


def test_banned_tool_denied_no_provider_churn() -> None:
    gw = UnifiedAIGateway.from_env(mock=True)
    resp = gw.invoke(
        prompt="write",
        payload={"simple": True},
        role="SIMPLE",
        tool_calls=[ToolCallRequest("exchange_write", {"qty": 1})],
    )
    assert resp.result_status == "TOOL_DENIED"
    assert resp.decision == "BLOCK"
    assert resp.attempts == []
    assert any("exchange_write" in d for d in resp.tool_denials)


def test_allowed_tool_passes() -> None:
    sandbox = ToolSandbox()
    out = sandbox.execute_readonly("market_snapshot", {"symbol": "BTCUSDT"})
    assert out["ok"] is True
    assert out["mode"] == "READ_ONLY"


def test_no_busy_loop_hard_cap() -> None:
    assert MAX_PROVIDER_ATTEMPTS_PER_REQUEST <= len(PROVIDER_IDS)
    assert "no_busy_loop" in HARD_BANS


def test_fixture_catalog_runs() -> None:
    for name in fixture_catalog():
        out = run_fixture(name)
        assert out["busy_loop_count"] == 0
        assert out["first"]["result_status"]


def test_hard_ban_probe_matrix() -> None:
    matrix = hard_ban_probe_matrix()
    assert matrix["all_banned_denied"] is True
    assert matrix["no_pr26_merge"] is True
    assert matrix["no_pr27_merge"] is True
    assert matrix["on_demand_zero"] is True


def test_provider_fallback_skips_unavailable_once() -> None:
    adapters = build_default_adapters(mock=True, unavailable=frozenset({"GROQ"}))
    gw = UnifiedAIGateway(adapters=adapters)
    resp = gw.invoke(
        prompt="fallback",
        payload={"candidate": {"symbol": "BTCUSDT"}, "suggested_decision": "LONG"},
        role="CANDIDATE_INTERPRETATION",
    )
    assert resp.result_status == "SUCCESS"
    assert resp.provider_id in {"OPENAI_COMPATIBLE", "LOCAL", "DETERMINISTIC_FALLBACK"}
    provider_attempts = [a.provider_id for a in resp.attempts]
    # Each provider attempted at most once.
    assert len(provider_attempts) == len(set(provider_attempts))
