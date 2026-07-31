"""Candidate-specific trade geometry — no fixed ±0.8% default as a strategy.

Hard gates (must not be lowered here):
  net_rr_min = MIN_NET_REWARD_RISK_RATIO (1.2)
  net_reward_to_cost_min = MIN_NET_REWARD_TO_COST (1.5)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_demo_execution.session_limits import (
    COST_UNCERTAINTY_BUFFER_RATE,
    FUNDING_CONSERVATIVE_BUFFER_RATE,
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
)

NET_RR_MIN = MIN_NET_REWARD_RISK_RATIO
NET_REWARD_TO_COST_MIN = MIN_NET_REWARD_TO_COST
MIN_TICK_BUFFER_MULT = 2.0
STRATEGY_NOISE_BUFFER_BPS = 2.0


@dataclass
class GeometryResult:
    entry_price: float | str
    stop_loss: float | str
    take_profit: float | str
    gross_reward: float | str
    gross_risk: float | str
    total_cost: float | str
    net_reward: float | str
    net_risk: float | str
    gross_rr: float | str
    net_rr: float | str
    geometry_source: str
    invalidation_reason: str
    target_reason: str
    time_stop: str | None
    allowed: bool
    block_reason: str
    labels: list[str] = field(default_factory=list)
    inputs_missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, str) and v.strip().upper() in {"", "MISSING", "UNKNOWN", "UNAVAILABLE", "N/A"}:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _round_to_tick(price: float, tick: float | None) -> float:
    if tick is None or tick <= 0:
        return price
    precision = max(0, min(12, len(str(tick).rstrip("0").split(".")[-1]) if "." in str(tick) else 0))
    steps = round(price / tick)
    return round(steps * tick, precision or 8)


def estimate_costs(
    *,
    notional: float,
    fee_rate: float,
    spread_bps: float,
    slippage_bps: float,
    funding_rate: float | None,
) -> dict[str, float]:
    entry_fee = notional * fee_rate
    exit_fee = notional * fee_rate
    slip = notional * (max(spread_bps, 0.0) + max(slippage_bps, 0.0)) / 10000.0
    if funding_rate is None:
        funding = notional * FUNDING_CONSERVATIVE_BUFFER_RATE
    else:
        funding = abs(notional * funding_rate)
    uncertainty = notional * COST_UNCERTAINTY_BUFFER_RATE
    total = entry_fee + exit_fee + slip + funding + uncertainty
    return {
        "entry_fee": entry_fee,
        "exit_fee": exit_fee,
        "slippage": slip,
        "funding": funding,
        "uncertainty": uncertainty,
        "total_cost": total,
    }


def min_stop_distance_price(
    *,
    entry: float,
    spread_bps: float,
    slippage_bps: float,
    tick_size: float | None,
) -> float:
    bps = max(spread_bps, 0.0) + max(slippage_bps, 0.0) + STRATEGY_NOISE_BUFFER_BPS
    dist = entry * (bps / 10000.0)
    if tick_size and tick_size > 0:
        dist = max(dist, tick_size * MIN_TICK_BUFFER_MULT)
    return dist


def compute_structure_geometry(
    *,
    side: str,
    entry_price: float,
    atr: float | None = None,
    recent_swing_high: float | None = None,
    recent_swing_low: float | None = None,
    support: float | None = None,
    resistance: float | None = None,
    liquidity_levels: list[float] | None = None,
    spread_bps: float = 0.0,
    slippage_bps: float = 0.0,
    fee_rate: float | None = None,
    funding_rate: float | None = None,
    tick_size: float | None = None,
    qty: float | None = None,
    time_horizon_sec: int | None = None,
) -> GeometryResult:
    missing: list[str] = []
    if atr is None:
        missing.append("atr")
    if recent_swing_high is None:
        missing.append("recent_swing_high")
    if recent_swing_low is None:
        missing.append("recent_swing_low")
    if support is None:
        missing.append("support")
    if resistance is None:
        missing.append("resistance")

    if fee_rate is None or fee_rate <= 0:
        return GeometryResult(
            entry_price=entry_price,
            stop_loss="UNAVAILABLE",
            take_profit="UNAVAILABLE",
            gross_reward="UNAVAILABLE",
            gross_risk="UNAVAILABLE",
            total_cost="UNAVAILABLE",
            net_reward="UNAVAILABLE",
            net_risk="UNAVAILABLE",
            gross_rr="UNAVAILABLE",
            net_rr="UNAVAILABLE",
            geometry_source="STRUCTURE",
            invalidation_reason="FEE_UNAVAILABLE",
            target_reason="UNAVAILABLE",
            time_stop=None,
            allowed=False,
            block_reason="FEE_RATE_UNKNOWN",
            labels=["FEE_REQUIRED_FOR_COST_AWARE_GEOMETRY"],
            inputs_missing=missing,
        )

    if missing:
        return GeometryResult(
            entry_price=entry_price,
            stop_loss="UNAVAILABLE",
            take_profit="UNAVAILABLE",
            gross_reward="UNAVAILABLE",
            gross_risk="UNAVAILABLE",
            total_cost="UNAVAILABLE",
            net_reward="UNAVAILABLE",
            net_risk="UNAVAILABLE",
            gross_rr="UNAVAILABLE",
            net_rr="UNAVAILABLE",
            geometry_source="STRUCTURE",
            invalidation_reason="GEOMETRY_INPUT_MISSING",
            target_reason="UNAVAILABLE",
            time_stop=None,
            allowed=False,
            block_reason="GEOMETRY_INPUT_MISSING",
            labels=["GEOMETRY_INPUT_MISSING"],
            inputs_missing=missing,
        )

    buy = str(side).lower() in {"buy", "long"}
    min_stop = min_stop_distance_price(
        entry=entry_price, spread_bps=spread_bps, slippage_bps=slippage_bps, tick_size=tick_size
    )

    if buy:
        # Invalidation below structure low / support
        raw_sl = min(v for v in [recent_swing_low, support] if v is not None)
        sl = min(raw_sl, entry_price - min_stop)
        # Target toward resistance / swing high / liquidity above
        candidates = [v for v in [resistance, recent_swing_high, *(liquidity_levels or [])] if v is not None and v > entry_price]
        if atr:
            candidates.append(entry_price + 1.5 * atr)
        if not candidates:
            return GeometryResult(
                entry_price=entry_price,
                stop_loss=_round_to_tick(sl, tick_size),
                take_profit="UNAVAILABLE",
                gross_reward="UNAVAILABLE",
                gross_risk="UNAVAILABLE",
                total_cost="UNAVAILABLE",
                net_reward="UNAVAILABLE",
                net_risk="UNAVAILABLE",
                gross_rr="UNAVAILABLE",
                net_rr="UNAVAILABLE",
                geometry_source="STRUCTURE",
                invalidation_reason="structure_stop",
                target_reason="NO_VALID_UPSIDE_TARGET",
                time_stop=str(time_horizon_sec) if time_horizon_sec else None,
                allowed=False,
                block_reason="BLOCK_INVALID_TRADE_GEOMETRY",
                labels=["NO_STRUCTURE_TARGET"],
                inputs_missing=[],
            )
        tp = max(candidates)
        inv_reason = "below_swing_low_or_support"
        tgt_reason = "resistance_swing_or_liquidity"
    else:
        raw_sl = max(v for v in [recent_swing_high, resistance] if v is not None)
        sl = max(raw_sl, entry_price + min_stop)
        candidates = [v for v in [support, recent_swing_low, *(liquidity_levels or [])] if v is not None and v < entry_price]
        if atr:
            candidates.append(entry_price - 1.5 * atr)
        if not candidates:
            return GeometryResult(
                entry_price=entry_price,
                stop_loss=_round_to_tick(sl, tick_size),
                take_profit="UNAVAILABLE",
                gross_reward="UNAVAILABLE",
                gross_risk="UNAVAILABLE",
                total_cost="UNAVAILABLE",
                net_reward="UNAVAILABLE",
                net_risk="UNAVAILABLE",
                gross_rr="UNAVAILABLE",
                net_rr="UNAVAILABLE",
                geometry_source="STRUCTURE",
                invalidation_reason="structure_stop",
                target_reason="NO_VALID_DOWNSIDE_TARGET",
                time_stop=str(time_horizon_sec) if time_horizon_sec else None,
                allowed=False,
                block_reason="BLOCK_INVALID_TRADE_GEOMETRY",
                labels=["NO_STRUCTURE_TARGET"],
                inputs_missing=[],
            )
        tp = min(candidates)
        inv_reason = "above_swing_high_or_resistance"
        tgt_reason = "support_swing_or_liquidity"

    sl = _round_to_tick(sl, tick_size)
    tp = _round_to_tick(tp, tick_size)
    q = qty if qty and qty > 0 else 1.0
    notional = abs(entry_price * q)

    if buy:
        gross_reward = (tp - entry_price) * q
        gross_risk = (entry_price - sl) * q
    else:
        gross_reward = (entry_price - tp) * q
        gross_risk = (sl - entry_price) * q

    if gross_risk <= 0 or gross_reward <= 0:
        return GeometryResult(
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            gross_reward=gross_reward,
            gross_risk=gross_risk,
            total_cost="UNAVAILABLE",
            net_reward="UNAVAILABLE",
            net_risk="UNAVAILABLE",
            gross_rr="UNAVAILABLE",
            net_rr="UNAVAILABLE",
            geometry_source="STRUCTURE",
            invalidation_reason=inv_reason,
            target_reason=tgt_reason,
            time_stop=str(time_horizon_sec) if time_horizon_sec else None,
            allowed=False,
            block_reason="BLOCK_INVALID_TRADE_GEOMETRY",
            labels=["NON_POSITIVE_GROSS"],
            inputs_missing=[],
        )

    costs = estimate_costs(
        notional=notional,
        fee_rate=fee_rate,
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
        funding_rate=funding_rate,
    )
    total_cost = costs["total_cost"]
    net_reward = gross_reward - total_cost
    net_risk = gross_risk + total_cost
    gross_rr = gross_reward / gross_risk
    net_rr = net_reward / net_risk if net_risk > 0 else 0.0

    labels: list[str] = []
    allowed = True
    block = "GEOMETRY_PASS"
    if net_reward <= 0:
        allowed = False
        block = "BLOCK_COST_DOMINATED_ENTRY"
        labels.append("net_reward_non_positive")
    elif net_reward < NET_REWARD_TO_COST_MIN * total_cost:
        allowed = False
        block = "BLOCK_COST_DOMINATED_ENTRY"
        labels.append("net_reward_to_cost_low")
    elif net_rr < NET_RR_MIN:
        allowed = False
        block = "BLOCK_COST_DOMINATED_ENTRY"
        labels.append("net_reward_risk_ratio_low")

    # Reject absurdly tight stops relative to min buffer
    stop_dist = abs(entry_price - sl)
    if stop_dist + 1e-12 < min_stop:
        allowed = False
        block = "BLOCK_INVALID_TRADE_GEOMETRY"
        labels.append("stop_inside_noise_buffer")

    return GeometryResult(
        entry_price=entry_price,
        stop_loss=sl,
        take_profit=tp,
        gross_reward=round(gross_reward, 8),
        gross_risk=round(gross_risk, 8),
        total_cost=round(total_cost, 8),
        net_reward=round(net_reward, 8),
        net_risk=round(net_risk, 8),
        gross_rr=round(gross_rr, 8),
        net_rr=round(net_rr, 8),
        geometry_source="STRUCTURE",
        invalidation_reason=inv_reason,
        target_reason=tgt_reason,
        time_stop=str(time_horizon_sec) if time_horizon_sec else None,
        allowed=allowed,
        block_reason=block,
        labels=labels,
        inputs_missing=[],
    )


def evaluate_fixed_symmetric_percent(
    *,
    side: str,
    entry_price: float,
    tp_pct: float,
    sl_pct: float,
    fee_rate: float,
    spread_bps: float,
    slippage_bps: float,
    funding_rate: float | None,
    qty: float,
) -> GeometryResult:
    """Engineering sensitivity only — never a live strategy default."""
    buy = str(side).lower() in {"buy", "long"}
    if buy:
        tp = entry_price * (1.0 + tp_pct)
        sl = entry_price * (1.0 - sl_pct)
        gross_reward = (tp - entry_price) * qty
        gross_risk = (entry_price - sl) * qty
    else:
        tp = entry_price * (1.0 - tp_pct)
        sl = entry_price * (1.0 + sl_pct)
        gross_reward = (entry_price - tp) * qty
        gross_risk = (sl - entry_price) * qty
    notional = abs(entry_price * qty)
    costs = estimate_costs(
        notional=notional,
        fee_rate=fee_rate,
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
        funding_rate=funding_rate,
    )
    total_cost = costs["total_cost"]
    net_reward = gross_reward - total_cost
    net_risk = gross_risk + total_cost
    gross_rr = gross_reward / gross_risk if gross_risk > 0 else 0.0
    net_rr = net_reward / net_risk if net_risk > 0 else 0.0
    incompatible = abs(tp_pct - sl_pct) < 1e-12 and abs(tp_pct - 0.008) < 1e-12
    allowed = net_reward > 0 and net_reward >= NET_REWARD_TO_COST_MIN * total_cost and net_rr >= NET_RR_MIN
    return GeometryResult(
        entry_price=entry_price,
        stop_loss=sl,
        take_profit=tp,
        gross_reward=gross_reward,
        gross_risk=gross_risk,
        total_cost=total_cost,
        net_reward=net_reward,
        net_risk=net_risk,
        gross_rr=gross_rr,
        net_rr=net_rr,
        geometry_source="SENSITIVITY_FIXED_PERCENT",
        invalidation_reason="fixed_percent_sl",
        target_reason="fixed_percent_tp",
        time_stop=None,
        allowed=allowed,
        block_reason="GEOMETRY_PASS" if allowed else "BLOCK_COST_DOMINATED_ENTRY",
        labels=["FIXED_SYMMETRIC_GEOMETRY_INCOMPATIBLE_WITH_NET_RR_GATE"] if incompatible and not allowed else [],
        inputs_missing=[],
    )
