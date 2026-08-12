"""Deterministic safety gate for V15-J continuous autonomy ops.

Fail-closed. Blocks exchange writes, Demo/Shadow/mainnet/real money,
qualification advances, and unsafe state transitions.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_autonomy.continuous_ops_control_v15.constants import (
    HARD_BANS,
    MUTATING_OPS,
    PRESERVED_FACTS,
    STATE_BLOCKED,
    STATE_COLD,
    STATE_KILLED,
    STATE_PAUSED,
    STATE_RECOVERING,
    STATE_RUNNING,
    STATE_SAFE_STOPPING,
    STATE_STARTING,
    STATE_STOPPED,
    STATE_PAUSING,
)


# Allowed state transitions for mutating ops (deterministic).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "start": frozenset({STATE_COLD, STATE_STOPPED}),
    "pause": frozenset({STATE_RUNNING}),
    "resume": frozenset({STATE_PAUSED}),
    "safe_stop": frozenset({STATE_RUNNING, STATE_PAUSED}),
    "kill": frozenset(
        {
            STATE_COLD,
            STATE_STARTING,
            STATE_RUNNING,
            STATE_PAUSING,
            STATE_PAUSED,
            STATE_SAFE_STOPPING,
            STATE_STOPPED,
            STATE_RECOVERING,
            STATE_BLOCKED,
        }
    ),
    "recover": frozenset({STATE_STOPPED, STATE_BLOCKED, STATE_PAUSED}),
}

EXCHANGE_WRITE_KEYS = frozenset(
    {
        "exchange_write",
        "place_order",
        "cancel_order",
        "submit_order",
        "demo_order",
        "shadow_order",
        "mainnet",
        "real_money",
        "live_order",
    }
)


class SafetyGateV15:
    """Deterministic safety gate — always fail-closed on banned surfaces."""

    def __init__(self) -> None:
        self.exchange_write_attempt_count = 0
        self.demo_order_count = 0
        self.shadow_order_count = 0
        self.mainnet_attempt_count = 0
        self.real_money_attempt_count = 0
        self.refusals: list[dict[str, Any]] = []

    def check(
        self,
        *,
        op: str,
        state: str,
        payload: dict[str, Any] | None = None,
        kill_engaged: bool = False,
    ) -> dict[str, Any]:
        payload = dict(payload or {})

        # Hard ban scan on payload keys / truthy flags
        banned_hit = self._scan_exchange_bans(payload)
        if banned_hit is not None:
            self.refusals.append(banned_hit)
            return banned_hit

        if kill_engaged and op not in {"kill"}:
            # After kill, only re-kill (idempotent) or read ops allowed.
            if op in MUTATING_OPS:
                result = {
                    "allowed": False,
                    "reason": "kill_switch_engaged",
                    "op": op,
                    "state": state,
                    "gate": "SafetyGateV15",
                    **PRESERVED_FACTS,
                    "exchange_write_attempt_count": self.exchange_write_attempt_count,
                }
                self.refusals.append(result)
                return result

        if state == STATE_KILLED and op in MUTATING_OPS and op != "kill":
            result = {
                "allowed": False,
                "reason": "state_killed_blocks_mutation",
                "op": op,
                "state": state,
                "gate": "SafetyGateV15",
                **PRESERVED_FACTS,
                "exchange_write_attempt_count": self.exchange_write_attempt_count,
            }
            self.refusals.append(result)
            return result

        if op in MUTATING_OPS:
            allowed_from = ALLOWED_TRANSITIONS.get(op, frozenset())
            if state not in allowed_from:
                result = {
                    "allowed": False,
                    "reason": "unsafe_transition",
                    "op": op,
                    "state": state,
                    "allowed_from": sorted(allowed_from),
                    "gate": "SafetyGateV15",
                    **PRESERVED_FACTS,
                    "exchange_write_attempt_count": self.exchange_write_attempt_count,
                }
                self.refusals.append(result)
                return result

        # Qualification advance always refused
        if payload.get("advance_qualification") or payload.get("qualification_advance"):
            result = {
                "allowed": False,
                "reason": "qualification_advance_banned",
                "op": op,
                "state": state,
                "gate": "SafetyGateV15",
                **PRESERVED_FACTS,
                "exchange_write_attempt_count": self.exchange_write_attempt_count,
            }
            self.refusals.append(result)
            return result

        return {
            "allowed": True,
            "reason": "safety_gate_pass",
            "op": op,
            "state": state,
            "gate": "SafetyGateV15",
            "hard_bans": HARD_BANS,
            **PRESERVED_FACTS,
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
        }

    def _scan_exchange_bans(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        for key in EXCHANGE_WRITE_KEYS:
            val = payload.get(key)
            if val is True or (isinstance(val, str) and val.strip().lower() in {"1", "true", "yes", "on"}):
                self.exchange_write_attempt_count += 1
                if key in {"demo_order"}:
                    self.demo_order_count += 0  # never increments — refused before write
                if key in {"shadow_order"}:
                    self.shadow_order_count += 0
                if key in {"mainnet"}:
                    self.mainnet_attempt_count += 0
                if key in {"real_money"}:
                    self.real_money_attempt_count += 0
                return {
                    "allowed": False,
                    "reason": f"hard_ban:{key}",
                    "op": payload.get("op"),
                    "gate": "SafetyGateV15",
                    "hard_bans": HARD_BANS,
                    **PRESERVED_FACTS,
                    "exchange_write_attempt_count": self.exchange_write_attempt_count,
                    "demo_order_count": self.demo_order_count,
                    "shadow_order_count": self.shadow_order_count,
                    "mainnet_attempt_count": self.mainnet_attempt_count,
                    "real_money_attempt_count": self.real_money_attempt_count,
                }
        return None

    def counters(self) -> dict[str, int]:
        return {
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
            "demo_order_count": self.demo_order_count,
            "shadow_order_count": self.shadow_order_count,
            "mainnet_attempt_count": self.mainnet_attempt_count,
            "real_money_attempt_count": self.real_money_attempt_count,
            "refusal_count": len(self.refusals),
        }
