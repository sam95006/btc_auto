"""LONG/SHORT symmetry — evaluate each side independently per symbol.

Every symbol: LONG, SHORT, WAIT scored separately.
Persist long_score, short_score, selected_side.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.nexus_research_ai_autonomy.market_opportunity_selection import score_market_candidate


@dataclass
class SideEvaluation:
    side: str  # LONG | SHORT | WAIT
    score: float
    candidate: dict[str, Any]
    action: str  # PASS | WAIT | REJECT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _side_regime(direction: str, change_pct_24h: float) -> str:
    if abs(change_pct_24h) > 3.0:
        return "HIGH_VOLATILITY" if change_pct_24h > 0 else "TREND_DOWN"
    if direction == "LONG":
        return "TREND_UP" if change_pct_24h >= 0 else "UNCERTAIN"
    return "TREND_DOWN" if change_pct_24h < 0 else "UNCERTAIN"


def evaluate_symbol_sides(
    *,
    symbol: str,
    entry_price: float,
    equity: float,
    vol_pct_per_hour: float,
    turnover24h: float,
    change_pct_24h: float = 0.0,
    strategy_family: str = "TREND",
    target_pct: float = 0.55,
    stop_pct: float = 0.40,
    activity_score: float = 0.75,
    qty_step: float = 0.001,
    min_qty: float = 0.001,
    min_notional: float = 5.0,
) -> dict[str, Any]:
    """Evaluate LONG, SHORT, WAIT independently for one symbol."""
    sides: dict[str, SideEvaluation] = {}
    for direction in ("LONG", "SHORT"):
        regime = _side_regime(direction, change_pct_24h)
        cand = score_market_candidate(
            symbol=symbol,
            entry_price=entry_price,
            equity=equity,
            vol_pct_per_hour=vol_pct_per_hour,
            strategy_family=strategy_family,
            direction=direction,
            target_pct=target_pct,
            stop_pct=stop_pct,
            regime=regime,
            turnover24h=turnover24h,
            activity_score=activity_score,
            qty_step=qty_step,
            min_qty=min_qty,
            min_notional=min_notional,
        )
        gates = cand.economic_edge_pass and cand.horizon_feasibility_pass and cand.risk_pass and cand.horizon_config_valid
        action = "PASS" if gates else "WAIT"
        sides[direction] = SideEvaluation(
            side=direction,
            score=float(cand.rank_score or 0.0),
            candidate=cand.to_dict(),
            action=action,
        )

    long_score = sides["LONG"].score
    short_score = sides["SHORT"].score
    long_ok = sides["LONG"].action == "PASS"
    short_ok = sides["SHORT"].action == "PASS"

    selected_side = "WAIT"
    selected_score = 0.0
    if long_ok and short_ok:
        if long_score >= short_score:
            selected_side = "LONG"
            selected_score = long_score
        else:
            selected_side = "SHORT"
            selected_score = short_score
    elif long_ok:
        selected_side = "LONG"
        selected_score = long_score
    elif short_ok:
        selected_side = "SHORT"
        selected_score = short_score

    best_cand = sides[selected_side].candidate if selected_side != "WAIT" else None

    return {
        "schema": "v18_2_28_long_short_symmetry_v1",
        "symbol": symbol,
        "long_score": long_score,
        "short_score": short_score,
        "selected_side": selected_side,
        "selected_score": selected_score,
        "long": sides["LONG"].to_dict(),
        "short": sides["SHORT"].to_dict(),
        "best_candidate": best_cand,
        "symmetry_evaluated": True,
    }


def build_symmetric_candidates(
    tickers: list[dict[str, Any]],
    *,
    equity: float,
    vol_estimator: Any,
    client: Any,
    strategy_family: str = "TREND",
    target_pct: float = 0.55,
    stop_pct: float = 0.40,
) -> list[dict[str, Any]]:
    """Build ranked candidate list with long/short symmetry metadata."""
    out: list[dict[str, Any]] = []
    for t in tickers:
        sym = str(t.get("symbol") or "")
        price = float(t.get("last_price") or 0)
        if not sym or price <= 0:
            continue
        try:
            info = client.fetch_instrument(sym)
            step = client.qty_step(info)
            min_q = client.min_qty(info)
            min_n = client.min_notional(info)
        except Exception:  # noqa: BLE001
            step, min_q, min_n = 0.001, 0.001, 5.0

        vol_h = vol_estimator(client, sym) if callable(vol_estimator) else 0.35
        ev = evaluate_symbol_sides(
            symbol=sym,
            entry_price=price,
            equity=equity,
            vol_pct_per_hour=vol_h,
            turnover24h=float(t.get("turnover_24h") or 0),
            change_pct_24h=float(t.get("change_pct_24h") or 0),
            strategy_family=strategy_family,
            target_pct=target_pct,
            stop_pct=stop_pct,
            qty_step=step,
            min_qty=min_q,
            min_notional=min_n,
        )
        if ev["selected_side"] == "WAIT":
            # Still include for funnel counts using best-scoring side candidate
            best = ev["long"]["candidate"] if ev["long_score"] >= ev["short_score"] else ev["short"]["candidate"]
            cand = dict(best)
            cand["long_score"] = ev["long_score"]
            cand["short_score"] = ev["short_score"]
            cand["selected_side"] = "WAIT"
            out.append(cand)
        else:
            cand = dict(ev["best_candidate"] or {})
            cand["long_score"] = ev["long_score"]
            cand["short_score"] = ev["short_score"]
            cand["selected_side"] = ev["selected_side"]
            cand["direction"] = ev["selected_side"]
            cand["rank_score"] = ev["selected_score"]
            out.append(cand)
    return out
