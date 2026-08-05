"""Consume canonical cost authority — never redefine fee/spread/slip formulas.

Market-impact, latency, and queue-position effects are explicit *scenario
modifiers* that map into canonical inputs (or an explicitly labeled research
approximation outside CostBridge). They do not invent parallel CostBridge math.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.nexus_execution.cost_model import (
    CANONICAL_COST_AUTHORITY,
    CANONICAL_COST_AUTHORITY_COUNT,
    COST_MODEL_SCHEMA,
    COST_MODEL_VERSION,
    DEFAULT_MAKER_FEE,
    DEFAULT_SLIPPAGE_BPS,
    DEFAULT_SPREAD_BPS,
    DEFAULT_TAKER_FEE,
    cancel_replace_component,
    compose_cost_bridge,
    funding_unavailable_buffer,
    get_cost_model_contract,
    leg_costs_for_notional,
    partial_fill_component,
)
from backend.nexus_cost_sensitivity.constants import (
    DEFAULT_BASE_IMPACT_BPS,
    REQUIRED_COST_COMPONENTS,
)


def _d(x: float | int | str | Decimal) -> Decimal:
    return Decimal(str(x))


def assert_canonical_authority() -> dict[str, Any]:
    """Prove we are bound to the sole Session cost authority."""
    contract = get_cost_model_contract()
    contract.validate()
    if contract.authority != CANONICAL_COST_AUTHORITY:
        raise AssertionError(f"authority_mismatch={contract.authority}")
    if CANONICAL_COST_AUTHORITY_COUNT != 1:
        raise AssertionError("canonical_cost_authority_count_must_be_1")
    return {
        "cost_model_version": COST_MODEL_VERSION,
        "cost_model_schema": COST_MODEL_SCHEMA,
        "canonical_cost_authority": CANONICAL_COST_AUTHORITY,
        "canonical_cost_authority_count": CANONICAL_COST_AUTHORITY_COUNT,
        "contract": contract.to_dict(),
    }


def market_impact_approximation(*, notional: Decimal, impact_bps: Decimal) -> Decimal:
    """Conservative visible-depth impact proxy (research approximation).

    Explicitly *outside* CostBridge identity — same pattern as V13-C discovery.
    """
    if impact_bps <= 0 or notional <= 0:
        return Decimal(0)
    return abs(notional) * impact_bps / Decimal("10000")


def resolve_leg_taker_flags(*, maker_taker_mix: float) -> tuple[bool, bool]:
    """Map mix in [0, 1] onto (entry_is_taker, exit_is_taker).

    0.0 → both maker, 0.5 → entry maker / exit taker, 1.0 → both taker.
    """
    m = max(0.0, min(1.0, float(maker_taker_mix)))
    if m <= 0.25:
        return (False, False)
    if m <= 0.5:
        return (False, True)
    if m <= 0.75:
        return (True, False)
    return (True, True)


def latency_to_extra_slippage_bps(latency_ms: float) -> Decimal:
    """Scenario modifier: adverse latency → extra slippage fed into canonical path."""
    # 0ms → 0bps; 100ms → +1bps; 500ms → +5bps (linear, capped).
    extra = min(20.0, max(0.0, float(latency_ms)) / 100.0)
    return _d(extra)


def queue_position_to_taker_bias(queue_position: float) -> float:
    """Scenario modifier: back-of-queue (1.0) biases maker→taker conversion."""
    return max(0.0, min(1.0, float(queue_position)))


def account_round_trip(
    *,
    side: str,
    qty: Decimal,
    entry_price: Decimal,
    exit_price: Decimal,
    maker_taker_mix: float = 1.0,
    spread_bps: Decimal | float | None = None,
    slippage_bps: Decimal | float | None = None,
    impact_bps: Decimal | float | None = None,
    funding_rate: Decimal | float | None = None,
    extra_fills: int = 0,
    cancel_replace_cycles: int = 0,
    latency_ms: float = 0.0,
    queue_position: float = 0.0,
    liquidity_collapse: float = 1.0,
    size_scale: float = 1.0,
) -> dict[str, Any]:
    """Full cost decomposition via canonical CostBridge + labeled impact approx.

    Latency / queue / liquidity / size are *modifiers* of canonical inputs —
    they do not replace CostBridge formulas.
    """
    scale = _d(max(0.0, float(size_scale)))
    scaled_qty = qty * scale
    notional = abs(scaled_qty * entry_price)

    collapse = _d(max(0.0, float(liquidity_collapse)))
    base_spread = _d(spread_bps) if spread_bps is not None else DEFAULT_SPREAD_BPS
    base_slip = _d(slippage_bps) if slippage_bps is not None else DEFAULT_SLIPPAGE_BPS
    base_impact = (
        _d(impact_bps) if impact_bps is not None else _d(DEFAULT_BASE_IMPACT_BPS)
    )

    # Queue back → raise effective maker/taker mix toward taker.
    q_bias = queue_position_to_taker_bias(queue_position)
    effective_mix = min(1.0, float(maker_taker_mix) + 0.5 * q_bias)
    entry_taker, exit_taker = resolve_leg_taker_flags(maker_taker_mix=effective_mix)

    # Latency adds adverse slippage into the *canonical* slippage_bps input.
    effective_slip = (base_slip + latency_to_extra_slippage_bps(latency_ms)) * collapse
    effective_spread = base_spread * collapse
    # Size scaling increases impact nonlinearly (sqrt proxy, labeled research).
    size_impact_mult = _d(1) if scale <= 0 else scale.sqrt()
    effective_impact = base_impact * collapse * size_impact_mult

    entry = leg_costs_for_notional(
        notional=notional,
        is_taker=entry_taker,
        fee_rate=DEFAULT_TAKER_FEE if entry_taker else DEFAULT_MAKER_FEE,
        spread_bps=effective_spread,
        slippage_bps=effective_slip,
    )
    exit_ = leg_costs_for_notional(
        notional=notional,
        is_taker=exit_taker,
        fee_rate=DEFAULT_TAKER_FEE if exit_taker else DEFAULT_MAKER_FEE,
        spread_bps=effective_spread,
        slippage_bps=effective_slip,
    )

    if funding_rate is None:
        funding = funding_unavailable_buffer(notional=notional)
    else:
        funding = abs(notional * _d(funding_rate))

    partial = partial_fill_component(extra_fills=int(extra_fills))
    cancel = cancel_replace_component(cycles=int(cancel_replace_cycles))
    impact = market_impact_approximation(notional=notional, impact_bps=effective_impact)

    bridge = compose_cost_bridge(
        side=side,
        qty=scaled_qty,
        entry_price=entry_price,
        exit_price=exit_price,
        entry_fee=entry["fee"],
        exit_fee=exit_["fee"],
        entry_spread=entry["spread_cost"],
        exit_spread=exit_["spread_cost"],
        entry_slippage=entry["slippage_cost"],
        exit_slippage=exit_["slippage_cost"],
        funding=funding,
        partial_fill=partial,
        cancel_replace=cancel,
    )
    net_after_full = bridge.net_pnl - impact
    components = {
        "entry_fee": bridge.entry_fee,
        "exit_fee": bridge.exit_fee,
        "spread_cost": bridge.spread_cost,
        "slippage_cost": bridge.slippage_cost,
        "funding_cost": bridge.funding_cost,
        "partial_fill_cost": bridge.partial_fill_cost,
        "cancel_replace_cost": bridge.cancel_replace_cost,
        "market_impact_approximation": impact,
    }
    missing = [k for k in REQUIRED_COST_COMPONENTS if k not in components]
    if missing:
        raise AssertionError(f"missing_cost_components={missing}")

    total_cost = sum(components.values(), Decimal(0))
    return {
        "cost_model_version": COST_MODEL_VERSION,
        "cost_authority": CANONICAL_COST_AUTHORITY,
        "cost_bridge_verified": True,
        "market_impact_outside_cost_bridge": True,
        "gross_pnl": bridge.gross_pnl,
        "cost_bridge_net_pnl": bridge.net_pnl,
        "net_pnl": net_after_full,
        "total_cost": total_cost,
        "cost_components": {k: format(v, "f") for k, v in components.items()},
        "cost_components_decimal": components,
        "notional": format(notional, "f"),
        "scenario_modifiers": {
            "maker_taker_mix": float(maker_taker_mix),
            "effective_maker_taker_mix": effective_mix,
            "entry_is_taker": entry_taker,
            "exit_is_taker": exit_taker,
            "spread_bps": format(effective_spread, "f"),
            "slippage_bps": format(effective_slip, "f"),
            "impact_bps": format(effective_impact, "f"),
            "latency_ms": float(latency_ms),
            "queue_position": float(queue_position),
            "liquidity_collapse": float(collapse),
            "size_scale": float(scale),
            "extra_fills": int(extra_fills),
            "cancel_replace_cycles": int(cancel_replace_cycles),
        },
    }
