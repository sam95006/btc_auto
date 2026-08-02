"""OOS failure attribution + risk-model integrity audit.

Marks prior failed holdout as CONSUMED_FAILED_HOLDOUT.
Does not start trading sessions.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset, load_dataset
from backend.nexus_demo_execution.market_event_sim import (
    MarketCandidate,
    SimTrade,
    build_candidates_from_dataset,
    run_market_qualification,
    simulate_natural_trade,
    summarize_trades,
)
from backend.nexus_demo_execution.risk_sizing import (
    AUDIT_SESSION_NET_LOSS_LIMIT,
    detect_sizing_defects,
    liquidation_price,
    size_position,
)
from backend.nexus_demo_execution.session_limits import (
    FIXED_LEVERAGE,
    MARGIN_MODE,
    MARGIN_PER_TRADE_CAP,
    MAX_SINGLE_TRADE_NET_LOSS,
    TAKER_FEE_RATE_DEFAULT,
)
from backend.nexus_demo_execution.structural_geometry_qualify import evaluate_structural_geometry

CONSUMED_OOS_ID = "OOS_REAL_MARKET_2026Q_FAILED_HOLDOUT_e186d13"
CONSUMED_STATUS = "CONSUMED_FAILED_HOLDOUT"


@dataclass
class TradeAuditRow:
    symbol: str
    side: str
    strategy: str
    regime: str
    entry_price: float
    quantity: float
    notional: float
    margin: float
    leverage: int
    stop_price: float
    stop_distance_pct: float
    take_profit_price: float | None
    target_distance_pct: float | None
    liquidation_price: float
    distance_to_liquidation_pct: float
    gross_pnl: float | None
    fees: float | None
    spread_cost: float | None
    slippage: float | None
    funding: float | None
    net_pnl: float | None
    maximum_possible_loss: float
    risk_budget: float
    risk_budget_breached: bool
    exit_status: str | None
    defects: list[str] = field(default_factory=list)
    mfe: float | None = None
    mae: float | None = None
    time_to_mfe_bars: int | None = None
    time_to_mae_bars: int | None = None
    sizing_mode: str = "LEGACY_QTY1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _r_unit(entry: float, stop: float) -> float:
    return abs(entry - stop) or 1e-12


def compute_mfe_mae(
    *,
    side: str,
    entry_price: float,
    stop: float,
    subsequent_after_fill: list[Candle],
) -> dict[str, Any]:
    """Diagnostic only — never used as live features."""
    buy = side.lower() in {"buy", "long"}
    r = _r_unit(entry_price, stop)
    mfe = 0.0
    mae = 0.0
    t_mfe = 0
    t_mae = 0
    for i, bar in enumerate(subsequent_after_fill, start=1):
        if buy:
            fav = bar.high - entry_price
            adv = entry_price - bar.low
        else:
            fav = entry_price - bar.low
            adv = bar.high - entry_price
        if fav > mfe:
            mfe = fav
            t_mfe = i
        if adv > mae:
            mae = adv
            t_mae = i
    return {
        "mfe": mfe,
        "mae": mae,
        "mfe_r": mfe / r,
        "mae_r": mae / r,
        "time_to_mfe_bars": t_mfe,
        "time_to_mae_bars": t_mae,
        "reached_0_5R": mfe >= 0.5 * r,
        "reached_1R": mfe >= 1.0 * r,
        "stopped_before_favorable": mfe <= 0,
    }


@dataclass
class SizedMeta:
    sized: Any
    block_reason: str


def simulate_with_risk_sizing(
    *,
    candidate: MarketCandidate,
    subsequent: list[Candle],
    cost_mode: str = "BASE_CONSERVATIVE",
    apply_costs: bool = True,
) -> tuple[SimTrade, SizedMeta | None]:
    """Natural entry sim with Founder risk sizing. Sets candidate.evidence.qty."""
    geo = evaluate_structural_geometry(candidate.evidence)
    if not geo.get("geometry_complete") or not geo.get("cost_gate_pass"):
        trade = simulate_natural_trade(
            candidate=candidate, subsequent=subsequent, cost_mode=cost_mode
        )
        return trade, None

    stop = float(geo["stop_price"])
    tp = float(geo["take_profit_price"])
    step = 0.001
    if candidate.symbol.startswith("BTC"):
        step = 0.001
    elif candidate.symbol.startswith("ETH"):
        step = 0.01
    elif candidate.symbol.startswith("DOGE"):
        step = 1.0
    elif candidate.symbol.startswith("XRP"):
        step = 0.1
    else:
        step = 0.1

    sized = size_position(
        symbol=candidate.symbol,
        side=candidate.side,
        entry_price=float(candidate.entry_price),
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
        trade = SimTrade(
            symbol=candidate.symbol,
            side=candidate.side,
            strategy=candidate.strategy,
            regime=candidate.regime,
            entry_status="GEOMETRY_BLOCKED",
            candidate_snapshot_time=candidate.candidate_snapshot_time,
            stop=stop,
            take_profit=tp,
            qty=0.0,
            path_source="REAL_HISTORICAL_MARKET_DATA",
        )
        return trade, SizedMeta(sized=sized, block_reason=sized.block_reason)

    candidate.evidence.qty = sized.quantity
    # Do NOT mutate fee_rate to 0 on evidence — geometry treats fee_rate<=0 as FEE_RATE_UNKNOWN.
    mode = "GROSS_NO_COST_DIAGNOSTIC" if not apply_costs else cost_mode
    trade = simulate_natural_trade(
        candidate=candidate,
        subsequent=subsequent,
        cost_mode=mode,
        apply_costs=apply_costs,
    )
    trade.qty = sized.quantity
    return trade, SizedMeta(sized=sized, block_reason=sized.block_reason)

def audit_legacy_qty1_trades(
    pairs: list[tuple[MarketCandidate, list[Candle]]],
) -> dict[str, Any]:
    """Re-run with legacy qty=1.0 to quantify risk-model defects on the failed cohort method."""
    rows: list[TradeAuditRow] = []
    risk_breach = 0
    liq_breach = 0
    invalid_size = 0
    pnl_err = 0
    for cand, sub in pairs:
        cand.evidence.qty = 1.0
        trade = simulate_natural_trade(candidate=cand, subsequent=sub, enforce_risk_sizing=False)
        if trade.entry_status != "ENTRY_FILLED" or trade.net_pnl is None:
            continue
        entry = float(trade.entry_price or cand.entry_price)
        stop = float(trade.stop or 0.0)
        qty = float(trade.qty or 1.0)
        det = detect_sizing_defects(
            entry_price=entry,
            qty=qty,
            stop_price=stop,
            side=trade.side,
            net_pnl=trade.net_pnl,
        )
        if "RISK_BUDGET_BREACH" in det["defects"] or "LOSS_SCALE_INCONSISTENT_WITH_3U_BUDGET" in det["defects"]:
            risk_breach += 1
        if "STOP_BEYOND_LIQUIDATION" in det["defects"]:
            liq_breach += 1
        if "POSITION_SIZING_OFF_TARGET" in det["defects"] or "LEVERAGE_LIKELY_DOUBLE_APPLIED" in det["defects"]:
            invalid_size += 1
        liq = float(det["liquidation_price"])
        buy = trade.side.lower() in {"buy", "long"}
        dist = ((entry - liq) / entry) if buy else ((liq - entry) / entry)
        rows.append(
            TradeAuditRow(
                symbol=trade.symbol,
                side=trade.side,
                strategy=trade.strategy,
                regime=trade.regime,
                entry_price=entry,
                quantity=qty,
                notional=abs(qty * entry),
                margin=MARGIN_PER_TRADE_CAP,
                leverage=FIXED_LEVERAGE,
                stop_price=stop,
                stop_distance_pct=abs(entry - stop) / entry,
                take_profit_price=trade.take_profit,
                target_distance_pct=(
                    abs(float(trade.take_profit) - entry) / entry if trade.take_profit else None
                ),
                liquidation_price=liq,
                distance_to_liquidation_pct=dist,
                gross_pnl=trade.gross_pnl,
                fees=trade.total_fees,
                spread_cost=trade.spread_cost,
                slippage=trade.slippage_cost,
                funding=trade.funding,
                net_pnl=trade.net_pnl,
                maximum_possible_loss=float(det["maximum_possible_loss"]),
                risk_budget=MAX_SINGLE_TRADE_NET_LOSS,
                risk_budget_breached=float(det["maximum_possible_loss"]) > MAX_SINGLE_TRADE_NET_LOSS,
                exit_status=trade.exit_status,
                defects=list(det["defects"]),
                sizing_mode="LEGACY_QTY1",
            )
        )

    # Classify simulator result
    mean_notional = statistics.fmean(r.notional for r in rows) if rows else 0.0
    has_size = invalid_size > 0 or (rows and mean_notional > MARGIN_PER_TRADE_CAP * FIXED_LEVERAGE * 2)
    # Legacy path had no liquidation gate at all (defect class even if stop happened to be inside).
    has_liq_model_missing = True
    has_liq = liq_breach > 0 or has_liq_model_missing
    has_pnl = False  # fees on notional only — accounting form OK if qty wrong
    if has_size and has_liq:
        result = "MULTIPLE_SIMULATION_DEFECTS"
    elif has_size:
        result = "SIMULATOR_POSITION_SIZING_BUG"
    elif has_liq:
        result = "SIMULATOR_LIQUIDATION_MODEL_MISSING"
    elif has_pnl:
        result = "SIMULATOR_PNL_ACCOUNTING_BUG"
    else:
        result = "SIMULATOR_RISK_MODEL_VALID"

    return {
        "simulator_risk_model_result": result,
        "invalid_position_size_trade_count": invalid_size,
        "risk_budget_breach_count": risk_breach,
        "liquidation_boundary_breach_count": liq_breach,
        "pnl_accounting_error_count": pnl_err,
        "legacy_trade_count": len(rows),
        "legacy_mean_notional": (statistics.fmean(r.notional for r in rows) if rows else None),
        "legacy_mean_max_loss": (statistics.fmean(r.maximum_possible_loss for r in rows) if rows else None),
        "desired_notional": MARGIN_PER_TRADE_CAP * FIXED_LEVERAGE,
        "risk_budget": MAX_SINGLE_TRADE_NET_LOSS,
        "margin_usdt": MARGIN_PER_TRADE_CAP,
        "leverage": FIXED_LEVERAGE,
        "margin_mode": MARGIN_MODE,
        "session_loss_limit_audit": AUDIT_SESSION_NET_LOSS_LIMIT,
        "sample_rows": [r.to_dict() for r in rows[:5]],
        "note": "Legacy market_event_sim defaulted qty=1.0 (whole-coin), ignoring 20U*25x and 3U risk cap; no liquidation gate.",
    }


def _cohort_bucket(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(key) or "UNKNOWN")].append(r)
    out: dict[str, Any] = {}
    for k, items in groups.items():
        nets = [float(x["net_pnl"]) for x in items if x.get("net_pnl") is not None]
        gross = [float(x["gross_pnl"]) for x in items if x.get("gross_pnl") is not None]
        wins = [n for n in nets if n > 0]
        losses = [n for n in nets if n <= 0]
        gw = sum(wins) if wins else 0.0
        gl = abs(sum(losses)) if losses else 0.0
        eq = 0.0
        peak = 0.0
        mdd = 0.0
        for n in nets:
            eq += n
            peak = max(peak, eq)
            mdd = min(mdd, eq - peak)
        out[k] = {
            "filled_trade_count": len(items),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(nets)) if nets else None,
            "gross_pnl": round(sum(gross), 8) if gross else None,
            "net_pnl": round(sum(nets), 8) if nets else None,
            "profit_factor": (round(gw / gl, 6) if gl > 0 else None),
            "expectancy": (statistics.fmean(nets) if nets else None),
            "maximum_drawdown": round(mdd, 8) if nets else None,
            "fees": round(sum(float(x.get("fees") or 0) for x in items), 8),
            "slippage": round(sum(float(x.get("slippage") or 0) for x in items), 8),
            "funding": round(sum(float(x.get("funding") or 0) for x in items), 8),
        }
    return out


def run_recalculated_pipeline(
    datasets: list[MarketDataset],
    *,
    min_sample: int = 30,
) -> dict[str, Any]:
    """Rebuild candidates, audit legacy defects, recalculate with risk sizing + attribution."""
    all_pairs: list[tuple[MarketCandidate, list[Candle]]] = []
    for ds in datasets:
        cands = build_candidates_from_dataset(ds, qty=1.0)  # evidence qty overwritten later
        by_ts = {c.ts_ms: i for i, c in enumerate(ds.candles)}
        for cand in cands:
            idx = by_ts.get(cand.candidate_snapshot_time)
            if idx is None:
                continue
            all_pairs.append((cand, ds.candles[idx + 1 :]))
    all_pairs.sort(key=lambda x: x[0].candidate_snapshot_time)

    legacy_audit = audit_legacy_qty1_trades(all_pairs)

    # Recalculate with risk sizing across cost modes on chronological folds
    n = len(all_pairs)
    i40, i55, i70, i85 = int(n * 0.40), int(n * 0.55), int(n * 0.70), int(n * 0.85)
    val_pairs = all_pairs[i40:i55]
    # Consumed failed OOS = previous holdout region [i85:) — mark consumed, do NOT use as proof
    consumed_pairs = all_pairs[i85:]
    # New validation-only recalculation uses train/val/test folds excluding claiming consumed as validated
    test_pairs = all_pairs[i55:i70]

    def _run_pairs(pairs: list[tuple[MarketCandidate, list[Candle]]], *, cost_mode: str, apply_costs: bool) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for cand, sub in pairs:
            # fresh qty each time
            c = MarketCandidate(
                symbol=cand.symbol,
                side=cand.side,
                strategy=cand.strategy,
                regime=cand.regime,
                candidate_snapshot_time=cand.candidate_snapshot_time,
                last_input_candle_time=cand.last_input_candle_time,
                entry_price=cand.entry_price,
                evidence=deepcopy(cand.evidence),
                future_data_reference_count=0,
                look_ahead_contamination=False,
            )
            c.evidence.qty = None
            trade, meta = simulate_with_risk_sizing(
                candidate=c, subsequent=sub, cost_mode=cost_mode, apply_costs=apply_costs
            )
            if meta and meta.block_reason not in {"", "OK"} and trade.entry_status != "ENTRY_FILLED":
                out.append(
                    {
                        "symbol": c.symbol,
                        "side": c.side,
                        "regime": c.regime,
                        "strategy": c.strategy,
                        "entry_status": trade.entry_status,
                        "block_reason": meta.block_reason,
                        "net_pnl": None,
                        "gross_pnl": None,
                        "fees": None,
                        "slippage": None,
                        "funding": None,
                        "exit_status": None,
                    }
                )
                continue
            if trade.entry_status != "ENTRY_FILLED":
                out.append(
                    {
                        "symbol": c.symbol,
                        "side": c.side,
                        "regime": c.regime,
                        "strategy": c.strategy,
                        "entry_status": trade.entry_status,
                        "block_reason": None,
                        "net_pnl": None,
                        "gross_pnl": None,
                        "fees": None,
                        "slippage": None,
                        "funding": None,
                        "exit_status": trade.exit_status,
                    }
                )
                continue
            # MFE/MAE on path after fill
            # Find fill index approximately: first bar touching entry
            fill_i = 0
            for j, bar in enumerate(sub):
                if bar.low <= float(trade.entry_price or c.entry_price) <= bar.high:
                    fill_i = j
                    break
            hold_bars: list[Candle] = []
            for bar in sub[fill_i + 1 :]:
                hold_bars.append(bar)
                if trade.exit_ts is not None and bar.ts_ms >= int(trade.exit_ts):
                    break
                if len(hold_bars) >= 48:
                    break
            mfe = compute_mfe_mae(
                side=c.side,
                entry_price=float(trade.entry_price or c.entry_price),
                stop=float(trade.stop or 0),
                subsequent_after_fill=hold_bars,
            )
            sized = meta.sized if meta else None
            out.append(
                {
                    "symbol": c.symbol,
                    "side": c.side,
                    "regime": c.regime,
                    "strategy": c.strategy,
                    "entry_status": trade.entry_status,
                    "exit_status": trade.exit_status,
                    "entry_price": trade.entry_price,
                    "quantity": trade.qty,
                    "notional": (float(trade.qty) * float(trade.entry_price or 0)),
                    "margin": MARGIN_PER_TRADE_CAP,
                    "leverage": FIXED_LEVERAGE,
                    "stop_price": trade.stop,
                    "take_profit_price": trade.take_profit,
                    "liquidation_price": getattr(sized, "liquidation_price", None),
                    "gross_pnl": trade.gross_pnl,
                    "fees": trade.total_fees,
                    "spread_cost": trade.spread_cost,
                    "slippage": trade.slippage_cost,
                    "funding": trade.funding,
                    "net_pnl": trade.net_pnl,
                    "maximum_possible_loss": getattr(sized, "maximum_possible_loss", None),
                    "risk_budget": MAX_SINGLE_TRADE_NET_LOSS,
                    "risk_budget_breached": bool(
                        getattr(sized, "maximum_possible_loss", 0) > MAX_SINGLE_TRADE_NET_LOSS
                    ),
                    **mfe,
                }
            )
        return out

    cost_versions = {
        "GROSS_NO_COST_DIAGNOSTIC": _run_pairs(test_pairs + consumed_pairs, cost_mode="BASE_CONSERVATIVE", apply_costs=False),
        "BASE_CONSERVATIVE_COST": _run_pairs(test_pairs + consumed_pairs, cost_mode="BASE_CONSERVATIVE", apply_costs=True),
        "OBSERVED_COST": _run_pairs(test_pairs + consumed_pairs, cost_mode="OBSERVED_COST", apply_costs=True),
        "ADVERSE_COST_STRESS": _run_pairs(test_pairs + consumed_pairs, cost_mode="ADVERSE_COST_STRESS", apply_costs=True),
    }

    def _summ(rows: list[dict[str, Any]]) -> dict[str, Any]:
        completed = [
            r
            for r in rows
            if r.get("net_pnl") is not None
            and r.get("exit_status")
            in {"STOP_LOSS", "TAKE_PROFIT", "TIME_STOP", "TRAILING_EXIT", "BREAK_EVEN_EXIT", "EARLY_EXIT"}
        ]
        nets = [float(r["net_pnl"]) for r in completed]
        gross = [float(r["gross_pnl"]) for r in completed if r.get("gross_pnl") is not None]
        wins = [n for n in nets if n > 0]
        losses = [n for n in nets if n <= 0]
        gw, gl = sum(wins), abs(sum(losses)) if losses else 0.0
        g_wins = [n for n in gross if n > 0]
        g_losses = [n for n in gross if n <= 0]
        ggw, ggl = sum(g_wins), abs(sum(g_losses)) if g_losses else 0.0
        eq = peak = mdd = 0.0
        for n in nets:
            eq += n
            peak = max(peak, eq)
            mdd = min(mdd, eq - peak)
        return {
            "simulated_trade_count": len(completed),
            "gross_pnl": round(sum(gross), 8) if gross else None,
            "gross_profit_factor": (round(ggw / ggl, 6) if ggl > 0 else None),
            "gross_expectancy": (statistics.fmean(gross) if gross else None),
            "net_pnl": round(sum(nets), 8) if nets else None,
            "profit_factor": (round(gw / gl, 6) if gl > 0 else None),
            "expectancy": (statistics.fmean(nets) if nets else None),
            "win_rate": (len(wins) / len(completed)) if completed else None,
            "maximum_drawdown": round(mdd, 8) if nets else None,
        }

    cost_summary = {k: _summ(v) for k, v in cost_versions.items()}
    gross_s = cost_summary["GROSS_NO_COST_DIAGNOSTIC"]
    net_s = cost_summary["BASE_CONSERVATIVE_COST"]
    g_pf = gross_s.get("gross_profit_factor")
    if g_pf is None:
        g_pf = gross_s.get("profit_factor")  # gross path: net==gross
    g_exp = gross_s.get("gross_expectancy")
    if g_exp is None:
        g_exp = gross_s.get("expectancy")
    if (g_pf is None or float(g_pf) <= 1) and (g_exp is None or float(g_exp) <= 0):
        gross_edge = "NO_GROSS_EDGE"
    elif float(g_pf or 0) > 1 and (net_s.get("profit_factor") or 0) < 1:
        gross_edge = "GROSS_EDGE_DESTROYED_BY_COST"
    elif (cost_summary["ADVERSE_COST_STRESS"].get("profit_factor") or 0) < 1 and float(g_pf or 0) > 1:
        gross_edge = "EDGE_UNSTABLE_UNDER_COST_STRESS"
    else:
        gross_edge = "NO_GROSS_EDGE"

    # Recalculated WF (validation fold) and consumed-OOS diagnostic (not proof)
    wf_rows = _run_pairs(val_pairs, cost_mode="BASE_CONSERVATIVE", apply_costs=True)
    oos_rows = _run_pairs(consumed_pairs, cost_mode="BASE_CONSERVATIVE", apply_costs=True)
    wf_s = _summ(wf_rows)
    oos_s = _summ(oos_rows)
    # Consumed holdout cannot become VALIDATED
    oos_status = "OOS_PERFORMANCE_FAILED"
    if (oos_s.get("simulated_trade_count") or 0) < min_sample:
        oos_status = "OOS_INSUFFICIENT_SAMPLE"
    elif oos_s.get("net_pnl") is not None and float(oos_s["net_pnl"]) > 0 and float(oos_s.get("profit_factor") or 0) > 1:
        # Still cannot validate on consumed holdout
        oos_status = "OOS_PERFORMANCE_FAILED"
        oos_s["note"] = "Positive metrics on CONSUMED_FAILED_HOLDOUT cannot become OOS_PERFORMANCE_VALIDATED"

    filled = [r for r in oos_rows if r.get("net_pnl") is not None]
    # Entry quality
    n_filled = len(filled) or 1
    entry_quality = {
        "pct_immediate_adverse": sum(1 for r in filled if float(r.get("mae") or 0) > 0 and float(r.get("mfe") or 0) <= 0) / n_filled,
        "pct_reach_0_5R_before_stop": sum(1 for r in filled if r.get("reached_0_5R")) / n_filled,
        "pct_reach_1R_before_stop": sum(1 for r in filled if r.get("reached_1R")) / n_filled,
        "pct_stopped_before_favorable": sum(1 for r in filled if r.get("stopped_before_favorable")) / n_filled,
        "pct_positive_mfe_negative_pnl": sum(
            1 for r in filled if float(r.get("mfe") or 0) > 0 and float(r.get("net_pnl") or 0) < 0
        )
        / n_filled,
    }
    # Primary failure classification — cost vs entry/exit precedence per Founder §5–7
    if gross_edge == "GROSS_EDGE_DESTROYED_BY_COST":
        primary_failure = "COST_DOMINATED_CHURN"
    elif entry_quality["pct_stopped_before_favorable"] > 0.5:
        primary_failure = "ENTRY_SELECTION_FAILURE"
    elif entry_quality["pct_positive_mfe_negative_pnl"] > 0.4:
        primary_failure = "EXIT_MANAGEMENT_FAILURE"
    elif gross_edge == "NO_GROSS_EDGE":
        primary_failure = "MULTIPLE_STRATEGY_FAILURES"
    else:
        primary_failure = "MULTIPLE_STRATEGY_FAILURES"

    loss_by_symbol = _cohort_bucket(filled, "symbol")
    loss_by_regime = _cohort_bucket(filled, "regime")
    loss_by_strategy = _cohort_bucket(filled, "strategy")
    loss_by_side = _cohort_bucket(filled, "side")
    loss_by_exit = _cohort_bucket(filled, "exit_status")

    # Recommendation: forensic only if recalculated still violates risk scale.
    recalc_breach = sum(1 for r in filled if float(r.get("net_pnl") or 0) < -MAX_SINGLE_TRADE_NET_LOSS * 5)
    if recalc_breach > max(3, int(0.1 * max(len(filled), 1))):
        recommendation = "NEXUS_SIMULATOR_FORENSIC_REQUIRED"
    elif gross_edge != "NO_GROSS_EDGE" and (wf_s.get("profit_factor") or 0) > 1 and (wf_s.get("expectancy") or 0) > 0:
        recommendation = "NEXUS_NEW_WALK_FORWARD_READY"
    else:
        recommendation = "NEXUS_STRATEGY_EDGE_RESEARCH_REQUIRED"

    return {
        "oos_cohort_status": CONSUMED_STATUS,
        "oos_cohort_id": CONSUMED_OOS_ID,
        "simulator_risk_model_result": legacy_audit["simulator_risk_model_result"],
        "legacy_audit": legacy_audit,
        "invalid_position_size_trade_count": legacy_audit["invalid_position_size_trade_count"],
        "risk_budget_breach_count": legacy_audit["risk_budget_breach_count"],
        "liquidation_boundary_breach_count": legacy_audit["liquidation_boundary_breach_count"],
        "pnl_accounting_error_count": legacy_audit["pnl_accounting_error_count"],
        "recalculated_wf": wf_s,
        "recalculated_oos_diagnostic_on_consumed_holdout": {**oos_s, "oos_status": oos_status, "not_proof": True},
        "recalculated_oos_status": oos_status,
        "cost_versions": cost_summary,
        "gross_edge_classification": gross_edge,
        "primary_failure_classification": primary_failure,
        "entry_quality": entry_quality,
        "loss_by_symbol": loss_by_symbol,
        "loss_by_regime": loss_by_regime,
        "loss_by_strategy": loss_by_strategy,
        "loss_by_side": loss_by_side,
        "loss_by_exit_reason": loss_by_exit,
        "consumed_oos_reuse_forbidden": True,
        "new_oos_required_for_validation": True,
        "risk_review_packet_ready": False,
        "shadow_status": "NOT_APPLIED",
        "qualification_complete": False,
        "recommendation": recommendation,
        "floors_unchanged": True,
        "margin_usdt": MARGIN_PER_TRADE_CAP,
        "leverage": FIXED_LEVERAGE,
        "margin_mode": MARGIN_MODE,
        "max_single_trade_net_loss": MAX_SINGLE_TRADE_NET_LOSS,
    }
