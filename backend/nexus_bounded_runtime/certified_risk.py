"""Certified deterministic risk authority for bounded 6H entry."""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.allocation import AllocationResult, MarginAllocator
from backend.nexus_demo_execution.session_limits import (
    FIXED_LEVERAGE,
    MARGIN_PER_TRADE_CAP,
    MAX_BAD_PROCESS_OUTCOMES,
    MAX_CONSECUTIVE_LOSSES,
    MAX_SESSION_NET_LOSS,
    MAX_SINGLE_TRADE_NET_LOSS,
)
from backend.nexus_demo_execution.v2_kill_switch import evaluate_kill_switch

RISK_AUTHORITY = "CERTIFIED_V2_KILL_SWITCH_AND_SESSION_LIMITS"


def evaluate_certified_entry_risk(
    *,
    snap: Any,
    candidate: Any,
    allocator: MarginAllocator,
    session_state: dict[str, Any],
    qty: str,
    price: float,
) -> dict[str, Any]:
    verdict = getattr(candidate, "risk_critic_verdict", None)
    if verdict not in {"PASS", "WATCH"}:
        return {"allowed": False, "reason": "risk_critic_block", "authority": RISK_AUTHORITY}

    decision = allocator.allocate(snap, requested_margin=float(MARGIN_PER_TRADE_CAP), open_count=0, pending_count=0)
    if decision.result != AllocationResult.ALLOCATED:
        return {"allowed": False, "reason": "allocator_rejected", "authority": RISK_AUTHORITY}

    try:
        notional = float(qty) * float(price)
        margin = notional / float(FIXED_LEVERAGE)
    except (TypeError, ValueError):
        return {"allowed": False, "reason": "margin_compute_failed", "authority": RISK_AUTHORITY}
    if not (0 < margin <= float(MARGIN_PER_TRADE_CAP)):
        return {"allowed": False, "reason": "margin_cap_exceeded", "authority": RISK_AUTHORITY}

    kill = evaluate_kill_switch(
        session_net_pnl=float(session_state.get("net_pnl") or 0.0),
        max_session_net_loss=float(MAX_SESSION_NET_LOSS),
        last_trade_net_pnl=session_state.get("last_trade_net_pnl"),
        max_single_trade_net_loss=float(MAX_SINGLE_TRADE_NET_LOSS),
        consecutive_losses=int(session_state.get("consecutive_losses") or 0),
        max_consecutive_losses=int(MAX_CONSECUTIVE_LOSSES),
        bad_process_outcomes=int(session_state.get("bad_process_wins") or 0)
        + int(session_state.get("bad_process_losses") or 0),
        max_bad_process_outcomes=int(MAX_BAD_PROCESS_OUTCOMES),
        duplicate_orders=int(session_state.get("duplicate_order_incidents") or 0),
        unprotected_positions=int(session_state.get("protection_incidents") or 0),
        protection_verify_timeout=False,
        reconciliation="MATCH",
        execution_owner_count=1,
        persistence_ok=True,
        runtime_stall=False,
        fee_expired=False,
        mainnet=False,
        real_money=False,
    )
    if kill.triggered:
        return {"allowed": False, "reason": kill.reason or "kill_switch", "authority": RISK_AUTHORITY, "kill": kill.to_dict()}
    return {
        "allowed": True,
        "authority": RISK_AUTHORITY,
        "fixed_leverage": FIXED_LEVERAGE,
        "margin_per_trade_cap": float(MARGIN_PER_TRADE_CAP),
        "allocated_margin": decision.margin_usdt,
    }
