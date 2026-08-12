"""Two-sided LONG/SHORT/WAIT hypothesis evaluation — no directional bias."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_research_ai_autonomy.market_opportunity_selection import (
    MarketCandidate,
    score_market_candidate,
)


@dataclass
class TwoSidedHypothesis:
    symbol: str
    long_score: float = 0.0
    short_score: float = 0.0
    direction_score_delta: float | None = None
    direction_evidence_long: dict[str, Any] | None = None
    direction_evidence_short: dict[str, Any] | None = None
    long_reason: str = ""
    short_reason: str = ""
    selected_side: str = "WAIT"
    side_selection_reason: str | None = None
    direction_ambiguity_supported: bool = False
    long_candidate: MarketCandidate | None = None
    short_candidate: MarketCandidate | None = None
    wait_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.long_candidate:
            d["long_candidate"] = self.long_candidate.to_dict()
        if self.short_candidate:
            d["short_candidate"] = self.short_candidate.to_dict()
        return d


def _candidate_score(c: MarketCandidate) -> float:
    if c.rejection_reason:
        return -1.0
    if not (c.economic_edge_pass and c.horizon_feasibility_pass and c.risk_pass):
        return c.rank_score * 0.5
    return c.rank_score


def evaluate_two_sided_hypothesis(
    *,
    symbol: str,
    entry_price: float,
    equity: float,
    vol_pct_per_hour: float,
    turnover24h: float,
    activity_score: float,
    qty_step: float,
    min_qty: float,
    min_notional: float,
    strategy_family: str = "TREND",
    target_pct: float = 0.55,
    stop_pct: float = 0.40,
    momentum_bias: float = 0.0,
) -> TwoSidedHypothesis:
    """Score LONG and SHORT independently; strongest valid net opportunity wins."""
    long_c = score_market_candidate(
        symbol=symbol,
        entry_price=entry_price,
        equity=equity,
        vol_pct_per_hour=vol_pct_per_hour,
        strategy_family=strategy_family,
        direction="LONG",
        target_pct=target_pct,
        stop_pct=stop_pct,
        turnover24h=turnover24h,
        activity_score=activity_score,
        qty_step=qty_step,
        min_qty=min_qty,
        min_notional=min_notional,
    )
    short_c = score_market_candidate(
        symbol=symbol,
        entry_price=entry_price,
        equity=equity,
        vol_pct_per_hour=vol_pct_per_hour,
        strategy_family=strategy_family,
        direction="SHORT",
        target_pct=target_pct,
        stop_pct=stop_pct,
        turnover24h=turnover24h,
        activity_score=activity_score,
        qty_step=qty_step,
        min_qty=min_qty,
        min_notional=min_notional,
    )

    ls = _candidate_score(long_c) + momentum_bias * 0.01
    ss = _candidate_score(short_c) - momentum_bias * 0.01

    long_ok = long_c.economic_edge_pass and long_c.horizon_feasibility_pass and long_c.risk_pass
    short_ok = short_c.economic_edge_pass and short_c.horizon_feasibility_pass and short_c.risk_pass

    long_reason = "PASS" if long_ok else (long_c.rejection_reason or "gates_fail")
    short_reason = "PASS" if short_ok else (short_c.rejection_reason or "gates_fail")

    selected = "WAIT"
    wait_reason = "no_valid_side"
    side_selection_reason = "no_valid_side"
    direction_ambiguity_supported = False
    if long_ok and short_ok:
        # Deterministic tie handling: do not allow array-order or default LONG bias.
        # Scores are already rounded in float space; we use exact equality of those values.
        ls_r = round(ls, 6)
        ss_r = round(ss, 6)
        if ls_r > ss_r:
            selected = "LONG"
            wait_reason = None
            side_selection_reason = "long_stronger_than_short"
        elif ss_r > ls_r:
            selected = "SHORT"
            wait_reason = None
            side_selection_reason = "short_stronger_than_long"
        else:
            selected = "WAIT"
            wait_reason = "DIRECTION_AMBIGUOUS"
            side_selection_reason = "DIRECTION_AMBIGUOUS"
            direction_ambiguity_supported = True
    elif long_ok:
        selected = "LONG"
        wait_reason = None
        side_selection_reason = "only_long_passed"
    elif short_ok:
        selected = "SHORT"
        wait_reason = None
        side_selection_reason = "only_short_passed"

    delta = round((round(ls, 6) - round(ss, 6)), 6)

    def _evidence(c: MarketCandidate, ok: bool) -> dict[str, Any]:
        return {
            "rank_score": c.rank_score,
            "economic_edge_pass": c.economic_edge_pass,
            "horizon_feasibility_pass": c.horizon_feasibility_pass,
            "risk_pass": c.risk_pass,
            "horizon_config_valid": getattr(c, "horizon_config_valid", None),
            "rejection_reason": c.rejection_reason,
            "gates_pass": ok,
        }

    return TwoSidedHypothesis(
        symbol=symbol,
        long_score=round(ls, 6),
        short_score=round(ss, 6),
        direction_score_delta=delta,
        direction_evidence_long=_evidence(long_c, long_ok),
        direction_evidence_short=_evidence(short_c, short_ok),
        long_reason=long_reason,
        short_reason=short_reason,
        selected_side=selected,
        side_selection_reason=side_selection_reason,
        direction_ambiguity_supported=direction_ambiguity_supported,
        long_candidate=long_c,
        short_candidate=short_c,
        wait_reason=wait_reason,
    )


def select_with_exchange_fallthrough(
    hypotheses: list[TwoSidedHypothesis],
    *,
    preflight_fn,
) -> dict[str, Any]:
    """Try ranked candidates until exchange preflight passes or exhausted."""
    ranked = sorted(
        [h for h in hypotheses if h.selected_side in {"LONG", "SHORT"}],
        key=lambda h: max(h.long_score if h.selected_side == "LONG" else 0, h.short_score if h.selected_side == "SHORT" else 0),
        reverse=True,
    )
    attempts: list[dict[str, Any]] = []
    for rank, h in enumerate(ranked, start=1):
        side = h.selected_side
        cand = h.long_candidate if side == "LONG" else h.short_candidate
        if cand is None:
            continue
        pf = preflight_fn(h.symbol, side, cand)
        attempts.append({"rank": rank, "symbol": h.symbol, "side": side, "preflight": pf})
        if pf.get("exchange_feasibility_pass"):
            return {
                "action": "SELECT",
                "selected_symbol": h.symbol,
                "selected_side": side,
                "hypothesis": h.to_dict(),
                "preflight": pf,
                "candidate_rank": rank,
                "fallthrough_attempts": attempts,
            }
    return {
        "action": "WAIT",
        "block_code": "NO_EXCHANGE_FEASIBLE_CANDIDATE",
        "fallthrough_attempts": attempts,
        "candidates_exhausted": len(attempts),
    }
