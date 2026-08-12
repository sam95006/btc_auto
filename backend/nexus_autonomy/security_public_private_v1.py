"""Public vs private route / schema separation guards."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from backend.nexus_autonomy.security_constants_v1 import (
    PRIVATE_LESSON_FIELDS,
    PRIVATE_STRATEGY_PARAM_FIELDS,
)
from backend.nexus_autonomy.security_exceptions_v1 import PublicPrivateBoundaryError


def _walk_keys(obj: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            keys.append(str(k))
            keys.extend(_walk_keys(v, path))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            keys.extend(_walk_keys(v, f"{prefix}[{i}]"))
    elif is_dataclass(obj) and not isinstance(obj, type):
        keys.extend(_walk_keys(asdict(obj), prefix))
    return keys


def assert_public_schema(payload: Any, *, context: str = "public") -> dict[str, Any]:
    """Reject private lesson memory / strategy params in public-facing payloads."""
    if is_dataclass(payload) and not isinstance(payload, type):
        data = asdict(payload)
    elif isinstance(payload, dict):
        data = payload
    else:
        data = {"_value": payload}

    keys = set(_walk_keys(data))
    lesson_hits = sorted(keys & PRIVATE_LESSON_FIELDS)
    strategy_hits = sorted(keys & PRIVATE_STRATEGY_PARAM_FIELDS)

    # Also scan serialized JSON for nested private markers
    blob = json.dumps(data, default=str).lower()
    if "raw_provider_prompt" in blob or "raw_provider_response" in blob:
        raise PublicPrivateBoundaryError(f"{context}:provider_raw_in_public")

    if lesson_hits:
        raise PublicPrivateBoundaryError(f"{context}:private_lesson_fields:{','.join(lesson_hits)}")
    if strategy_hits:
        raise PublicPrivateBoundaryError(f"{context}:private_strategy_fields:{','.join(strategy_hits)}")
    return {"ok": True, "context": context, "key_count": len(keys)}


def redact_account_identifiers(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with account identifiers / keys redacted for public views."""
    REDACT_KEYS = {
        "api_key",
        "api_secret",
        "account_id",
        "uid",
        "member_id",
        "wallet_address",
        "order_id",
        "order_link_id",
        "x-bapi-api-key",
        "x-bapi-sign",
    }

    def _redact(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if str(k).lower() in REDACT_KEYS:
                    out[k] = "***"
                else:
                    out[k] = _redact(v)
            return out
        if isinstance(obj, list):
            return [_redact(x) for x in obj]
        return obj

    return _redact(payload)


def public_private_route_inventory() -> dict[str, Any]:
    """Static inventory of public vs founder-private route modules."""
    public_modules = [
        "backend.api.market_public_routes",
        "backend.api.market_chart_routes",
        "backend.api.market_sector_routes",
        "backend.api.market_scanner_routes",
        "backend.api.market_intelligence_routes",
        "backend.api.nexus_market_data_routes",
    ]
    private_modules = [
        "backend.api.founder_private_routes",
        "backend.nexus_autonomy.private_observability_v1",
        "backend.nexus_learning",
        "backend.nexus_autonomy.private_event_ledger_v1",
    ]
    demo_authorized = [
        "backend.nexus_demo_execution.api_routes",
        "backend.nexus_research.demo_autonomous.api_routes",
    ]
    return {
        "public_route_modules": public_modules,
        "private_route_modules": private_modules,
        "demo_authorized_route_modules": demo_authorized,
        "graphs_separate": True,
        "note": "demo_authorized routes may import write clients; public product routes must not",
    }


def prove_lesson_not_publicly_serializable() -> dict[str, Any]:
    private_lesson = {
        "lesson_id": "L-1",
        "symbol": "BTCUSDT",
        "process_classification": "BAD_PROCESS",
        "immediate_safe_actions": ["block_symbol"],
        "temporary_controls": [{"action": "block_symbol"}],
    }
    public_ok = {"status": "ok", "symbol_count": 3, "source": "BYBIT_MAINNET_LINEAR"}
    assert_public_schema(public_ok, context="public_market")
    blocked = False
    try:
        assert_public_schema(private_lesson, context="public_api")
    except PublicPrivateBoundaryError:
        blocked = True
    if not blocked:
        raise PublicPrivateBoundaryError("lesson_serialization_not_blocked")
    return {
        "private_lesson_public_exposure_count": 0,
        "lesson_block_enforced": True,
    }


def prove_strategy_params_not_public() -> dict[str, Any]:
    private = {"strategy_id": "S1", "strategy_parameters": {"entry_threshold": 0.2}}
    blocked = False
    try:
        assert_public_schema(private, context="public_api")
    except PublicPrivateBoundaryError:
        blocked = True
    if not blocked:
        raise PublicPrivateBoundaryError("strategy_params_not_blocked")
    return {
        "private_strategy_public_exposure_count": 0,
        "strategy_block_enforced": True,
    }
