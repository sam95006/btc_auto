"""Demo strategy — capital allocation stack.

Components:
  DemoRiskBudget           — equity-risk calculation from tier
  DemoPositionSizer        — qty from risk budget + stop distance
  LeverageSelector         — 25/30/35x with safety downgrade
  MarginRequirementCalculator — margin from notional / leverage
  LiquidationDistanceGuard — ensure liquidation far enough from entry
  FeeSlippageBuffer        — reserve for fees, slippage, funding
  PortfolioExposureController — portfolio-level caps
  DemoCapitalAllocator     — orchestrator

Defaults: ISOLATED, max_open_demo_positions=1,
          no_averaging_down, no_martingale, auto_add_margin=false.

Leverage does NOT decide max loss — Risk Budget does.
If 25x is unsafe → lower leverage or allow_trade=false.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_strategy.risk_tiers import (
    RiskTier,
    RiskTierName,
    VALIDATION_TIER,
    first_order_tier,
    get_tier,
)

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Defaults ──────────────────────────────────────────────────────────────────
MARGIN_MODE = "ISOLATED"
MAX_OPEN_DEMO_POSITIONS = 1
NO_AVERAGING_DOWN = True
NO_MARTINGALE = True
AUTO_ADD_MARGIN = False

LEVERAGE_OPTIONS = (25, 30, 35)
DEFAULT_LEVERAGE = 25

FEE_RATE_TAKER = 0.00055
FEE_RATE_MAKER = 0.0002
SLIPPAGE_BUFFER_PCT = 0.05
FUNDING_RESERVE_PERIODS = 3
DEFAULT_FUNDING_RATE = 0.0001

MIN_LIQUIDATION_DISTANCE_PCT = 2.0


@dataclass
class RiskBudgetResult:
    equity: float
    tier: RiskTier
    risk_pct: float
    risk_amount_usd: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "equity": self.equity,
            "tier": self.tier.to_dict(),
            "riskPct": self.risk_pct,
            "riskAmountUsd": self.risk_amount_usd,
            "source": self.source,
        }


class DemoRiskBudget:
    """Compute the dollar risk budget from equity and tier."""

    def compute(
        self,
        equity: float,
        tier: RiskTier | RiskTierName | str,
        requested_risk_pct: float | None = None,
        *,
        source: str = "fixture",
    ) -> RiskBudgetResult:
        if isinstance(tier, (str, RiskTierName)):
            tier = get_tier(tier)

        risk_pct = tier.clamp(requested_risk_pct if requested_risk_pct else tier.max_risk_pct)
        risk_usd = equity * risk_pct / 100.0

        return RiskBudgetResult(
            equity=equity,
            tier=tier,
            risk_pct=risk_pct,
            risk_amount_usd=risk_usd,
            source=source,
        )


@dataclass
class PositionSizeResult:
    qty: float
    notional: float
    entry_price: float
    stop_distance_pct: float
    risk_per_unit: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "qty": self.qty,
            "notional": self.notional,
            "entryPrice": self.entry_price,
            "stopDistancePct": self.stop_distance_pct,
            "riskPerUnit": self.risk_per_unit,
        }


class DemoPositionSizer:
    """Size position from risk budget and stop distance."""

    def compute(
        self,
        risk_amount_usd: float,
        entry_price: float,
        stop_distance_pct: float,
    ) -> PositionSizeResult:
        if entry_price <= 0 or stop_distance_pct <= 0:
            return PositionSizeResult(
                qty=0.0, notional=0.0, entry_price=entry_price,
                stop_distance_pct=stop_distance_pct, risk_per_unit=0.0,
            )

        risk_per_unit = entry_price * stop_distance_pct / 100.0
        qty = risk_amount_usd / risk_per_unit if risk_per_unit > 0 else 0.0
        qty = math.floor(qty * 1_000_000) / 1_000_000
        notional = qty * entry_price

        return PositionSizeResult(
            qty=qty,
            notional=notional,
            entry_price=entry_price,
            stop_distance_pct=stop_distance_pct,
            risk_per_unit=risk_per_unit,
        )


@dataclass
class LeverageResult:
    selected: int
    original_request: int
    downgraded: bool
    reason: str
    margin_mode: str = MARGIN_MODE

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "originalRequest": self.original_request,
            "downgraded": self.downgraded,
            "reason": self.reason,
            "marginMode": self.margin_mode,
        }


class LeverageSelector:
    """Select leverage from {25, 30, 35}x with safety downgrade.

    Leverage does NOT decide max loss — Risk Budget does.
    If the selected leverage causes unsafe liquidation distance,
    we lower leverage or block the trade entirely.
    """

    def __init__(self, options: tuple[int, ...] = LEVERAGE_OPTIONS) -> None:
        self._options = sorted(options)

    def select(
        self,
        requested: int = DEFAULT_LEVERAGE,
        stop_distance_pct: float = 1.0,
        min_liq_distance_pct: float = MIN_LIQUIDATION_DISTANCE_PCT,
        *,
        allow_dynamic: bool = False,
    ) -> LeverageResult:
        # Discrete major-band path (25/30/35). Invalid requests snap to lowest option
        # unless allow_dynamic=True (autonomous tiered 5–50 policy).
        if requested not in self._options:
            if allow_dynamic:
                candidates = list(range(max(int(requested), 1), 0, -1))
                fallback_low = 1
            else:
                requested = self._options[0]
                candidates = sorted(self._options, reverse=True)
                fallback_low = self._options[0]
        else:
            candidates = sorted((o for o in self._options if o <= requested), reverse=True)
            fallback_low = self._options[0]

        for lev in candidates:
            if (not allow_dynamic) and requested in self._options and lev > requested:
                continue
            liq_dist = 100.0 / lev
            if liq_dist >= min_liq_distance_pct and liq_dist > stop_distance_pct * 1.5:
                return LeverageResult(
                    selected=lev,
                    original_request=requested,
                    downgraded=lev != requested,
                    reason=f"{lev}x safe: liq_dist={liq_dist:.2f}% > stop*1.5={stop_distance_pct*1.5:.2f}%",
                )

        liq_dist = 100.0 / fallback_low
        safe = liq_dist >= min_liq_distance_pct and liq_dist > stop_distance_pct * 1.5
        return LeverageResult(
            selected=fallback_low if safe else 0,
            original_request=requested,
            downgraded=True,
            reason=(
                f"Downgraded to {fallback_low}x" if safe
                else f"NO safe leverage: even {fallback_low}x liq_dist={liq_dist:.2f}% insufficient"
            ),
        )


@dataclass
class MarginResult:
    margin_required: float
    notional: float
    leverage: int
    margin_mode: str = MARGIN_MODE
    auto_add_margin: bool = AUTO_ADD_MARGIN

    def to_dict(self) -> dict[str, Any]:
        return {
            "marginRequired": self.margin_required,
            "notional": self.notional,
            "leverage": self.leverage,
            "marginMode": self.margin_mode,
            "autoAddMargin": self.auto_add_margin,
        }


class MarginRequirementCalculator:
    def compute(self, notional: float, leverage: int) -> MarginResult:
        margin = notional / leverage if leverage > 0 else notional
        return MarginResult(
            margin_required=round(margin, 4),
            notional=notional,
            leverage=leverage,
        )


@dataclass
class LiquidationGuardResult:
    safe: bool
    liq_distance_pct: float
    stop_distance_pct: float
    leverage: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "safe": self.safe,
            "liqDistancePct": self.liq_distance_pct,
            "stopDistancePct": self.stop_distance_pct,
            "leverage": self.leverage,
            "reason": self.reason,
        }


class LiquidationDistanceGuard:
    def check(
        self,
        leverage: int,
        stop_distance_pct: float,
        min_liq_distance_pct: float = MIN_LIQUIDATION_DISTANCE_PCT,
    ) -> LiquidationGuardResult:
        liq_dist = 100.0 / leverage if leverage > 0 else 100.0
        safe = liq_dist >= min_liq_distance_pct and liq_dist > stop_distance_pct * 1.5
        reason = (
            f"OK: liq {liq_dist:.2f}% > min {min_liq_distance_pct}% and > stop*1.5"
            if safe
            else f"UNSAFE: liq {liq_dist:.2f}% too close (stop={stop_distance_pct:.2f}%, min={min_liq_distance_pct}%)"
        )
        return LiquidationGuardResult(
            safe=safe,
            liq_distance_pct=round(liq_dist, 4),
            stop_distance_pct=stop_distance_pct,
            leverage=leverage,
            reason=reason,
        )


@dataclass
class FeeSlippageResult:
    fee_estimate_usd: float
    slippage_estimate_usd: float
    funding_reserve_usd: float
    total_buffer_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "feeEstimateUsd": self.fee_estimate_usd,
            "slippageEstimateUsd": self.slippage_estimate_usd,
            "fundingReserveUsd": self.funding_reserve_usd,
            "totalBufferUsd": self.total_buffer_usd,
        }


class FeeSlippageBuffer:
    """Reserve funds for fees, slippage, and funding payments."""

    def compute(
        self,
        notional: float,
        *,
        fee_rate: float = FEE_RATE_TAKER,
        slippage_pct: float = SLIPPAGE_BUFFER_PCT,
        funding_rate: float = DEFAULT_FUNDING_RATE,
        funding_periods: int = FUNDING_RESERVE_PERIODS,
    ) -> FeeSlippageResult:
        fee_open = notional * fee_rate
        fee_close = notional * fee_rate
        fee_total = fee_open + fee_close

        slippage = notional * slippage_pct / 100.0
        funding_reserve = notional * abs(funding_rate) * funding_periods

        return FeeSlippageResult(
            fee_estimate_usd=round(fee_total, 4),
            slippage_estimate_usd=round(slippage, 4),
            funding_reserve_usd=round(funding_reserve, 4),
            total_buffer_usd=round(fee_total + slippage + funding_reserve, 4),
        )


@dataclass
class ExposureCheckResult:
    allowed: bool
    current_positions: int
    max_positions: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "currentPositions": self.current_positions,
            "maxPositions": self.max_positions,
            "reason": self.reason,
        }


class PortfolioExposureController:
    """Enforce portfolio-level constraints."""

    def __init__(
        self,
        max_positions: int = MAX_OPEN_DEMO_POSITIONS,
    ) -> None:
        self._max_positions = max_positions

    def check(self, current_open: int = 0) -> ExposureCheckResult:
        allowed = current_open < self._max_positions
        return ExposureCheckResult(
            allowed=allowed,
            current_positions=current_open,
            max_positions=self._max_positions,
            reason=(
                "OK" if allowed
                else f"Max demo positions reached ({current_open}/{self._max_positions})"
            ),
        )


# ── Orchestrator ──────────────────────────────────────────────────────────────

@dataclass
class AllocationDecision:
    allow_trade: bool
    symbol: str
    direction: str
    qty: float
    notional: float
    margin_required: float
    leverage: int
    risk_tier: str
    risk_pct: float
    risk_amount_usd: float
    fee_buffer_usd: float
    liq_distance_pct: float
    block_reasons: list[str] = field(default_factory=list)
    margin_mode: str = MARGIN_MODE
    auto_add_margin: bool = AUTO_ADD_MARGIN
    no_averaging_down: bool = NO_AVERAGING_DOWN
    no_martingale: bool = NO_MARTINGALE
    source: str = "fixture"
    decided_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowTrade": self.allow_trade,
            "symbol": self.symbol,
            "direction": self.direction,
            "qty": self.qty,
            "notional": self.notional,
            "marginRequired": self.margin_required,
            "leverage": self.leverage,
            "riskTier": self.risk_tier,
            "riskPct": self.risk_pct,
            "riskAmountUsd": self.risk_amount_usd,
            "feeBufferUsd": self.fee_buffer_usd,
            "liqDistancePct": self.liq_distance_pct,
            "blockReasons": self.block_reasons,
            "marginMode": self.margin_mode,
            "autoAddMargin": self.auto_add_margin,
            "noAveragingDown": self.no_averaging_down,
            "noMartingale": self.no_martingale,
            "source": self.source,
            "decidedAtMs": self.decided_at_ms,
            "researchOnly": True,
        }


class DemoCapitalAllocator:
    """Orchestrates the full allocation pipeline.

    Pipeline:
      1. Risk budget from tier + equity
      2. Position sizing from budget + stop distance
      3. Leverage selection with safety downgrade
      4. Margin requirement
      5. Liquidation distance guard
      6. Fee/slippage buffer check
      7. Portfolio exposure check
    """

    def __init__(self) -> None:
        self._risk_budget = DemoRiskBudget()
        self._sizer = DemoPositionSizer()
        self._leverage = LeverageSelector()
        self._margin_calc = MarginRequirementCalculator()
        self._liq_guard = LiquidationDistanceGuard()
        self._fee_buffer = FeeSlippageBuffer()
        self._exposure = PortfolioExposureController()

    def allocate(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_distance_pct: float,
        equity: float,
        *,
        tier: RiskTier | RiskTierName | str | None = None,
        requested_leverage: int = DEFAULT_LEVERAGE,
        is_first_order: bool = False,
        current_open_positions: int = 0,
        funding_rate: float = DEFAULT_FUNDING_RATE,
        source: str = "fixture",
        allow_dynamic_leverage: bool = False,
    ) -> AllocationDecision:
        block_reasons: list[str] = []

        if is_first_order or tier is None:
            active_tier = first_order_tier() if is_first_order else VALIDATION_TIER
        else:
            active_tier = get_tier(tier) if isinstance(tier, (str, RiskTierName)) else tier

        budget = self._risk_budget.compute(equity, active_tier, source=source)

        exposure = self._exposure.check(current_open_positions)
        if not exposure.allowed:
            block_reasons.append(exposure.reason)

        lev_result = self._leverage.select(
            requested=requested_leverage,
            stop_distance_pct=stop_distance_pct,
            allow_dynamic=allow_dynamic_leverage,
        )
        if lev_result.selected == 0:
            block_reasons.append(lev_result.reason)

        effective_leverage = lev_result.selected or requested_leverage

        liq_check = self._liq_guard.check(effective_leverage, stop_distance_pct)
        if not liq_check.safe:
            block_reasons.append(liq_check.reason)

        sizing = self._sizer.compute(budget.risk_amount_usd, entry_price, stop_distance_pct)

        margin = self._margin_calc.compute(sizing.notional, effective_leverage)

        fees = self._fee_buffer.compute(
            sizing.notional,
            funding_rate=funding_rate,
        )

        total_capital_needed = margin.margin_required + fees.total_buffer_usd
        if total_capital_needed > equity and sizing.qty > 0:
            block_reasons.append(
                f"Capital needed ${total_capital_needed:.2f} > equity ${equity:.2f}"
            )

        allow_trade = len(block_reasons) == 0 and sizing.qty > 0

        return AllocationDecision(
            allow_trade=allow_trade,
            symbol=symbol,
            direction=direction,
            qty=sizing.qty,
            notional=sizing.notional,
            margin_required=margin.margin_required,
            leverage=effective_leverage,
            risk_tier=active_tier.name.value,
            risk_pct=budget.risk_pct,
            risk_amount_usd=budget.risk_amount_usd,
            fee_buffer_usd=fees.total_buffer_usd,
            liq_distance_pct=liq_check.liq_distance_pct,
            block_reasons=block_reasons,
            source=source,
        )
