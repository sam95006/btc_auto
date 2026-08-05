"""Deployment environment guard — LOCAL/STAGING only."""
from __future__ import annotations

import os
from typing import Any

from backend.nexus_publishing_gateway.constants import (
    DEPLOYMENT_ENVIRONMENTS,
    FORBIDDEN_ENVIRONMENTS,
)
from backend.nexus_publishing_gateway.exceptions import EnvironmentGuardError


def resolve_environment(explicit: str | None = None) -> str:
    raw = (explicit or os.environ.get("NEXUS_PUBLISHING_ENV") or os.environ.get("NEXUS_ENV") or "LOCAL")
    env = str(raw).strip().upper()
    if env in {"DEV", "DEVELOPMENT", "TEST", "CI"}:
        env = "LOCAL"
    return env


def assert_local_or_staging(explicit: str | None = None) -> str:
    env = resolve_environment(explicit)
    if env in FORBIDDEN_ENVIRONMENTS or env not in DEPLOYMENT_ENVIRONMENTS:
        raise EnvironmentGuardError(f"publishing_gateway_forbidden_env:{env}")
    # Hard-ban live exchange / billing flags if present
    if os.environ.get("EXCHANGE_WRITE", "").lower() in {"1", "true", "yes"}:
        raise EnvironmentGuardError("publishing_gateway_exchange_write_banned")
    if os.environ.get("NEXUS_LIVE_BILLING", "").lower() in {"1", "true", "yes"}:
        raise EnvironmentGuardError("publishing_gateway_live_billing_banned")
    if os.environ.get("MAINNET", "").lower() in {"1", "true", "yes"}:
        raise EnvironmentGuardError("publishing_gateway_mainnet_banned")
    return env


def environment_status() -> dict[str, Any]:
    env = resolve_environment()
    return {
        "environment": env,
        "allowed": env in DEPLOYMENT_ENVIRONMENTS,
        "production_deploy": False,
        "live_billing": False,
        "exchange_write": False,
    }
