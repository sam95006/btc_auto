"""Risk-based position sizing for RESEARCH_PNL_TRADE — no fixed 0.001 BTC.

Envelope: preferred notional 250–500 USDT on ~5k Demo equity at 1x.
Max expected loss/trade ≤ 0.10% equity (~≤5 USDT) including costs where possible.
Leverage remains 1x — never raise leverage to force larger PnL.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_demo_execution.demo_write_client import _round_qty

PREFERRED_NOTIONAL_MIN = 250.0
PREFERRED_NOTIONAL_MAX = 500.0
MAX_LOSS_EQUITY_PCT = 0.10  # 0.10% equity
DEFAULT_EQUITY = 5000.0
LEVERAGE = 1


@dataclass
class RiskSizeResult:
    action: str  # SIZE | WAIT
    qty: float
    qty_str: str
    notional_usdt: float
    expected_loss_usdt: float
    max_loss_usdt: float
    equity: float
    entry_price: float
    stop_distance_pct: float
    target_distance_pct: float
    leverage: int = LEVERAGE
    preferred_notional_band: tuple[float, float] = (PREFERRED_NOTIONAL_MIN, PREFERRED_NOTIONAL_MAX)
    reasons: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["preferred_notional_band"] = list(self.preferred_notional_band)
        return d


def compute_risk_based_size(
    *,
    equity: float,
    entry_price: float,
    stop_distance_pct: float,
    target_distance_pct: float,
    fee_rate_roundtrip: float,
    slippage_pct: float,
    liquidity: float,
    confidence: float,
    qty_step: float,
    min_qty: float,
    min_notional: float,
    preferred_notional: float | None = None,
    max_loss_equity_pct: float = MAX_LOSS_EQUITY_PCT,
    leverage: int = LEVERAGE,
) -> RiskSizeResult:
    """Deterministic risk size. Reduce size or WAIT if max-loss envelope violated."""
    blocks: list[str] = []
    reasons: list[str] = []
    eq = float(equity or 0.0)
    px = float(entry_price or 0.0)
    stop_pct = abs(float(stop_distance_pct or 0.0))
    tgt_pct = abs(float(target_distance_pct or 0.0))
    fee_rt = abs(float(fee_rate_roundtrip or 0.0))
    slip = abs(float(slippage_pct or 0.0))
    liq = float(liquidity if liquidity is not None else 0.0)
    conf = float(confidence if confidence is not None else 0.0)
    step = float(qty_step or 0.0)
    min_q = float(min_qty or 0.0)
    min_n = float(min_notional or 0.0)

    inputs = {
        "equity": eq,
        "entry_price": px,
        "stop_distance_pct": stop_pct,
        "target_distance_pct": tgt_pct,
        "fee_rate_roundtrip": fee_rt,
        "slippage_pct": slip,
        "liquidity": liq,
        "confidence": conf,
        "qty_step": step,
        "min_qty": min_q,
        "min_notional": min_n,
        "max_loss_equity_pct": max_loss_equity_pct,
        "leverage": leverage,
    }

    if leverage != 1:
        blocks.append("leverage_not_1x")
    else:
        reasons.append("leverage_1x")

    if eq <= 0 or px <= 0 or step <= 0:
        blocks.append("invalid_price_equity_or_step")
        return RiskSizeResult(
            action="WAIT",
            qty=0.0,
            qty_str="0",
            notional_usdt=0.0,
            expected_loss_usdt=0.0,
            max_loss_usdt=0.0,
            equity=eq,
            entry_price=px,
            stop_distance_pct=stop_pct,
            target_distance_pct=tgt_pct,
            leverage=1,
            reasons=reasons,
            blocks=blocks,
            inputs=inputs,
        )

    if stop_pct <= 0:
        blocks.append("stop_distance_missing")
    if liq < 0.2:
        blocks.append("liquidity_too_low")
    if conf < 0.35:
        blocks.append("confidence_too_low")

    max_loss = eq * (max_loss_equity_pct / 100.0)
    reasons.append(f"max_loss_usdt={max_loss:.6f}")

    # Preferred notional mid of band, scaled by confidence (still inside band).
    band_lo, band_hi = PREFERRED_NOTIONAL_MIN, PREFERRED_NOTIONAL_MAX
    if preferred_notional is not None:
        target_notional = float(preferred_notional)
    else:
        # Map confidence 0.35–1.0 → band_lo–band_hi
        c = max(0.0, min(1.0, conf))
        target_notional = band_lo + (band_hi - band_lo) * c
    target_notional = max(band_lo, min(band_hi, target_notional))

    # Risk cap: loss ≈ notional * (stop_pct + fee_rt + slip)
    loss_frac = stop_pct / 100.0 + fee_rt + slip / 100.0
    if loss_frac <= 0:
        blocks.append("non_positive_loss_fraction")
        loss_frac = stop_pct / 100.0 if stop_pct > 0 else 0.01

    risk_capped_notional = max_loss / loss_frac if loss_frac > 0 else 0.0
    notional = min(target_notional, risk_capped_notional)

    # If risk-capped notional falls below preferred band, still allow if ≥ min exchange
    # notional AND expected loss ≤ max_loss; else WAIT (do not raise leverage).
    if notional + 1e-9 < band_lo:
        if risk_capped_notional >= max(min_n, 5.0) and risk_capped_notional <= max_loss / max(loss_frac, 1e-12):
            notional = risk_capped_notional
            reasons.append("below_preferred_band_risk_capped")
        else:
            blocks.append("risk_requires_wait_below_safe_notional")
            return RiskSizeResult(
                action="WAIT",
                qty=0.0,
                qty_str="0",
                notional_usdt=0.0,
                expected_loss_usdt=max_loss,
                max_loss_usdt=max_loss,
                equity=eq,
                entry_price=px,
                stop_distance_pct=stop_pct,
                target_distance_pct=tgt_pct,
                leverage=1,
                reasons=reasons + ["WAIT_risk_envelope"],
                blocks=blocks,
                inputs=inputs,
            )

    raw_qty = notional / px
    qty_str = _round_qty(raw_qty, step)
    qty = float(qty_str)
    if qty <= 0 and min_q > 0:
        # Do not fall back to fixed 0.001 for PnL research — WAIT
        blocks.append("qty_rounded_to_zero")
        return RiskSizeResult(
            action="WAIT",
            qty=0.0,
            qty_str="0",
            notional_usdt=0.0,
            expected_loss_usdt=0.0,
            max_loss_usdt=max_loss,
            equity=eq,
            entry_price=px,
            stop_distance_pct=stop_pct,
            target_distance_pct=tgt_pct,
            leverage=1,
            reasons=reasons,
            blocks=blocks,
            inputs=inputs,
        )

    if min_q > 0 and qty + 1e-15 < min_q:
        # Stepping up to min_qty only if risk still OK
        steps = math.ceil(min_q / step) if step > 0 else 1
        qty = steps * step
        qty_str = _round_qty(qty, step)
        qty = float(qty_str)
        reasons.append("bumped_to_min_qty")

    notional = qty * px
    if min_n > 0 and notional + 1e-12 < min_n:
        need = math.ceil((min_n / px) / step) * step if step > 0 else min_q
        qty = float(_round_qty(need, step))
        qty_str = _round_qty(qty, step)
        notional = qty * px
        reasons.append("bumped_to_min_notional")

    expected_loss = notional * loss_frac
    if expected_loss > max_loss + 1e-9:
        # Reduce size to fit risk envelope
        fit_notional = max_loss / loss_frac
        fit_qty = float(_round_qty(fit_notional / px, step))
        if fit_qty <= 0 or fit_qty * px * loss_frac > max_loss + 1e-6:
            blocks.append("cannot_fit_max_loss_envelope")
            return RiskSizeResult(
                action="WAIT",
                qty=0.0,
                qty_str="0",
                notional_usdt=0.0,
                expected_loss_usdt=expected_loss,
                max_loss_usdt=max_loss,
                equity=eq,
                entry_price=px,
                stop_distance_pct=stop_pct,
                target_distance_pct=tgt_pct,
                leverage=1,
                reasons=reasons + ["WAIT_size_reduction_failed"],
                blocks=blocks,
                inputs=inputs,
            )
        qty = fit_qty
        qty_str = _round_qty(qty, step)
        notional = qty * px
        expected_loss = notional * loss_frac
        reasons.append("size_reduced_to_max_loss")

    if blocks:
        return RiskSizeResult(
            action="WAIT",
            qty=0.0,
            qty_str="0",
            notional_usdt=0.0,
            expected_loss_usdt=expected_loss,
            max_loss_usdt=max_loss,
            equity=eq,
            entry_price=px,
            stop_distance_pct=stop_pct,
            target_distance_pct=tgt_pct,
            leverage=1,
            reasons=reasons,
            blocks=blocks,
            inputs=inputs,
        )

    reasons.append(f"notional={notional:.4f}")
    reasons.append(f"expected_loss={expected_loss:.6f}")
    return RiskSizeResult(
        action="SIZE",
        qty=qty,
        qty_str=qty_str,
        notional_usdt=notional,
        expected_loss_usdt=expected_loss,
        max_loss_usdt=max_loss,
        equity=eq,
        entry_price=px,
        stop_distance_pct=stop_pct,
        target_distance_pct=tgt_pct,
        leverage=1,
        reasons=reasons,
        blocks=blocks,
        inputs=inputs,
    )
