"""Kill-switch rules shared by 6H V2 / 12H V3 bounded Demo sessions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


KILL_REASONS = (
    "SESSION_NET_LOSS_BREACH",
    "SINGLE_TRADE_NET_LOSS_BREACH",
    "CONSECUTIVE_LOSSES_BREACH",
    "BAD_PROCESS_OUTCOME",
    "DUPLICATE_ORDER",
    "UNPROTECTED_POSITION",
    "PROTECTION_VERIFY_TIMEOUT",
    "RECONCILIATION_MISMATCH",
    "EXECUTION_OWNER_COUNT_INVALID",
    "PERSISTENCE_FAILURE",
    "RUNTIME_STALL",
    "FEE_CONFIG_EXPIRED",
    "MAINNET_DETECTED",
    "REAL_MONEY_DETECTED",
)


@dataclass
class KillSwitchDecision:
    triggered: bool
    reason: str = ""
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "reason": self.reason,
            "actions": list(self.actions),
            "auto_restart": False,
        }


STOP_ACTIONS = (
    "NEW_ENTRY_BLOCKED",
    "WRITE_WINDOW_CLOSED",
    "CANCEL_PENDING",
    "PRESERVE_PROTECTION",
    "REDUCE_ONLY_FLATTEN",
    "RECONCILE",
    "EXPORT",
    "SESSION_KILLED",
)


def evaluate_kill_switch(
    *,
    session_net_pnl: float,
    max_session_net_loss: float,
    last_trade_net_pnl: float | None,
    max_single_trade_net_loss: float,
    consecutive_losses: int,
    max_consecutive_losses: int,
    bad_process_outcomes: int,
    max_bad_process_outcomes: int,
    duplicate_orders: int,
    unprotected_positions: int,
    protection_verify_timeout: bool,
    reconciliation: str,
    execution_owner_count: int,
    persistence_ok: bool,
    runtime_stall: bool,
    fee_expired: bool,
    mainnet: bool,
    real_money: bool,
) -> KillSwitchDecision:
    checks: list[tuple[bool, str]] = [
        (session_net_pnl < -abs(max_session_net_loss), "SESSION_NET_LOSS_BREACH"),
        (
            last_trade_net_pnl is not None and last_trade_net_pnl < -abs(max_single_trade_net_loss),
            "SINGLE_TRADE_NET_LOSS_BREACH",
        ),
        (consecutive_losses > max_consecutive_losses, "CONSECUTIVE_LOSSES_BREACH"),
        (bad_process_outcomes > max_bad_process_outcomes, "BAD_PROCESS_OUTCOME"),
        (duplicate_orders > 0, "DUPLICATE_ORDER"),
        (unprotected_positions > 0, "UNPROTECTED_POSITION"),
        (protection_verify_timeout, "PROTECTION_VERIFY_TIMEOUT"),
        (str(reconciliation).upper() != "MATCH", "RECONCILIATION_MISMATCH"),
        (int(execution_owner_count) != 1, "EXECUTION_OWNER_COUNT_INVALID"),
        (not persistence_ok, "PERSISTENCE_FAILURE"),
        (runtime_stall, "RUNTIME_STALL"),
        (fee_expired, "FEE_CONFIG_EXPIRED"),
        (mainnet, "MAINNET_DETECTED"),
        (real_money, "REAL_MONEY_DETECTED"),
    ]
    for hit, reason in checks:
        if hit:
            return KillSwitchDecision(triggered=True, reason=reason, actions=list(STOP_ACTIONS))
    return KillSwitchDecision(triggered=False)
