"""Immutable risk gates for the V1.1 execution simulator.

Hard limits (system-wide, cannot be overridden by AI):

  * ``max_leverage_ceiling`` = 50x   (leverage=100x always REJECTED)
  * ``margin_mode``          = ISOLATED only
  * Auto-add-margin          = FORBIDDEN
  * Martingale, averaging_down, risk_increase, stop_widening,
    leverage_increase                = FORBIDDEN
  * Reduce-only that would open new exposure = REJECTED

Configurable bounded limits (per-simulator instance):

  * ``max_positions`` (default 2, bounded validation uses 1)
  * ``max_intents``   (default 2, bounded validation uses 1)
  * ``margin_usdt``   (bounded validation uses 20)
  * ``leverage``      (default 25, bounded validation uses 25)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

MAX_LEVERAGE_CEILING = 50
FORBIDDEN_LEVERAGE_VALUES: frozenset[int] = frozenset({100})
FORBIDDEN_ACTIONS: frozenset[str] = frozenset({
    "risk_increase",
    "stop_widening",
    "leverage_increase",
    "martingale",
    "averaging_down",
    "auto_add_margin",
    "cross_margin",
    "duplicate_exposure",
    "unbounded_pyramiding",
})


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_positions: int
    max_intents: int
    leverage: int
    margin_usdt: Decimal
    margin_mode: str = "ISOLATED"
    max_leverage_ceiling: int = MAX_LEVERAGE_CEILING

    def __post_init__(self) -> None:
        if self.leverage <= 0:
            raise ValueError("leverage_must_be_positive")
        if self.leverage > self.max_leverage_ceiling:
            raise ValueError(f"leverage_exceeds_ceiling {self.leverage} > {self.max_leverage_ceiling}")
        if self.leverage in FORBIDDEN_LEVERAGE_VALUES:
            raise ValueError(f"leverage_forbidden {self.leverage}")
        if self.max_positions <= 0:
            raise ValueError("max_positions_must_be_positive")
        if self.max_intents <= 0:
            raise ValueError("max_intents_must_be_positive")
        if self.margin_mode != "ISOLATED":
            raise ValueError(f"only_isolated_margin_allowed got={self.margin_mode}")


@dataclass
class RiskState:
    """Snapshot passed to ``evaluate_intent`` — never mutated inside the gate."""

    open_position_count: int
    pending_intent_count: int
    open_position_symbols: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reason: str
    detail: dict[str, Any] | None = None
    order_or_policy_mutation: bool = False


def evaluate_intent(
    limits: RiskLimits,
    state: RiskState,
    intent: dict[str, Any],
) -> RiskDecision:
    """Run the fixed risk pipeline against ``intent`` and return a decision.

    ``intent`` is the raw incoming request dict (see
    :class:`~contracts.OrderIntent` for canonical shape). We accept ``dict``
    here to keep the gate cheap for the fuzz harness.
    """
    requested_actions = intent.get("requested_actions") or ()
    if isinstance(requested_actions, str):
        requested_actions = (requested_actions,)
    forbidden_hits = tuple(sorted(set(requested_actions) & FORBIDDEN_ACTIONS))
    if forbidden_hits:
        return RiskDecision(
            allowed=False,
            reason="HARD_RISK_OVERRIDE_REJECTED",
            detail={"forbidden_actions": list(forbidden_hits)},
            order_or_policy_mutation=False,
        )

    margin_mode = str(intent.get("margin_mode") or limits.margin_mode).upper()
    if margin_mode != "ISOLATED":
        return RiskDecision(allowed=False, reason="CROSS_MARGIN_FORBIDDEN")

    leverage = int(intent.get("leverage") or limits.leverage)
    if leverage in FORBIDDEN_LEVERAGE_VALUES:
        return RiskDecision(allowed=False, reason="LEVERAGE_FORBIDDEN_VALUE")
    if leverage > limits.max_leverage_ceiling:
        return RiskDecision(
            allowed=False,
            reason="LEVERAGE_CEILING",
            detail={"leverage": leverage, "ceiling": limits.max_leverage_ceiling},
        )

    reduce_only = bool(intent.get("reduce_only"))
    if state.pending_intent_count >= limits.max_intents:
        return RiskDecision(
            allowed=False,
            reason="MAX_INTENTS",
            detail={"pending": state.pending_intent_count, "max": limits.max_intents},
        )
    if not reduce_only and state.open_position_count >= limits.max_positions:
        return RiskDecision(
            allowed=False,
            reason="MAX_POSITIONS",
            detail={"open": state.open_position_count, "max": limits.max_positions},
        )
    if reduce_only and intent.get("symbol") not in state.open_position_symbols:
        return RiskDecision(
            allowed=False,
            reason="REDUCE_ONLY_WITHOUT_POSITION",
            detail={"symbol": intent.get("symbol")},
        )

    return RiskDecision(allowed=True, reason="PASS")
