"""True event-driven Structural Geometry simulation on REAL historical candles.

Natural entry only. Cost Gate pass ≠ trade. Synthetic forced paths forbidden
for qualification statuses.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset
from backend.nexus_demo_execution.market_structure import (
    atr_from_ohlc,
    support_resistance_from_swings,
    swing_high_low,
)
from backend.nexus_demo_execution.pit_data_foundation import (
    validate_candidate_field_asof,
    validate_outcome_after_decision,
)
from backend.nexus_demo_execution.session_limits import (
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
    TAKER_FEE_RATE_DEFAULT,
)
from backend.nexus_demo_execution.structural_geometry_qualify import (
    CandidateEvidence,
    evaluate_structural_geometry,
)

EntryStatus = Literal[
    "ENTRY_NOT_TRIGGERED",
    "ENTRY_TRIGGERED_NOT_FILLED",
    "ENTRY_FILLED",
    "ENTRY_EXPIRED",
    "ENTRY_INVALIDATED_BEFORE_FILL",
    "COST_GATE_BLOCKED",
    "GEOMETRY_BLOCKED",
]

ExitStatus = Literal[
    "STOP_LOSS",
    "TAKE_PROFIT",
    "TIME_STOP",
    "TRAILING_EXIT",
    "BREAK_EVEN_EXIT",
    "EARLY_EXIT",
    "PARTIAL_AND_FINAL_EXIT",
    "UNRESOLVED_AT_DATA_END",
]

INTRABAR_METHOD = "ADVERSE_FIRST"
TAKER_FEE = TAKER_FEE_RATE_DEFAULT  # 0.00055


@dataclass
class MarketCandidate:
    symbol: str
    side: str
    strategy: str
    regime: str
    candidate_snapshot_time: int
    last_input_candle_time: int
    entry_price: float
    evidence: CandidateEvidence
    interval: str = "15"
    future_data_reference_count: int = 0
    look_ahead_contamination: bool = False


@dataclass
class SimTrade:
    symbol: str
    side: str
    strategy: str
    regime: str
    entry_status: EntryStatus
    exit_status: ExitStatus | None = None
    candidate_snapshot_time: int | None = None
    entry_ts: int | None = None
    exit_ts: int | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    stop: float | None = None
    take_profit: float | None = None
    qty: float = 1.0
    gross_pnl: float | None = None
    entry_fee: float | None = None
    exit_fee: float | None = None
    total_fees: float | None = None
    spread_cost: float | None = None
    slippage_cost: float | None = None
    funding: float | None = None
    net_pnl: float | None = None
    intrabar_resolution_method: str | None = None
    adverse_first_applied: bool = False
    ambiguity_count: int = 0
    look_ahead_contamination: bool = False
    path_source: str = "REAL_HISTORICAL_MARKET_DATA"


def _ohlc_dicts(candles: list[Candle]) -> list[dict[str, float]]:
    return [
        {"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume, "ts_ms": float(c.ts_ms)}
        for c in candles
    ]


def _regime(closes: list[float]) -> str:
    if len(closes) < 20:
        return "UNKNOWN"
    sma = sum(closes[-20:]) / 20.0
    last = closes[-1]
    if last > sma * 1.002:
        return "TREND_UP"
    if last < sma * 0.998:
        return "TREND_DOWN"
    return "RANGE"


def build_candidates_from_dataset(
    ds: MarketDataset,
    *,
    min_bars: int = 40,
    stride: int = 4,
    atr_period: int = 14,
    swing_lookback: int = 20,
    fee_rate: float = TAKER_FEE,
    spread_bps: float = 2.0,
    slippage_bps: float = 2.0,
    funding_rate: float = 0.0001,
    qty: float = 1.0,
) -> list[MarketCandidate]:
    """Create candidates using only candles available at snapshot time (no future)."""
    out: list[MarketCandidate] = []
    candles = ds.candles
    for i in range(min_bars, len(candles) - 2, max(1, stride)):
        hist = candles[: i + 1]
        ohlc = _ohlc_dicts(hist)
        last = hist[-1]
        atr = atr_from_ohlc(ohlc, period=atr_period)
        sh, sl = swing_high_low(ohlc, lookback=swing_lookback)
        support, resistance = support_resistance_from_swings(last=last.close, swing_high=sh, swing_low=sl)
        closes = [c.close for c in hist]
        regime = _regime(closes)
        if regime == "TREND_UP":
            side = "Buy"
        elif regime == "TREND_DOWN":
            side = "Sell"
        else:
            side = "Buy" if last.close >= last.open else "Sell"
        decision_ts_ms = int(last.close_ts_ms or last.ts_ms)
        feature_asof = {
            "entry_price": decision_ts_ms,
            "atr": decision_ts_ms,
            "recent_swing_high": decision_ts_ms,
            "recent_swing_low": decision_ts_ms,
            "support": decision_ts_ms,
            "resistance": decision_ts_ms,
            "liquidity_levels": decision_ts_ms,
            "spread_bps": decision_ts_ms,
            "slippage_bps": decision_ts_ms,
            "fee_rate": decision_ts_ms,
            "funding_rate": decision_ts_ms,
            "tick_size": decision_ts_ms,
            "qty": decision_ts_ms,
        }
        feature_sources = {field: "PIT_HISTORICAL_MARKET_DATA_OR_STATIC_POLICY" for field in feature_asof}
        evidence = CandidateEvidence(
            symbol=ds.symbol,
            side=side,
            entry_price=float(last.close),
            regime=regime,
            strategy="STRUCT_SWING",
            atr=atr,
            recent_swing_high=sh,
            recent_swing_low=sl,
            support=support,
            resistance=resistance,
            liquidity_levels=[x for x in [resistance if side == "Buy" else support] if x is not None],
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
            fee_rate=fee_rate,
            funding_rate=funding_rate,
            tick_size=None,
            qty=qty,
            data_freshness_sec=0.0,
            ts=float(last.ts_ms),
            decision_ts_ms=decision_ts_ms,
            field_asof_ts_ms=feature_asof,
            field_sources=feature_sources,
        )
        out.append(
            MarketCandidate(
                symbol=ds.symbol,
                side=side,
                strategy="STRUCT_SWING",
                regime=regime,
                interval=ds.interval,
                candidate_snapshot_time=int(last.ts_ms),
                last_input_candle_time=int(last.ts_ms),
                entry_price=float(last.close),
                evidence=evidence,
                future_data_reference_count=0,
                look_ahead_contamination=False,
            )
        )
    return out


def _fee(notional: float, rate: float) -> float:
    return abs(notional) * rate


def _bps(notional: float, bps: float) -> float:
    return abs(notional) * (bps / 10000.0)


def simulate_natural_trade(
    *,
    candidate: MarketCandidate,
    subsequent: list[Candle],
    entry_wait_bars: int = 12,
    time_stop_bars: int = 48,
    adverse_first: bool = True,
    cost_mode: str = "BASE_CONSERVATIVE",
    enforce_risk_sizing: bool = True,
    apply_costs: bool = True,
) -> SimTrade:
    """Natural entry on subsequent real candles only."""
    asof = validate_candidate_field_asof(candidate.evidence)
    if not asof.ok:
        return SimTrade(
            symbol=candidate.symbol,
            side=candidate.side,
            strategy=candidate.strategy,
            regime=candidate.regime,
            entry_status="GEOMETRY_BLOCKED",
            candidate_snapshot_time=candidate.candidate_snapshot_time,
            look_ahead_contamination=True,
        )
    if candidate.evidence.decision_ts_ms is not None:
        outcome = validate_outcome_after_decision(
            decision_ts_ms=int(candidate.evidence.decision_ts_ms),
            outcome_bars=subsequent,
            interval=candidate.interval,
        )
        if not outcome.ok:
            return SimTrade(
                symbol=candidate.symbol,
                side=candidate.side,
                strategy=candidate.strategy,
                regime=candidate.regime,
                entry_status="GEOMETRY_BLOCKED",
                candidate_snapshot_time=candidate.candidate_snapshot_time,
                look_ahead_contamination=True,
            )
    geo = evaluate_structural_geometry(candidate.evidence)
    if geo.get("geometry_missing") or geo.get("geometry_invalid") or not geo.get("geometry_complete"):
        return SimTrade(
            symbol=candidate.symbol,
            side=candidate.side,
            strategy=candidate.strategy,
            regime=candidate.regime,
            entry_status="GEOMETRY_BLOCKED",
            candidate_snapshot_time=candidate.candidate_snapshot_time,
            look_ahead_contamination=candidate.look_ahead_contamination,
        )
    if not geo.get("cost_gate_pass"):
        return SimTrade(
            symbol=candidate.symbol,
            side=candidate.side,
            strategy=candidate.strategy,
            regime=candidate.regime,
            entry_status="COST_GATE_BLOCKED",
            candidate_snapshot_time=candidate.candidate_snapshot_time,
        )

    stop = float(geo["stop_price"])
    tp = float(geo["take_profit_price"])
    entry = float(candidate.entry_price)
    side = candidate.side
    buy = side.lower() in {"buy", "long"}

    from backend.nexus_demo_execution.risk_sizing import size_position
    from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP, MAX_SINGLE_TRADE_NET_LOSS

    raw_qty = candidate.evidence.qty
    if enforce_risk_sizing and (raw_qty is None or float(raw_qty) >= 0.99):
        step = 0.001
        if candidate.symbol.startswith("ETH"):
            step = 0.01
        elif candidate.symbol.startswith("DOGE"):
            step = 1.0
        elif candidate.symbol.startswith("XRP") or candidate.symbol.startswith("SOL"):
            step = 0.1
        sized = size_position(
            symbol=candidate.symbol,
            side=side,
            entry_price=entry,
            stop_price=stop,
            take_profit_price=tp,
            margin_usdt=MARGIN_PER_TRADE_CAP,
            leverage=FIXED_LEVERAGE,
            risk_budget_usdt=MAX_SINGLE_TRADE_NET_LOSS,
            qty_step=step,
            min_order_qty=step,
            min_notional=5.0,
        )
        if not sized.allowed:
            return SimTrade(
                symbol=candidate.symbol,
                side=side,
                strategy=candidate.strategy,
                regime=candidate.regime,
                entry_status="GEOMETRY_BLOCKED",
                candidate_snapshot_time=candidate.candidate_snapshot_time,
                stop=stop,
                take_profit=tp,
                qty=0.0,
            )
        qty = float(sized.quantity)
        candidate.evidence.qty = qty
    else:
        qty = float(raw_qty if raw_qty is not None else 1.0)

    # Geometry/cost-gate keep real fee inputs; diagnostic gross path zeros costs at PnL only.
    fee_rate = float(TAKER_FEE if candidate.evidence.fee_rate is None else candidate.evidence.fee_rate)
    slip_bps = float(0.0 if candidate.evidence.slippage_bps is None else candidate.evidence.slippage_bps)
    spread_bps = float(0.0 if candidate.evidence.spread_bps is None else candidate.evidence.spread_bps)
    if not apply_costs or cost_mode == "GROSS_NO_COST_DIAGNOSTIC":
        fee_rate = 0.0
        slip_bps = 0.0
        spread_bps = 0.0
    elif cost_mode == "ADVERSE_COST_STRESS":
        slip_bps *= 2.0
        spread_bps *= 2.0
        fee_rate = max(fee_rate, TAKER_FEE)
    elif cost_mode == "OBSERVED_COST":
        pass  # use observed estimates as-is

    trade = SimTrade(
        symbol=candidate.symbol,
        side=side,
        strategy=candidate.strategy,
        regime=candidate.regime,
        entry_status="ENTRY_NOT_TRIGGERED",
        candidate_snapshot_time=candidate.candidate_snapshot_time,
        stop=stop,
        take_profit=tp,
        qty=qty,
        look_ahead_contamination=candidate.look_ahead_contamination,
        path_source="REAL_HISTORICAL_MARKET_DATA",
    )
    if not subsequent:
        trade.entry_status = "ENTRY_EXPIRED"
        return trade

    # Natural limit-style fill: price must trade through entry after snapshot.
    fill_idx: int | None = None
    for j, bar in enumerate(subsequent[:entry_wait_bars]):
        # Invalidation before fill: stop touched before entry
        hit_sl_pre = (bar.low <= stop) if buy else (bar.high >= stop)
        touches_entry = bar.low <= entry <= bar.high
        if hit_sl_pre and not touches_entry:
            trade.entry_status = "ENTRY_INVALIDATED_BEFORE_FILL"
            return trade
        if touches_entry:
            fill_idx = j
            break
    if fill_idx is None:
        trade.entry_status = "ENTRY_EXPIRED" if len(subsequent) >= entry_wait_bars else "ENTRY_NOT_TRIGGERED"
        return trade

    fill_bar = subsequent[fill_idx]
    fill_px = entry
    # Adverse slippage on fill
    if buy:
        fill_px *= 1 + slip_bps / 10000.0
    else:
        fill_px *= 1 - slip_bps / 10000.0
    qty = trade.qty
    notional = abs(fill_px * qty)
    entry_fee = _fee(notional, fee_rate)
    spread = _bps(notional, spread_bps)
    slip = _bps(notional, slip_bps)
    trade.entry_status = "ENTRY_FILLED"
    trade.entry_ts = fill_bar.ts_ms
    trade.entry_price = fill_px
    trade.entry_fee = entry_fee
    trade.spread_cost = spread
    trade.slippage_cost = slip
    trade.intrabar_resolution_method = INTRABAR_METHOD
    trade.adverse_first_applied = adverse_first

    funding_acc = 0.0
    amb = 0
    post = subsequent[fill_idx + 1 :]
    for i, bar in enumerate(post, start=1):
        if i > time_stop_bars:
            trade.exit_status = "TIME_STOP"
            trade.exit_ts = bar.ts_ms
            trade.exit_price = bar.close
            break
        if apply_costs and cost_mode != "GROSS_NO_COST_DIAGNOSTIC":
            fr = 0.0001 if candidate.evidence.funding_rate is None else float(candidate.evidence.funding_rate)
            funding_acc += abs(fill_px * qty) * fr / (24.0 * 4.0)
        hit_sl = (bar.low <= stop) if buy else (bar.high >= stop)
        hit_tp = (bar.high >= tp) if buy else (bar.low <= tp)
        if hit_sl and hit_tp:
            amb += 1
            if not adverse_first:
                trade.look_ahead_contamination = True
            trade.exit_status = "STOP_LOSS"
            trade.exit_ts = bar.ts_ms
            trade.exit_price = stop
            trade.adverse_first_applied = True
            break
        if hit_sl:
            trade.exit_status = "STOP_LOSS"
            trade.exit_ts = bar.ts_ms
            trade.exit_price = stop
            break
        if hit_tp:
            trade.exit_status = "TAKE_PROFIT"
            trade.exit_ts = bar.ts_ms
            trade.exit_price = tp
            break
    else:
        trade.exit_status = "UNRESOLVED_AT_DATA_END"
        if post:
            trade.exit_ts = post[-1].ts_ms
            trade.exit_price = post[-1].close
        else:
            trade.exit_ts = fill_bar.ts_ms
            trade.exit_price = fill_px

    trade.ambiguity_count = amb
    if trade.exit_price is None or trade.entry_price is None:
        return trade
    if trade.exit_status == "UNRESOLVED_AT_DATA_END":
        # Unresolved must not count as win/loss PnL
        trade.net_pnl = None
        trade.gross_pnl = None
        return trade

    exit_notional = abs(float(trade.exit_price) * qty)
    exit_fee = _fee(exit_notional, fee_rate)
    if buy:
        gross = (float(trade.exit_price) - float(trade.entry_price)) * qty
    else:
        gross = (float(trade.entry_price) - float(trade.exit_price)) * qty
    fees = entry_fee + exit_fee
    net = gross - fees - spread - slip - funding_acc
    trade.gross_pnl = round(gross, 8)
    trade.exit_fee = round(exit_fee, 8)
    trade.total_fees = round(fees, 8)
    trade.funding = round(funding_acc, 8)
    trade.net_pnl = round(net, 8)
    return trade


def summarize_trades(trades: list[SimTrade], *, min_sample: int = 30) -> dict[str, Any]:
    completed = [
        t
        for t in trades
        if t.entry_status == "ENTRY_FILLED"
        and t.exit_status
        in {"STOP_LOSS", "TAKE_PROFIT", "TIME_STOP", "TRAILING_EXIT", "BREAK_EVEN_EXIT", "EARLY_EXIT", "PARTIAL_AND_FINAL_EXIT"}
        and t.net_pnl is not None
    ]
    unresolved = sum(1 for t in trades if t.exit_status == "UNRESOLVED_AT_DATA_END")
    nets = [float(t.net_pnl) for t in completed]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    gw = sum(wins) if wins else 0.0
    gl = abs(sum(losses)) if losses else 0.0
    pf = (gw / gl) if gl > 0 else None
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    cons = 0
    max_cons = 0
    largest_loss = None
    for n in nets:
        eq += n
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
        if n <= 0:
            cons += 1
            max_cons = max(max_cons, cons)
            largest_loss = n if largest_loss is None else min(largest_loss, n)
        else:
            cons = 0
    look_ahead = any(t.look_ahead_contamination for t in trades)
    amb = sum(int(t.ambiguity_count) for t in trades)
    synth = sum(1 for t in trades if t.path_source != "REAL_HISTORICAL_MARKET_DATA")
    return {
        "candidate_count": len(trades),
        "geometry_complete_count": sum(1 for t in trades if t.entry_status not in {"GEOMETRY_BLOCKED"}),
        "cost_gate_pass_count": sum(
            1 for t in trades if t.entry_status not in {"GEOMETRY_BLOCKED", "COST_GATE_BLOCKED"}
        ),
        "entry_triggered_count": sum(
            1
            for t in trades
            if t.entry_status
            in {"ENTRY_FILLED", "ENTRY_TRIGGERED_NOT_FILLED", "ENTRY_INVALIDATED_BEFORE_FILL"}
        ),
        "entry_filled_count": sum(1 for t in trades if t.entry_status == "ENTRY_FILLED"),
        "entry_not_triggered_total": sum(1 for t in trades if t.entry_status == "ENTRY_NOT_TRIGGERED"),
        "entry_expired_total": sum(1 for t in trades if t.entry_status == "ENTRY_EXPIRED"),
        "completed_trade_count": len(completed),
        "simulated_trade_count": len(completed),
        "unresolved_trade_count": unresolved,
        "gross_pnl": round(sum(float(t.gross_pnl or 0) for t in completed), 8) if completed else None,
        "total_fees": round(sum(float(t.total_fees or 0) for t in completed), 8) if completed else None,
        "spread_cost": round(sum(float(t.spread_cost or 0) for t in completed), 8) if completed else None,
        "slippage_cost": round(sum(float(t.slippage_cost or 0) for t in completed), 8) if completed else None,
        "funding": round(sum(float(t.funding or 0) for t in completed), 8) if completed else None,
        "net_pnl": round(sum(nets), 8) if completed else None,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(completed)) if completed else None,
        "profit_factor": (None if pf is None else round(pf, 6)),
        "expectancy": (statistics.fmean(nets) if nets else None),
        "maximum_drawdown": (round(mdd, 8) if completed else None),
        "largest_loss": largest_loss,
        "maximum_consecutive_losses": max_cons,
        "look_ahead_contamination": look_ahead,
        "intrabar_ambiguity_count": amb,
        "synthetic_forced_trade_count": synth,
        "intrabar_resolution_method": INTRABAR_METHOD,
        "path_source": "REAL_HISTORICAL_MARKET_DATA",
        "floors_unchanged": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
        "symbol_distribution": _count([t.symbol for t in completed]),
        "regime_distribution": _count([t.regime for t in completed]),
        "strategy_distribution": _count([t.strategy for t in completed]),
    }


def _count(items: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return out


def _classify_oos(summary: dict[str, Any], *, min_sample: int, data_valid: bool) -> str:
    if not data_valid:
        return "OOS_DATA_INVALID"
    if summary.get("look_ahead_contamination"):
        return "OOS_PERFORMANCE_FAILED"
    if int(summary.get("synthetic_forced_trade_count") or 0) > 0:
        return "OOS_DATA_INVALID"
    n = int(summary.get("simulated_trade_count") or 0)
    if n == 0:
        return "OOS_INSUFFICIENT_SAMPLE"
    required = (
        "net_pnl",
        "profit_factor",
        "expectancy",
        "maximum_drawdown",
        "win_rate",
        "gross_pnl",
        "total_fees",
        "spread_cost",
        "slippage_cost",
        "funding",
    )
    if any(summary.get(k) is None for k in required):
        return "OOS_INSUFFICIENT_SAMPLE"
    if n < min_sample:
        return "OOS_INSUFFICIENT_SAMPLE"
    net = float(summary["net_pnl"])
    pf = float(summary["profit_factor"])
    exp = float(summary["expectancy"])
    if net > 0 and pf > 1 and exp > 0:
        return "OOS_PERFORMANCE_VALIDATED"
    return "OOS_PERFORMANCE_FAILED"


def run_market_qualification(
    datasets: list[MarketDataset],
    *,
    min_sample: int = 30,
    cost_mode: str = "BASE_CONSERVATIVE",
) -> dict[str, Any]:
    """Chronological multi-symbol WF + untouched OOS on real historical data."""
    if any(d.classification != "REAL_HISTORICAL_MARKET_DATA" for d in datasets):
        return {
            "market_data_source": "DATA_INVALID",
            "oos_status": "OOS_DATA_INVALID",
            "qualification_complete": False,
            "recommendation": "NEXUS_GEOMETRY_QUALIFICATION_IN_PROGRESS",
            "look_ahead_contamination": False,
            "synthetic_forced_trade_count": 0,
        }

    # Build all candidates tagged with symbol + index into that symbol's candle series
    all_cands: list[tuple[MarketCandidate, list[Candle]]] = []
    for ds in datasets:
        cands = build_candidates_from_dataset(ds)
        by_ts = {c.ts_ms: i for i, c in enumerate(ds.candles)}
        for cand in cands:
            idx = by_ts.get(cand.candidate_snapshot_time)
            if idx is None:
                continue
            subsequent = ds.candles[idx + 1 :]
            all_cands.append((cand, subsequent))

    all_cands.sort(key=lambda x: x[0].candidate_snapshot_time)
    n = len(all_cands)
    if n < 20:
        return {
            "market_data_source": "REAL_HISTORICAL_MARKET_DATA",
            "oos_status": "OOS_INSUFFICIENT_SAMPLE",
            "walk_forward_folds": [],
            "recommendation": "NEXUS_OOS_INSUFFICIENT_SAMPLE",
            "qualification_complete": False,
            "synthetic_forced_trade_count": 0,
            "look_ahead_contamination": False,
            "candidate_count": n,
        }

    # Three chronological folds with non-overlapping OOS blocks in the last 45%
    i40, i55, i70, i85 = int(n * 0.40), int(n * 0.55), int(n * 0.70), int(n * 0.85)
    folds_spec = [
        ("fold1_train", all_cands[:i40]),
        ("fold1_validation", all_cands[i40:i55]),
        ("fold1_test", all_cands[i55:i70]),
        ("fold2_test", all_cands[i70:i85]),
        ("fold3_test_oos", all_cands[i85:]),
    ]

    def _run(tag: str, rows: list[tuple[MarketCandidate, list[Candle]]]) -> dict[str, Any]:
        trades = [
            simulate_natural_trade(candidate=c, subsequent=sub, cost_mode=cost_mode) for c, sub in rows
        ]
        s = summarize_trades(trades, min_sample=min_sample)
        s["fold_tag"] = tag
        return s

    fold_results = {tag: _run(tag, rows) for tag, rows in folds_spec}
    # Cost sensitivity on OOS only
    oos_rows = all_cands[i85:]
    sens = {}
    for mode in ("BASE_CONSERVATIVE", "OBSERVED_COST", "ADVERSE_COST_STRESS"):
        trades = [simulate_natural_trade(candidate=c, subsequent=sub, cost_mode=mode) for c, sub in oos_rows]
        sens[mode] = summarize_trades(trades, min_sample=min_sample)

    oos = fold_results["fold3_test_oos"]
    # Prefer adverse stress must also not be the only failing mode for validation
    oos_status = _classify_oos(oos, min_sample=min_sample, data_valid=True)
    if oos_status == "OOS_PERFORMANCE_VALIDATED":
        adv = sens["ADVERSE_COST_STRESS"]
        if (adv.get("net_pnl") is None) or float(adv["net_pnl"]) <= 0 or float(adv.get("profit_factor") or 0) <= 1:
            oos_status = "OOS_PERFORMANCE_FAILED"
            oos["adverse_cost_failed"] = True

    wf = fold_results["fold1_validation"]
    look_ahead = any(fr.get("look_ahead_contamination") for fr in fold_results.values())
    synth = sum(int(fr.get("synthetic_forced_trade_count") or 0) for fr in fold_results.values())

    if look_ahead:
        recommendation = "NEXUS_GEOMETRY_QUALIFICATION_IN_PROGRESS"
        oos_status = "OOS_PERFORMANCE_FAILED"
    elif oos_status == "OOS_INSUFFICIENT_SAMPLE":
        recommendation = "NEXUS_OOS_INSUFFICIENT_SAMPLE"
    elif oos_status == "OOS_PERFORMANCE_VALIDATED":
        recommendation = "NEXUS_RISK_REVIEW_READY"
    else:
        recommendation = "NEXUS_GEOMETRY_QUALIFICATION_IN_PROGRESS"

    provenance = [d.provenance() for d in datasets]
    return {
        "market_data_source": "REAL_HISTORICAL_MARKET_DATA",
        "market_data_symbols": [d.symbol for d in datasets],
        "market_data_time_range": {
            "start": min(d.start_time for d in datasets),
            "end": max(d.end_time for d in datasets),
        },
        "market_data_record_count": sum(d.record_count for d in datasets),
        "market_data_checksums": {d.symbol: d.data_checksum for d in datasets},
        "market_data_provenance": provenance,
        "walk_forward_folds": fold_results,
        "walk_forward_simulated_trades": wf.get("simulated_trade_count"),
        "walk_forward_net_pnl": wf.get("net_pnl"),
        "walk_forward_profit_factor": wf.get("profit_factor"),
        "walk_forward_expectancy": wf.get("expectancy"),
        "walk_forward_max_drawdown": wf.get("maximum_drawdown"),
        "oos": oos,
        "oos_status": oos_status,
        "oos_simulated_trades": oos.get("simulated_trade_count"),
        "oos_net_pnl": oos.get("net_pnl"),
        "oos_profit_factor": oos.get("profit_factor"),
        "oos_expectancy": oos.get("expectancy"),
        "oos_max_drawdown": oos.get("maximum_drawdown"),
        "oos_win_rate": oos.get("win_rate"),
        "cost_sensitivity": sens,
        "synthetic_forced_trade_count": synth,
        "look_ahead_contamination": look_ahead,
        "intrabar_ambiguity_count": int(oos.get("intrabar_ambiguity_count") or 0),
        "floors_unchanged": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
        "risk_review_packet_ready": oos_status == "OOS_PERFORMANCE_VALIDATED" and not look_ahead and synth == 0,
        "risk_review_status": "RISK_REVIEW_PENDING_FOUNDER",
        "shadow_status": "NOT_APPLIED",
        "qualification_complete": False,
        "recommendation": recommendation,
    }
