"""Research observe authorization — never enables trading or mainnet."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

ALLOWED_SCOPES: frozenset[str] = frozenset(
    {
        "observe_diagnostics",
        "authorize_research_campaign_plan",
        "authorize_fixture_replay",
        "authorize_lesson_pipeline_inspect",
    }
)

FORBIDDEN_SCOPES: frozenset[str] = frozenset(
    {
        "mainnet",
        "real_trade",
        "exchange_write",
        "demo_order",
        "shadow_order",
        "formal_wf",
        "real_oos",
        "strategy_promotion",
        "arm_execution",
    }
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def authorize_research_observe(
    *,
    scope: str,
    actor_tier: str,
    identity_source: str,
) -> dict[str, Any]:
    """Authorize research observation only. Fail-closed on trade/mainnet scopes."""
    cleaned = str(scope or "").strip().lower()
    if cleaned in FORBIDDEN_SCOPES or any(tok in cleaned for tok in FORBIDDEN_SCOPES):
        return {
            "ok": False,
            "authorized": False,
            "scope": cleaned,
            "error": "forbidden_scope_real_trade_or_mainnet",
            "researchOnly": True,
            "realExecutionEnabled": False,
            "exchangeWriteEnabled": False,
            "mainnetShortcut": False,
            "realTradeShortcut": False,
            "founderOnly": True,
            "memberAccessible": False,
        }

    if cleaned not in ALLOWED_SCOPES:
        return {
            "ok": False,
            "authorized": False,
            "scope": cleaned,
            "error": "unknown_or_disallowed_research_scope",
            "allowedScopes": sorted(ALLOWED_SCOPES),
            "researchOnly": True,
            "realExecutionEnabled": False,
            "founderOnly": True,
            "memberAccessible": False,
        }

    return {
        "ok": True,
        "authorized": True,
        "scope": cleaned,
        "actor": {"tier": actor_tier, "identitySource": identity_source},
        "authorizedAt": _utc(),
        "expiresPolicy": "session_bound_research_only",
        "researchOnly": True,
        "observeOnly": True,
        "realExecutionEnabled": False,
        "armEnabled": False,
        "exchangeWriteEnabled": False,
        "mainnetShortcut": False,
        "realTradeShortcut": False,
        "founderOnly": True,
        "memberAccessible": False,
        "note": "Research observe authorization granted — trading remains disabled.",
    }
