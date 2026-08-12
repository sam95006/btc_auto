"""Health + read-only observability for Founder-private control plane."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


FORBIDDEN_OBSERVABILITY_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "token",
        "private_key",
        "authorization",
        "strategy_parameters",
        "account_balance",
        "wallet_address",
    }
)


def build_health(
    *,
    state: str,
    mode: str | None,
    kill_switch_engaged: bool,
    exchange_write_attempt_count: int,
    checkpoint_count: int,
    run_id: str | None,
) -> dict[str, Any]:
    healthy = (
        state not in {"FAILED_SAFE", "KILLED"}
        and exchange_write_attempt_count == 0
        and not kill_switch_engaged
    )
    return {
        "schema": "v10_private_control_plane_health",
        "created_at": _utc(),
        "healthy": healthy,
        "state": state,
        "mode": mode,
        "run_id": run_id,
        "kill_switch_engaged": kill_switch_engaged,
        "exchange_write_attempt_count": exchange_write_attempt_count,
        "checkpoint_count": checkpoint_count,
        "exchange_writes_permitted": False,
        "public_api_exposed": False,
    }


def build_observability(
    *,
    state: str,
    mode: str | None,
    kill_switch_engaged: bool,
    kill_switch_reason: str | None,
    exchange_write_attempt_count: int,
    checkpoint_count: int,
    transition_count: int,
    run_id: str | None,
    allowed_modes: list[str],
    commands_invoked: list[str],
) -> dict[str, Any]:
    """Read-only observability snapshot — no secrets, no strategy params."""
    snap = {
        "schema": "v10_private_control_plane_observability",
        "created_at": _utc(),
        "read_only": True,
        "founder_private": True,
        "public_product_exposure": False,
        "state": state,
        "mode": mode,
        "run_id": run_id,
        "allowed_modes": list(allowed_modes),
        "kill_switch_engaged": kill_switch_engaged,
        "kill_switch_reason": kill_switch_reason,
        "exchange_write_attempt_count": exchange_write_attempt_count,
        "checkpoint_count": checkpoint_count,
        "transition_count": transition_count,
        "commands_invoked": list(commands_invoked),
        "formal_trading_state": {
            "formal_walk_forward_executed": False,
            "oos_executed": False,
            "demo_order_count": 0,
            "shadow_order_count": 0,
            "exchange_write_attempt_count": exchange_write_attempt_count,
            "deployment_started": False,
            "mainnet": False,
            "real_money": False,
        },
        "secrets_present": False,
        "account_information_present": False,
        "strategy_parameters_present": False,
        "profitability_claim": None,
    }
    leaked = [k for k in snap if k.lower() in FORBIDDEN_OBSERVABILITY_KEYS]
    if leaked:
        raise RuntimeError(f"observability_secret_keys:{leaked}")
    return snap
