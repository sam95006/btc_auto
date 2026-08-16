"""Composed product health/readiness — application, optional DB, AI config, Shadow read-only."""
from __future__ import annotations

import os
from typing import Any

from backend.nexus_api_contract import validate_contract as validate_api_contract
from backend.nexus_event_contract import validate_contract as validate_event_contract
from backend.nexus_persistence_pg.runtime import PostgresRuntimeConfig
from backend.nexus_shadow_watch.watch import ACTIVE_CAMPAIGN_ID, collect_campaign_watch


def _ai_provider_health() -> dict[str, Any]:
    """Public/product health must never inspect AI provider secret values.

    Credential presence is owned by ``nexus-runtime-staging``. The API may only
    echo an allow-listed sanitized status injected by Runtime, defaulting to
    ``NOT_CONFIGURED``.
    """
    status = (os.getenv("NEXUS_AI_PROVIDER_PUBLIC_STATUS") or "NOT_CONFIGURED").strip().upper()
    if status not in {"NOT_CONFIGURED", "CONFIGURED", "DEGRADED"}:
        status = "NOT_CONFIGURED"
    return {
        "configured": status == "CONFIGURED",
        "status": status,
        "secret_boundary": "runtime_owned",
    }


def compose_health(*, campaign_id: str = ACTIVE_CAMPAIGN_ID) -> dict[str, Any]:
    pg = PostgresRuntimeConfig.from_env()
    pg_health = pg.health()
    runtime_binding = (os.getenv("NEXUS_RUNTIME_BINDING") or "LOCAL_SHADOW").upper()
    shadow = (
        {
            "campaign_id": campaign_id,
            "process_alive": None,
            "runtime_state": "UNAVAILABLE_NOT_BOUND",
            "evidence": {"persistence_health": None},
            "safety": {"exchange_write": 0},
        }
        if runtime_binding == "UNAVAILABLE"
        else collect_campaign_watch(campaign_id=campaign_id)
    )
    api = validate_api_contract()
    events = validate_event_contract()
    return {
        "schema": "v18_3_3_product_health_v1",
        "application": {"status": "OK", "live_trading_wired": False},
        "postgres": pg_health,
        "ai_provider": _ai_provider_health(),
        "shadow_readonly": {
            "campaign_id": campaign_id,
            "process_alive": shadow.get("process_alive"),
            "runtime_state": shadow.get("runtime_state"),
            "persistence_health": shadow.get("evidence", {}).get("persistence_health"),
            "exchange_write": shadow.get("safety", {}).get("exchange_write"),
            "binding": runtime_binding,
        },
        "contracts": {
            "api_ok": api["ok"],
            "event_ok": events["ok"],
        },
    }


def compose_readiness(*, campaign_id: str = ACTIVE_CAMPAIGN_ID) -> dict[str, Any]:
    health = compose_health(campaign_id=campaign_id)
    pg_ready = health["postgres"].get("db_ready", False) or not health["postgres"].get(
        "runtime_enabled", False
    )
    contracts_ready = health["contracts"]["api_ok"] and health["contracts"]["event_ok"]
    shadow_ok = (
        health["shadow_readonly"].get("binding") == "UNAVAILABLE"
        or health["shadow_readonly"].get("persistence_health") == "PASS"
    )
    ready = contracts_ready and shadow_ok and (
        health["postgres"].get("status") in {"NOT_CONFIGURED", "DISABLED"} or pg_ready
    )
    return {
        "schema": "v18_3_3_product_readiness_v1",
        "ready": ready,
        "checks": {
            "contracts": contracts_ready,
            "shadow_readonly": shadow_ok,
            "postgres_optional": pg_ready,
        },
        "health": health,
    }
