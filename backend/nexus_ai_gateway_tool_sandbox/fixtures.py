"""Deterministic fixtures for V18-E AI Gateway and Tool Sandbox."""
from __future__ import annotations

from typing import Any

from backend.nexus_ai_gateway_tool_sandbox.adapters import build_default_adapters
from backend.nexus_ai_gateway_tool_sandbox.constants import (
    ALLOWED_TOOLS,
    BANNED_TOOLS,
    PROVIDER_IDS,
    RANDOM_SEED,
)
from backend.nexus_ai_gateway_tool_sandbox.contracts import ToolCallRequest
from backend.nexus_ai_gateway_tool_sandbox.gateway import UnifiedAIGateway


def fixture_catalog() -> dict[str, dict[str, Any]]:
    """Named deterministic scenarios (no network)."""
    return {
        "simple_deterministic": {
            "role": "SIMPLE",
            "prompt": "summarize regime briefly",
            "payload": {
                "simple": True,
                "suggested_decision": "WAIT",
                "confidence": 0.5,
            },
            "expect_provider": "DETERMINISTIC_FALLBACK",
            "expect_status": "SUCCESS",
        },
        "candidate_primary": {
            "role": "CANDIDATE_INTERPRETATION",
            "prompt": "interpret candidate BTCUSDT",
            "payload": {
                "candidate": {"symbol": "BTCUSDT", "score": 0.71},
                "suggested_decision": "LONG",
                "confidence": 0.66,
                "supporting_evidence_ids": ["ev1"],
            },
            "expect_provider": "GROQ",
            "expect_status": "SUCCESS",
        },
        "critic_contradiction": {
            "role": "MAJOR_CONTRADICTION_CRITIC",
            "prompt": "resolve major contradiction",
            "payload": {
                "major_contradiction": True,
                "critic_decision": "ABSTAIN",
                "critic_confidence": 0.35,
                "contradicting_evidence_ids": ["ce1", "ce2"],
            },
            "expect_provider": "SAMBANOVA",
            "expect_status": "SUCCESS",
        },
        "all_remote_down_capacity": {
            "role": "CANDIDATE_INTERPRETATION",
            "prompt": "candidate while remotes down",
            "payload": {"candidate": {"symbol": "ETHUSDT"}, "suggested_decision": "LONG"},
            "disable_fallback": True,
            "unavailable": set(PROVIDER_IDS) - {"DETERMINISTIC_FALLBACK"},
            "expect_status": "PROVIDER_CAPACITY_BLOCKED",
            "expect_pipeline": "CONTINUE_WITHOUT_AI",
            "expect_decision": "WAIT",
        },
        "banned_tool": {
            "role": "SIMPLE",
            "prompt": "attempt exchange write",
            "payload": {"simple": True},
            "tool_calls": [ToolCallRequest("exchange_write", {"symbol": "BTCUSDT"})],
            "expect_status": "TOOL_DENIED",
        },
        "allowed_tool": {
            "role": "SIMPLE",
            "prompt": "read market snapshot",
            "payload": {"simple": True, "suggested_decision": "WAIT"},
            "tool_calls": [ToolCallRequest("market_snapshot", {"symbol": "BTCUSDT"})],
            "expect_status": "SUCCESS",
        },
        "budget_exceeded": {
            "role": "CANDIDATE_INTERPRETATION",
            "prompt": "over budget",
            "payload": {"candidate": {"symbol": "SOLUSDT"}},
            "budget_calls": 0,
            "expect_status": "BUDGET_EXCEEDED",
            "expect_pipeline": "CONTINUE_WITHOUT_AI",
        },
        "cache_hit": {
            "role": "SIMPLE",
            "prompt": "cacheable simple",
            "payload": {"simple": True, "suggested_decision": "WAIT", "confidence": 0.4},
            "run_twice": True,
            "expect_second_cache_hit": True,
        },
    }


def build_fixture_gateway(
    *,
    unavailable: set[str] | frozenset[str] | None = None,
    disable_fallback: bool = False,
    budget_calls: int | None = None,
    budget_tokens: int | None = None,
) -> UnifiedAIGateway:
    adapters = build_default_adapters(
        mock=True,
        unavailable=frozenset(unavailable or ()),
    )
    gw = UnifiedAIGateway(
        adapters=adapters,
        disable_deterministic_fallback=disable_fallback,
    )
    if budget_calls is not None:
        gw.budget.max_calls = budget_calls
    if budget_tokens is not None:
        gw.budget.max_tokens = budget_tokens
    return gw


def run_fixture(name: str) -> dict[str, Any]:
    catalog = fixture_catalog()
    if name not in catalog:
        raise KeyError(f"unknown_fixture:{name}")
    spec = catalog[name]
    gw = build_fixture_gateway(
        unavailable=spec.get("unavailable"),
        disable_fallback=bool(spec.get("disable_fallback")),
        budget_calls=spec.get("budget_calls"),
    )
    kwargs: dict[str, Any] = {
        "prompt": spec["prompt"],
        "payload": spec.get("payload"),
        "role": spec.get("role"),
        "tool_calls": spec.get("tool_calls"),
    }
    first = gw.invoke(**kwargs)
    second = None
    if spec.get("run_twice"):
        second = gw.invoke(**kwargs)
    return {
        "fixture": name,
        "seed": RANDOM_SEED,
        "first": first.to_dict(),
        "second": second.to_dict() if second else None,
        "provider_statuses": gw.provider_statuses(),
        "busy_loop_count": gw.busy_loop_count,
        "allowed_tools": sorted(ALLOWED_TOOLS),
        "banned_tools": sorted(BANNED_TOOLS),
        "spec": {k: v for k, v in spec.items() if k not in {"tool_calls", "unavailable"}},
    }
