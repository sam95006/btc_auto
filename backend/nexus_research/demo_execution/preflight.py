"""Demo order execution — preflight gate checks.

All gates must pass before an intent reaches READY_FOR_AUTHORIZATION.
If any gate fails, the order is PREFLIGHT_BLOCKED.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_execution.intent import DemoOrderIntent

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False


@dataclass
class PreflightGate:
    name: str
    passed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "reason": self.reason}


@dataclass
class PreflightResult:
    all_passed: bool
    gates: list[PreflightGate] = field(default_factory=list)
    checked_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    order_sent: bool = field(default=False, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allPassed": self.all_passed,
            "gates": [g.to_dict() for g in self.gates],
            "checkedAtMs": self.checked_at_ms,
            "orderSent": False,
        }


class DemoOrderPreflight:
    """Run all preflight gates for a DemoOrderIntent."""

    ALLOWED_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})
    ALLOWED_SIDES = frozenset({"Buy", "Sell"})
    MAX_LEVERAGE = 35
    MIN_LEVERAGE = 1

    def __init__(
        self,
        *,
        max_open_positions: int = 1,
        current_open_positions: int = 0,
        ambiguous_orders_exist: bool = False,
        allowed_symbols: frozenset[str] | set[str] | None = None,
        max_leverage: int | None = None,
        min_leverage: int | None = None,
    ) -> None:
        self._max_open = max_open_positions
        self._current_open = current_open_positions
        self._ambiguous_exist = ambiguous_orders_exist
        self._allowed_symbols = (
            frozenset(s.upper() for s in allowed_symbols)
            if allowed_symbols is not None
            else self.ALLOWED_SYMBOLS
        )
        self._max_leverage = int(max_leverage) if max_leverage is not None else self.MAX_LEVERAGE
        self._min_leverage = int(min_leverage) if min_leverage is not None else self.MIN_LEVERAGE

    def check(self, intent: DemoOrderIntent) -> PreflightResult:
        gates: list[PreflightGate] = []

        sym_ok = intent.symbol.upper() in self._allowed_symbols
        gates.append(PreflightGate(
            name="symbol_allowed",
            passed=sym_ok,
            reason=f"{intent.symbol} {'allowed' if sym_ok else 'not in allowlist'}",
        ))

        gates.append(PreflightGate(
            name="side_valid",
            passed=intent.side in self.ALLOWED_SIDES,
            reason=f"{intent.side} {'valid' if intent.side in self.ALLOWED_SIDES else 'invalid'}",
        ))

        gates.append(PreflightGate(
            name="qty_positive",
            passed=intent.qty > 0,
            reason=f"qty={intent.qty}",
        ))

        lev_ok = self._min_leverage <= intent.leverage <= self._max_leverage
        gates.append(PreflightGate(
            name="leverage_in_range",
            passed=lev_ok,
            reason=f"leverage={intent.leverage} (range {self._min_leverage}-{self._max_leverage})",
        ))

        gates.append(PreflightGate(
            name="stop_loss_set",
            passed=intent.stop_loss_price > 0,
            reason=f"stopLoss={intent.stop_loss_price}",
        ))

        sl_valid = (
            (intent.side == "Buy" and intent.stop_loss_price < intent.entry_price)
            or (intent.side == "Sell" and intent.stop_loss_price > intent.entry_price)
        )
        gates.append(PreflightGate(
            name="stop_loss_direction",
            passed=sl_valid,
            reason=(
                f"SL={intent.stop_loss_price} vs entry={intent.entry_price} "
                f"side={intent.side}"
            ),
        ))

        gates.append(PreflightGate(
            name="client_order_id_present",
            passed=bool(intent.client_order_id),
            reason=f"clientOrderId={'set' if intent.client_order_id else 'missing'}",
        ))

        pos_ok = self._current_open < self._max_open
        gates.append(PreflightGate(
            name="position_capacity",
            passed=pos_ok,
            reason=f"open={self._current_open}/{self._max_open}",
        ))

        gates.append(PreflightGate(
            name="no_ambiguous_orders",
            passed=not self._ambiguous_exist,
            reason="ambiguous orders block new orders" if self._ambiguous_exist else "no ambiguous orders",
        ))

        gates.append(PreflightGate(
            name="order_not_sent",
            passed=not intent.order_sent,
            reason="order_sent must be False",
        ))

        all_passed = all(g.passed for g in gates)
        return PreflightResult(all_passed=all_passed, gates=gates)
