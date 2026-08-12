"""Full-market PnL opportunity selection — no implicit BTCUSDT default.

Rank eligible liquid symbols by post-cost edge, horizon feasibility, and risk.
If none pass all gates: NO_ECONOMICALLY_FEASIBLE_MARKET_OPPORTUNITY → WAIT.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_research_ai_autonomy.economic_entry_filter import evaluate_economic_entry
from backend.nexus_research_ai_autonomy.horizon_feasibility import (
    INVALID_HORIZON_CONFIGURATION,
    build_horizon_plan,
    evaluate_horizon_feasibility,
    validate_horizon_configuration,
)
from backend.nexus_research_ai_autonomy.risk_based_sizing import compute_risk_based_size


@dataclass
class MarketCandidate:
    symbol: str
    strategy_family: str
    direction: str
    entry_price: float
    forecast_horizon_sec: int | None = None
    expected_move_pct: float | None = None
    target_move_pct: float | None = None
    expected_time_to_target: float | None = None
    estimated_roundtrip_cost_usdt: float | None = None
    expected_net_target_usdt: float | None = None
    edge_cost_ratio: float | None = None
    liquidity: float = 0.0
    activity_score: float = 0.0
    regime: str = "UNCERTAIN"
    economic_edge_pass: bool = False
    horizon_feasibility_pass: bool = False
    horizon_config_valid: bool = True
    risk_pass: bool = False
    rank_score: float = 0.0
    rejection_reason: str | None = None
    horizon_plan: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketOpportunityFunnel:
    eligible_universe: int = 0
    economic_edge_pass: int = 0
    horizon_feasibility_pass: int = 0
    both_pass: int = 0
    risk_pass: int = 0
    prepared: int = 0
    triggered: int = 0
    real_orders: int = 0
    top_rejection_reasons: list[dict[str, Any]] = field(default_factory=list)
    best_candidate: MarketCandidate | None = None
    action: str = "WAIT"
    block_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.best_candidate is not None:
            d["best_candidate"] = self.best_candidate.to_dict()
        return d


def _liquidity_score(*, turnover24h: float | None, spread_bps: float | None) -> float:
    t = float(turnover24h or 0.0)
    liq = min(1.0, t / 50_000_000.0) if t > 0 else 0.2
    if spread_bps is not None and spread_bps > 0:
        liq *= max(0.1, 1.0 - min(0.9, spread_bps / 50.0))
    return max(0.05, min(1.0, liq))


def score_market_candidate(
    *,
    symbol: str,
    entry_price: float,
    equity: float,
    vol_pct_per_hour: float,
    strategy_family: str = "TREND",
    direction: str = "LONG",
    target_pct: float = 0.55,
    stop_pct: float = 0.40,
    regime: str = "UNCERTAIN",
    turnover24h: float | None = None,
    spread_bps: float | None = None,
    activity_score: float = 0.7,
    qty_step: float = 0.001,
    min_qty: float = 0.001,
    min_notional: float = 5.0,
    preferred_notional: float = 350.0,
    hard_max_hold_override: int | None = None,
) -> MarketCandidate:
    liq = _liquidity_score(turnover24h=turnover24h, spread_bps=spread_bps)
    if liq < 0.25:
        return MarketCandidate(
            symbol=symbol,
            strategy_family=strategy_family,
            direction=direction,
            entry_price=entry_price,
            liquidity=liq,
            activity_score=activity_score,
            regime=regime,
            rejection_reason="liquidity_too_thin",
        )

    plan = build_horizon_plan(
        strategy_family=strategy_family,
        side=direction,
        entry_price=entry_price,
        expected_target_move_pct=target_pct,
        stop_move_pct=stop_pct,
        realized_vol_pct_per_hour=vol_pct_per_hour,
        regime=regime,
        activity_score=activity_score,
        liquidity=liq,
        hard_max_hold_override=hard_max_hold_override,
    )
    cfg_ok, _, cfg_block = validate_horizon_configuration(plan)
    if not cfg_ok:
        return MarketCandidate(
            symbol=symbol,
            strategy_family=strategy_family,
            direction=direction,
            entry_price=entry_price,
            forecast_horizon_sec=plan.forecast_horizon_sec,
            expected_move_pct=plan.expected_path_range_pct,
            target_move_pct=target_pct,
            expected_time_to_target=plan.expected_time_to_target,
            liquidity=liq,
            activity_score=activity_score,
            regime=regime,
            horizon_config_valid=False,
            rejection_reason=cfg_block or INVALID_HORIZON_CONFIGURATION,
            horizon_plan=plan.to_dict(),
        )

    sizing = compute_risk_based_size(
        equity=equity,
        entry_price=entry_price,
        stop_distance_pct=stop_pct,
        target_distance_pct=target_pct,
        fee_rate_roundtrip=0.0011,
        slippage_pct=0.02,
        liquidity=liq,
        confidence=0.75,
        qty_step=qty_step,
        min_qty=min_qty,
        min_notional=min_notional,
        preferred_notional=preferred_notional,
    )
    risk_ok = sizing.action == "SIZE"
    notional = float(sizing.notional_usdt or 0.0)

    econ = evaluate_economic_entry(
        notional_usdt=notional if risk_ok else preferred_notional,
        target_distance_pct=target_pct,
        roundtrip_fee_pct=0.11,
        slippage_pct=0.02,
    )
    econ_ok = econ.action == "PASS"
    horiz = evaluate_horizon_feasibility(plan=plan, economic_edge_pass=econ_ok)
    horizon_ok = horiz.horizon_feasibility_pass

    est_cost = notional * 0.0011 if notional > 0 else preferred_notional * 0.0011
    exp_gross = notional * (target_pct / 100.0) if notional > 0 else 0.0
    exp_net = exp_gross - est_cost
    edge_ratio = (exp_gross / est_cost) if est_cost > 1e-9 else 0.0

    rank = 0.0
    if horizon_ok and econ_ok and risk_ok:
        rank = edge_ratio * liq * float(activity_score) * (1.0 + min(1.0, float(plan.vol_cover_ratio or 0)))

    reason = None
    if not cfg_ok:
        reason = cfg_block
    elif not horizon_ok:
        reason = horiz.block_code or "HORIZON_TARGET_MISMATCH"
    elif not econ_ok:
        reason = "ECONOMIC_EDGE_FAIL"
    elif not risk_ok:
        reason = "RISK_SIZING_WAIT"

    return MarketCandidate(
        symbol=symbol,
        strategy_family=strategy_family,
        direction=direction,
        entry_price=entry_price,
        forecast_horizon_sec=plan.forecast_horizon_sec,
        expected_move_pct=plan.expected_path_range_pct,
        target_move_pct=target_pct,
        expected_time_to_target=plan.expected_time_to_target,
        estimated_roundtrip_cost_usdt=est_cost,
        expected_net_target_usdt=exp_net,
        edge_cost_ratio=edge_ratio,
        liquidity=liq,
        activity_score=activity_score,
        regime=regime,
        economic_edge_pass=econ_ok,
        horizon_feasibility_pass=horizon_ok,
        horizon_config_valid=cfg_ok,
        risk_pass=risk_ok,
        rank_score=rank,
        rejection_reason=reason,
        horizon_plan=plan.to_dict(),
    )


def build_canonical_funnel_stages(candidates: list[MarketCandidate]) -> dict[str, Any]:
    """Stage-by-stage survivor counts: eligible → liquidity/data → economic → horizon → risk → prepared → trigger → order."""
    stages = {
        "eligible": len(candidates),
        "liquidity_data_pass": 0,
        "economic_pass": 0,
        "horizon_pass": 0,
        "risk_pass": 0,
        "prepared": 0,
        "triggered": 0,
        "real_orders": 0,
    }
    for c in candidates:
        if c.rejection_reason == "liquidity_too_thin":
            continue
        if not c.horizon_config_valid:
            continue
        stages["liquidity_data_pass"] += 1
        if c.economic_edge_pass:
            stages["economic_pass"] += 1
        if c.horizon_feasibility_pass:
            stages["horizon_pass"] += 1
        if c.risk_pass:
            stages["risk_pass"] += 1
    valid = [
        c
        for c in candidates
        if c.economic_edge_pass and c.horizon_feasibility_pass and c.risk_pass and c.horizon_config_valid
    ]
    if valid:
        stages["prepared"] = 1
    stages["both_pass"] = sum(
        1 for c in candidates if c.economic_edge_pass and c.horizon_feasibility_pass and c.horizon_config_valid
    )
    return stages


def rank_market_candidates(candidates: list[MarketCandidate]) -> MarketOpportunityFunnel:
    """Rank naturally valid candidates; do NOT pick highest volatility alone."""
    funnel = MarketOpportunityFunnel(eligible_universe=len(candidates))
    reject_counts: dict[str, int] = {}

    for c in candidates:
        if c.rejection_reason:
            reject_counts[c.rejection_reason] = reject_counts.get(c.rejection_reason, 0) + 1
        if c.economic_edge_pass:
            funnel.economic_edge_pass += 1
        if c.horizon_feasibility_pass:
            funnel.horizon_feasibility_pass += 1
        if c.economic_edge_pass and c.horizon_feasibility_pass:
            funnel.both_pass += 1
        if c.risk_pass:
            funnel.risk_pass += 1

    valid = [
        c
        for c in candidates
        if c.economic_edge_pass and c.horizon_feasibility_pass and c.risk_pass and c.horizon_config_valid
    ]
    valid.sort(key=lambda x: x.rank_score, reverse=True)

    funnel.top_rejection_reasons = [
        {"reason": r, "count": n}
        for r, n in sorted(reject_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
    ]

    if not valid:
        funnel.action = "WAIT"
        funnel.block_code = "NO_ECONOMICALLY_FEASIBLE_MARKET_OPPORTUNITY"
        return funnel

    best = valid[0]
    funnel.best_candidate = best
    funnel.prepared = 1
    funnel.action = "PREPARE"
    return funnel


def evaluate_symbol_opportunity(
    *,
    symbol: str,
    entry_price: float,
    turnover_24h: float,
    trade_count_24h: int = 0,
    change_pct_24h: float = 0.0,
    equity: float,
    strategy_family: str = "TREND",
    direction: str = "LONG",
    realized_vol_pct_per_hour: float = 0.35,
    target_pct: float = 0.55,
    stop_pct: float = 0.40,
    regime: str = "UNCERTAIN",
    qty_step: float = 0.001,
    min_qty: float = 0.001,
    min_notional: float = 5.0,
    preferred_notional: float = 350.0,
) -> dict[str, Any]:
    """Evaluate one symbol for full-market funnel (runner-compatible dict)."""
    act = min(1.0, max(0.2, math.log10(max(turnover_24h, 1.0)) / 8.0)) if turnover_24h else 0.5
    if abs(change_pct_24h) > 3.0:
        regime = "HIGH_VOLATILITY" if change_pct_24h > 0 else "TREND_DOWN"
    cand = score_market_candidate(
        symbol=symbol,
        entry_price=entry_price,
        equity=equity,
        vol_pct_per_hour=realized_vol_pct_per_hour,
        strategy_family=strategy_family,
        direction=direction,
        target_pct=target_pct,
        stop_pct=stop_pct,
        regime=regime,
        turnover24h=turnover_24h,
        activity_score=act,
        qty_step=qty_step,
        min_qty=min_qty,
        min_notional=min_notional,
        preferred_notional=preferred_notional,
    )
    d = cand.to_dict()
    d["liquidity_score"] = cand.liquidity
    d["trade_count_24h"] = trade_count_24h
    return d


def select_best_market_opportunity(candidates: list[Any]) -> dict[str, Any]:
    """Runner-facing selection envelope with funnel counts."""
    objs: list[MarketCandidate] = []
    for c in candidates:
        if isinstance(c, MarketCandidate):
            objs.append(c)
        else:
            objs.append(
                MarketCandidate(
                    symbol=str(c.get("symbol") or ""),
                    strategy_family=str(c.get("strategy_family") or "TREND"),
                    direction=str(c.get("direction") or "LONG"),
                    entry_price=float(c.get("entry_price") or 0),
                    forecast_horizon_sec=c.get("forecast_horizon_sec"),
                    expected_move_pct=c.get("expected_move_pct"),
                    target_move_pct=c.get("target_move_pct"),
                    expected_time_to_target=c.get("expected_time_to_target"),
                    estimated_roundtrip_cost_usdt=c.get("estimated_roundtrip_cost_usdt"),
                    expected_net_target_usdt=c.get("expected_net_target_usdt"),
                    edge_cost_ratio=c.get("edge_cost_ratio"),
                    liquidity=float(c.get("liquidity") or c.get("liquidity_score") or 0),
                    activity_score=float(c.get("activity_score") or 0),
                    regime=str(c.get("regime") or "UNCERTAIN"),
                    economic_edge_pass=bool(c.get("economic_edge_pass")),
                    horizon_feasibility_pass=bool(c.get("horizon_feasibility_pass")),
                    horizon_config_valid=bool(c.get("horizon_config_valid", True)),
                    risk_pass=bool(c.get("risk_pass")),
                    rank_score=float(c.get("rank_score") or 0),
                    rejection_reason=c.get("rejection_reason"),
                    horizon_plan=c.get("horizon_plan"),
                )
            )
    funnel = rank_market_candidates(objs)
    fd = funnel.to_dict()
    canonical = build_canonical_funnel_stages(objs)
    out: dict[str, Any] = {
        "action": "SELECT" if funnel.best_candidate else "WAIT",
        "block_code": funnel.block_code,
        "funnel": {
            "eligible": canonical["eligible"],
            "eligible_universe": funnel.eligible_universe,
            "liquidity_data_pass": canonical["liquidity_data_pass"],
            "economic_pass": canonical["economic_pass"],
            "economic_edge_pass": funnel.economic_edge_pass,
            "horizon_pass": canonical["horizon_pass"],
            "horizon_feasibility_pass": funnel.horizon_feasibility_pass,
            "both_pass": canonical["both_pass"],
            "risk_pass": canonical["risk_pass"],
            "prepared": canonical["prepared"],
            "triggered": canonical["triggered"],
            "real_orders": canonical["real_orders"],
            "top_rejection_reasons": funnel.top_rejection_reasons,
            "canonical_order": [
                "eligible",
                "liquidity_data_pass",
                "economic_pass",
                "horizon_pass",
                "risk_pass",
                "prepared",
                "triggered",
                "real_orders",
            ],
        },
        "selected": fd.get("best_candidate"),
        "selected_symbol": (funnel.best_candidate.symbol if funnel.best_candidate else None),
    }
    if funnel.best_candidate is None:
        out["action"] = "WAIT"
    return out
