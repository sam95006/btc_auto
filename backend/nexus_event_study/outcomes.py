"""V14-B Event Study Engine — cost-aware multi-horizon outcomes."""
from __future__ import annotations

from typing import Any, Sequence

from backend.nexus_event_study.constants import (
    DEFAULT_FEE_BPS,
    DEFAULT_HORIZONS,
    DEFAULT_SLIP_BPS,
)
from backend.nexus_event_study.types import HorizonOutcome, StudyEvent


def round_trip_cost(*, fee_bps: float = DEFAULT_FEE_BPS, slip_bps: float = DEFAULT_SLIP_BPS) -> float:
    """Round-trip cost as fraction of notional (entry + exit fees/slip)."""
    return 2.0 * (fee_bps + slip_bps) / 10_000.0


def signed_return(entry: float, exit_px: float, side: str) -> float:
    raw = (exit_px - entry) / max(entry, 1e-12)
    if side.upper() in {"SELL", "SHORT"}:
        return -raw
    return raw


def multi_horizon_outcomes(
    event: StudyEvent,
    price_path: Sequence[float],
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    fee_bps: float = DEFAULT_FEE_BPS,
    slip_bps: float = DEFAULT_SLIP_BPS,
) -> list[HorizonOutcome]:
    """Map forward price path to cost-aware outcomes.

    price_path[0] is the decision/entry bar close; path[h] is h bars ahead.
    Missing horizons are marked available=False with reason — never imputed.
    """
    cost = round_trip_cost(fee_bps=fee_bps, slip_bps=slip_bps)
    entry = float(event.entry_price)
    out: list[HorizonOutcome] = []
    for h in horizons:
        h = int(h)
        if h <= 0:
            out.append(
                HorizonOutcome(
                    horizon=h,
                    gross_return=None,
                    net_return=None,
                    cost=None,
                    available=False,
                    missing_reason="invalid_horizon",
                )
            )
            continue
        if h >= len(price_path):
            out.append(
                HorizonOutcome(
                    horizon=h,
                    gross_return=None,
                    net_return=None,
                    cost=None,
                    available=False,
                    missing_reason="insufficient_forward_path",
                )
            )
            continue
        gross = signed_return(entry, float(price_path[h]), event.side)
        net = gross - cost
        out.append(
            HorizonOutcome(
                horizon=h,
                gross_return=gross,
                net_return=net,
                cost=cost,
                available=True,
                missing_reason=None,
            )
        )
    return out


def summarize_horizon_outcomes(
    outcomes_by_event: list[list[HorizonOutcome]],
    *,
    horizon: int,
) -> dict[str, Any]:
    rets = [
        o.net_return
        for bundle in outcomes_by_event
        for o in bundle
        if o.horizon == horizon and o.available and o.net_return is not None
    ]
    gross = [
        o.gross_return
        for bundle in outcomes_by_event
        for o in bundle
        if o.horizon == horizon and o.available and o.gross_return is not None
    ]
    missing = sum(
        1
        for bundle in outcomes_by_event
        for o in bundle
        if o.horizon == horizon and not o.available
    )
    mean_net = sum(rets) / len(rets) if rets else None
    mean_gross = sum(gross) / len(gross) if gross else None
    return {
        "horizon": horizon,
        "n_available": len(rets),
        "n_missing": missing,
        "mean_net_return": mean_net,
        "mean_gross_return": mean_gross,
        "cost_aware": True,
        "profitability_claimed": False,
        "is_trade": False,
    }
