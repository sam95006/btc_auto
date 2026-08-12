"""Economic entry filter — expected net TP ≥ 1.0 USDT preferred; WAIT if unsafe.

Entry FILTER only — not a guaranteed profit. Do NOT raise risk beyond bounds
to force +1U. Exit remains Risk/stop/regime/trail/time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PREFERRED_EXPECTED_NET_TP_USDT = 1.0
MIN_EDGE_TO_ROUNDTRIP_COST_RATIO = 1.5  # avoid barely-above-cost setups


@dataclass
class EconomicEntryFilterResult:
    action: str  # PASS | WAIT
    expected_target_move_pct: float
    roundtrip_fee_pct: float
    slippage_pct: float
    expected_gross_profit_usdt: float
    expected_fee_usdt: float
    expected_slip_usdt: float
    expected_net_profit_usdt: float
    edge_to_roundtrip_cost_ratio: float | None
    preferred_net_tp_usdt: float = PREFERRED_EXPECTED_NET_TP_USDT
    reasons: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    maker_taker: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_economic_entry(
    *,
    notional_usdt: float,
    target_distance_pct: float,
    fee_rate_one_way: float | None = None,
    roundtrip_fee_pct: float | None = None,
    slippage_pct: float = 0.02,
    maker_fee_rate: float = 0.0002,
    taker_fee_rate: float = 0.00055,
    assumed_fee_side: str = "TAKER",
    preferred_net_tp_usdt: float = PREFERRED_EXPECTED_NET_TP_USDT,
    min_edge_to_cost_ratio: float = MIN_EDGE_TO_ROUNDTRIP_COST_RATIO,
) -> EconomicEntryFilterResult:
    """Compute expected gross/fee/slip/net before PreparedDecision commit."""
    blocks: list[str] = []
    reasons: list[str] = []
    notional = float(notional_usdt or 0.0)
    tgt_pct = abs(float(target_distance_pct or 0.0))
    slip_pct = abs(float(slippage_pct or 0.0))

    side = str(assumed_fee_side or "TAKER").upper()
    one_way = float(fee_rate_one_way) if fee_rate_one_way is not None else (
        float(taker_fee_rate) if side == "TAKER" else float(maker_fee_rate)
    )
    rt_fee_pct = (
        float(roundtrip_fee_pct)
        if roundtrip_fee_pct is not None
        else one_way * 2.0 * 100.0  # percent units to match target_distance_pct
    )
    # Normalize: target_distance_pct is in percent (e.g. 0.50 = 0.50%)
    # rt_fee_pct also in percent; one_way rate is fraction.

    if notional <= 0:
        blocks.append("notional_non_positive")
    if tgt_pct <= 0:
        blocks.append("target_distance_missing")

    expected_gross = notional * (tgt_pct / 100.0)
    expected_fee = notional * (rt_fee_pct / 100.0)
    expected_slip = notional * (slip_pct / 100.0)
    expected_net = expected_gross - expected_fee - expected_slip
    cost = expected_fee + expected_slip
    ratio = (expected_gross / cost) if cost > 1e-12 else None

    maker_taker = {
        "assumed_side": side,
        "maker_fee_rate": maker_fee_rate,
        "taker_fee_rate": taker_fee_rate,
        "one_way_fee_rate": one_way,
        "actual_fees_recorded_at_fill": False,  # filled later from exchange
    }

    if expected_net + 1e-12 < preferred_net_tp_usdt:
        blocks.append("expected_net_below_preferred_1u")
        reasons.append(f"expected_net={expected_net:.6f}<{preferred_net_tp_usdt}")
    else:
        reasons.append(f"expected_net_ok={expected_net:.6f}")

    if ratio is not None and ratio < min_edge_to_cost_ratio:
        blocks.append("edge_to_roundtrip_cost_ratio_thin")
        reasons.append(f"edge_cost_ratio={ratio:.4f}<{min_edge_to_cost_ratio}")
    elif ratio is not None:
        reasons.append(f"edge_cost_ratio_ok={ratio:.4f}")

    # WAIT if unsafe — do NOT raise risk/size/leverage to force 1U
    action = "WAIT" if blocks else "PASS"
    if action == "WAIT":
        reasons.append("WAIT_do_not_raise_risk_to_force_1u")

    return EconomicEntryFilterResult(
        action=action,
        expected_target_move_pct=tgt_pct,
        roundtrip_fee_pct=rt_fee_pct,
        slippage_pct=slip_pct,
        expected_gross_profit_usdt=expected_gross,
        expected_fee_usdt=expected_fee,
        expected_slip_usdt=expected_slip,
        expected_net_profit_usdt=expected_net,
        edge_to_roundtrip_cost_ratio=ratio,
        preferred_net_tp_usdt=preferred_net_tp_usdt,
        reasons=reasons,
        blocks=blocks,
        maker_taker=maker_taker,
    )


def annotate_actual_fees(
    filter_result: dict[str, Any],
    *,
    open_fee: Any,
    close_fee: Any,
    fee_currency: str = "USDT",
    is_maker_open: bool | None = None,
    is_maker_close: bool | None = None,
) -> dict[str, Any]:
    """Attach MAKER/TAKER actual fees after fill — does not mutate entry decision."""
    out = dict(filter_result)
    mt = dict(out.get("maker_taker") or {})
    try:
        of = abs(float(open_fee or 0.0))
        cf = abs(float(close_fee or 0.0))
    except (TypeError, ValueError):
        of, cf = 0.0, 0.0
    mt.update(
        {
            "actual_fees_recorded_at_fill": True,
            "open_fee": of,
            "close_fee": cf,
            "fee_total": of + cf,
            "fee_currency": fee_currency,
            "open_maker": is_maker_open,
            "close_maker": is_maker_close,
            "open_fee_class": (
                "MAKER" if is_maker_open is True else ("TAKER" if is_maker_open is False else "UNKNOWN")
            ),
            "close_fee_class": (
                "MAKER" if is_maker_close is True else ("TAKER" if is_maker_close is False else "UNKNOWN")
            ),
        }
    )
    out["maker_taker"] = mt
    out["actual_fee_usdt"] = of + cf
    return out
