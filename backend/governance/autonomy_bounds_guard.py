"""Clamp AI / learning outputs to hard safety bounds."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from config.autonomy_bounds_config import (
    ABSOLUTE_MAX_MARGIN_PCT,
    DEFAULT_SAFE_LEVERAGE,
    DEFAULT_SAFE_POSITION_SIZE_MULT,
    DEFAULT_SAFE_STOP_LOSS_PCT,
    HARD_MAX_LEVERAGE,
    HARD_MAX_MARGIN_USD,
    HARD_MAX_OPEN_POSITIONS,
    HARD_MAX_POSITION_SIZE_MULT,
    HARD_MAX_SIGNAL_WEIGHT_ADJ,
    HARD_MAX_STOP_LOSS_PCT,
    HARD_MIN_LEVERAGE,
    HARD_MIN_MARGIN_USD,
    HARD_MIN_POSITION_SIZE_MULT,
)

logger = logging.getLogger(__name__)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float, field: str, warnings: List[str]) -> float:
    if value < low:
        warnings.append(f"{field}_below_hard_min:{value}->{low}")
        return low
    if value > high:
        warnings.append(f"{field}_above_hard_max:{value}->{high}")
        return high
    return value


def clamp_trade_proposal(proposal: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    proposal = dict(proposal or {})
    warnings: List[str] = []

    if proposal.get("leverage") is not None:
        lev = _safe_float(proposal.get("leverage"), DEFAULT_SAFE_LEVERAGE)
        if lev > HARD_MAX_LEVERAGE or lev < HARD_MIN_LEVERAGE:
            warnings.append(f"leverage_out_of_bounds:{lev}")
            lev = DEFAULT_SAFE_LEVERAGE
        proposal["leverage"] = round(
            _clamp(lev, HARD_MIN_LEVERAGE, HARD_MAX_LEVERAGE, "leverage", warnings),
            4,
        )

    if proposal.get("margin") is not None:
        margin = _safe_float(proposal.get("margin"), HARD_MIN_MARGIN_USD)
        proposal["margin"] = round(
            _clamp(margin, HARD_MIN_MARGIN_USD, HARD_MAX_MARGIN_USD, "margin", warnings),
            4,
        )

    stop = proposal.get("stop_loss_pct")
    if stop is not None:
        stop_f = _safe_float(stop, DEFAULT_SAFE_STOP_LOSS_PCT)
        if stop_f > HARD_MAX_STOP_LOSS_PCT:
            warnings.append(f"stop_loss_pct_out_of_bounds:{stop_f}")
            stop_f = DEFAULT_SAFE_STOP_LOSS_PCT
        proposal["stop_loss_pct"] = round(_clamp(stop_f, 0.001, HARD_MAX_STOP_LOSS_PCT, "stop_loss_pct", warnings), 6)

    if warnings:
        proposal["autonomy_bounds_clamped"] = True
        proposal["autonomy_bounds_warnings"] = list(warnings)
        for msg in warnings:
            logger.warning("autonomy_bounds trade_proposal: %s", msg)
    return proposal, warnings


def clamp_learning_patch(patch: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    patch = dict(patch or {})
    warnings: List[str] = []

    if patch.get("leverage_cap") is not None:
        cap = _safe_float(patch.get("leverage_cap"), DEFAULT_SAFE_LEVERAGE)
        if cap > HARD_MAX_LEVERAGE or cap < HARD_MIN_LEVERAGE:
            warnings.append(f"leverage_cap_out_of_bounds:{cap}")
            cap = DEFAULT_SAFE_LEVERAGE
        patch["leverage_cap"] = round(_clamp(cap, HARD_MIN_LEVERAGE, HARD_MAX_LEVERAGE, "leverage_cap", warnings), 4)

    if patch.get("position_size_multiplier") is not None:
        mult = _safe_float(patch.get("position_size_multiplier"), DEFAULT_SAFE_POSITION_SIZE_MULT)
        patch["position_size_multiplier"] = round(
            _clamp(
                mult,
                HARD_MIN_POSITION_SIZE_MULT,
                HARD_MAX_POSITION_SIZE_MULT,
                "position_size_multiplier",
                warnings,
            ),
            4,
        )

    if patch.get("signal_weight_adjustment") is not None:
        adj = _safe_float(patch.get("signal_weight_adjustment"), 0.0)
        patch["signal_weight_adjustment"] = round(
            _clamp(adj, -HARD_MAX_SIGNAL_WEIGHT_ADJ, HARD_MAX_SIGNAL_WEIGHT_ADJ, "signal_weight_adjustment", warnings),
            4,
        )

    if patch.get("max_open_positions") is not None:
        n = int(_safe_float(patch.get("max_open_positions"), HARD_MAX_OPEN_POSITIONS))
        if n > HARD_MAX_OPEN_POSITIONS:
            warnings.append(f"max_open_positions_out_of_bounds:{n}")
            n = HARD_MAX_OPEN_POSITIONS
        patch["max_open_positions"] = max(1, n)

    if warnings:
        patch["autonomy_bounds_clamped"] = True
        patch["autonomy_bounds_warnings"] = list(warnings)
        for msg in warnings:
            logger.warning("autonomy_bounds learning_patch: %s", msg)
    return patch, warnings


def validate_proposal_bounds(
    proposal: Dict[str, Any],
    *,
    available_balance: float = 0.0,
) -> Tuple[Dict[str, Any], List[str]]:
    """Enforce wallet % cap and absolute leverage ceiling."""
    proposal = dict(proposal or {})
    warnings: List[str] = []
    balance = _safe_float(available_balance)
    if balance > 0 and proposal.get("margin") is not None:
        cap = balance * ABSOLUTE_MAX_MARGIN_PCT
        margin = _safe_float(proposal.get("margin"))
        if margin > cap:
            warnings.append(f"margin_above_wallet_pct:{margin}->{cap}")
            proposal["margin"] = round(cap, 4)
    if proposal.get("leverage") is not None:
        lev = _safe_float(proposal.get("leverage"))
        if lev > HARD_MAX_LEVERAGE:
            warnings.append(f"leverage_capped:{lev}->{HARD_MAX_LEVERAGE}")
            proposal["leverage"] = HARD_MAX_LEVERAGE
    if warnings:
        proposal["bounds_validated"] = True
        proposal["bounds_warnings"] = warnings
    return proposal, warnings
