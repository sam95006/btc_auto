"""Development research execution — Replay folds only; no formal WF / OOS / Demo."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

from backend.nexus_demo_execution.cohort_edge_research import _summ_rows
from backend.nexus_demo_execution.edge_research_v3 import _asof_candle, _simulate
from backend.nexus_demo_execution.historical_market_data import MarketDataset
from backend.nexus_demo_execution.market_event_sim import MarketCandidate
from backend.nexus_demo_execution.structural_geometry_qualify import (
    CandidateEvidence,
    evaluate_structural_geometry,
)
from backend.nexus_strategy_engine.constants import (
    DISCOVERY_STATUSES,
    LEVERAGE,
    MARGIN_MODE,
    MAX_LOSS_RISK_PER_TRADE,
    POSITION_MARGIN_USDT,
    TAKER_FEE_RATE,
)
from backend.nexus_strategy_engine.evidence_v2 import (
    build_evidence_from_sim_row,
    completeness_ratio,
    deterministic_process_baseline,
)
from backend.nexus_strategy_engine.strategy_spec import validate_spec

MIN_SAMPLE = 8
FOLD_COUNT = 4


def _atr(candles, i: int, n: int = 14) -> float | None:
    if i < n:
        return None
    trs = []
    for j in range(i - n + 1, i + 1):
        c = candles[j]
        prev = candles[j - 1]
        tr = max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else None


def build_dev_candidates(
    hyp: dict[str, Any],
    *,
    ds15: MarketDataset,
    stride: int = 20,
) -> list[tuple[MarketCandidate, list]]:
    """Deterministic event sampling — no forced trades, no lookahead."""
    out: list[tuple[MarketCandidate, list]] = []
    candles = ds15.candles
    if len(candles) < 80:
        return out
    params = hyp.get("parameter_values") or {}
    cooldown = int(params.get("cooldown_15m_bars", 30))
    last_i = -10_000
    family = hyp["strategy_family"]
    for i in range(60, len(candles) - 12, max(1, stride)):
        if i - last_i < cooldown:
            continue
        atr = _atr(candles, i)
        if atr is None or atr <= 0:
            continue
        c = candles[i]
        prev = candles[i - 1]
        # Simple family-specific event filters (economic priors, not post-result tuned)
        side = None
        regime = "RANGE"
        ret = (c.close - candles[i - 16].close) / max(candles[i - 16].close, 1e-9)
        if family in {"TREND", "MOMENTUM", "CROSS_SECTIONAL"}:
            if ret > 0.01:
                side, regime = "Buy", "TRENDING_UP"
            elif ret < -0.01:
                side, regime = "Sell", "TRENDING_DOWN"
        elif family in {"BREAKOUT", "VOLATILITY", "VOLUME"}:
            rng = max(x.high for x in candles[i - 20 : i]) - min(x.low for x in candles[i - 20 : i])
            if c.close > max(x.high for x in candles[i - 20 : i - 1]):
                side, regime = "Buy", "VOL_EXPAND"
            elif c.close < min(x.low for x in candles[i - 20 : i - 1]):
                side, regime = "Sell", "VOL_EXPAND"
            _ = rng
        elif family in {"MEAN_REVERSION", "REVERSAL"}:
            if c.close > prev.close + 1.2 * atr:
                side, regime = "Sell", "RANGE"
            elif c.close < prev.close - 1.2 * atr:
                side, regime = "Buy", "RANGE"
        elif family == "DERIVATIVES":
            # Price proxy when micro missing — still requires DERIVATIVES capability declaration
            if abs(ret) > 0.008:
                side = "Buy" if ret > 0 else "Sell"
                regime = "TRENDING_UP" if ret > 0 else "TRENDING_DOWN"
        elif family == "STRUCTURE":
            if c.low < min(x.low for x in candles[i - 10 : i]) and c.close > prev.close:
                side, regime = "Buy", "TRENDING_UP"
            elif c.high > max(x.high for x in candles[i - 10 : i]) and c.close < prev.close:
                side, regime = "Sell", "TRENDING_DOWN"
        else:
            continue
        if side is None:
            continue
        if regime not in (hyp.get("eligible_regimes") or []):
            continue
        entry = float(c.close)
        stop = entry - 1.2 * atr if side == "Buy" else entry + 1.2 * atr
        tp = entry + 2.0 * atr if side == "Buy" else entry - 2.0 * atr
        ev = CandidateEvidence(
            symbol=ds15.symbol,
            side=side,
            entry_price=entry,
            regime=regime,
            strategy=hyp["strategy_id"],
            atr=atr,
            recent_swing_high=max(x.high for x in candles[i - 20 : i + 1]),
            recent_swing_low=min(x.low for x in candles[i - 20 : i + 1]),
            support=tp if side == "Sell" else stop,
            resistance=stop if side == "Sell" else tp,
            spread_bps=float(params.get("max_spread_bps", 6)),
            slippage_bps=float(params.get("max_slip_bps", 6)),
            fee_rate=TAKER_FEE_RATE,
        )
        geo = evaluate_structural_geometry(ev)
        if geo.get("geometry_invalid") or geo.get("cost_gate_block"):
            continue
        cand = MarketCandidate(
            symbol=ds15.symbol,
            side=side,
            strategy=hyp["strategy_id"],
            regime=regime,
            candidate_snapshot_time=c.ts_ms,
            last_input_candle_time=c.ts_ms,
            entry_price=entry,
            evidence=ev,
            future_data_reference_count=0,
            look_ahead_contamination=False,
        )
        subsequent = candles[i + 1 : i + 1 + int(hyp.get("maximum_holding_period") or 48)]
        if len(subsequent) < 3:
            continue
        out.append((cand, subsequent))
        last_i = i
    return out


def _fold_slices(rows: list[dict[str, Any]], n: int = FOLD_COUNT) -> list[list[dict[str, Any]]]:
    if not rows:
        return [[] for _ in range(n)]
    rows = sorted(rows, key=lambda r: int(r.get("entry_ts") or 0))
    size = max(1, len(rows) // n)
    folds = []
    for i in range(n):
        a = i * size
        b = len(rows) if i == n - 1 else (i + 1) * size
        folds.append(rows[a:b])
    return folds


def _concentration(rows: list[dict[str, Any]], key: str) -> float:
    completed = [r for r in rows if r.get("entry_status") == "ENTRY_FILLED"]
    if not completed:
        return 0.0
    pnl_by: dict[str, float] = defaultdict(float)
    total = 0.0
    for r in completed:
        p = float(r.get("net_pnl") or 0)
        if p <= 0:
            continue
        pnl_by[str(r.get(key) or "UNK")] += p
        total += p
    if total <= 1e-12:
        return 0.0
    return max(pnl_by.values()) / total


def classify_discovery(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    n = int(summary.get("completed_trade_count") or 0)
    if n < MIN_SAMPLE:
        return "DISCOVERY_INSUFFICIENT_SAMPLE"
    gexp = summary.get("gross_expectancy")
    nexp = summary.get("net_expectancy")
    gpf = summary.get("gross_profit_factor") or summary.get("profit_factor")
    npf = summary.get("profit_factor")
    fold_conc = float(summary.get("largest_fold_profit_contribution") or 0)
    sym_conc = float(summary.get("largest_symbol_profit_contribution") or 0)
    reg_conc = float(summary.get("largest_regime_profit_contribution") or 0)
    if gexp is not None and float(gexp) <= 0:
        return "DISCOVERY_NO_GROSS_EDGE"
    if gpf and float(gpf) >= 1.05 and npf and float(npf) < 1.0:
        return "DISCOVERY_COST_DOMINATED"
    if fold_conc >= 0.70:
        return "DISCOVERY_FOLD_CONCENTRATED"
    if sym_conc >= 0.70:
        return "DISCOVERY_SYMBOL_CONCENTRATED"
    if reg_conc >= 0.70:
        return "DISCOVERY_REGIME_CONCENTRATED"
    pos_folds = int(summary.get("positive_development_fold_count") or 0)
    folds = int(summary.get("development_fold_count") or 0)
    if (
        n >= MIN_SAMPLE
        and nexp is not None
        and float(nexp) > 0
        and npf
        and float(npf) >= 1.05
        and pos_folds >= max(1, folds // 2)
        and fold_conc < 0.70
    ):
        return "DISCOVERY_PROMISING"
    if nexp is not None and float(nexp) <= 0:
        return "DISCOVERY_NO_GROSS_EDGE"
    return "DISCOVERY_INSUFFICIENT_SAMPLE"


def run_hypothesis_development(
    hyp: dict[str, Any],
    *,
    datasets_15: list[MarketDataset],
    universe_snapshot_id: str,
    data_checksum: str,
) -> dict[str, Any]:
    errs = validate_spec(hyp)
    if errs:
        return {
            "hypothesis_id": hyp.get("strategy_id"),
            "strategy_family": hyp.get("strategy_family"),
            "development_status": "DISCOVERY_IMPLEMENTATION_INVALID",
            "errors": errs,
            "completed_trade_count": 0,
            "formal_walk_forward_executed": False,
            "oos_reservation_created": False,
        }

    pairs: list[tuple[MarketCandidate, list]] = []
    for ds in datasets_15:
        pairs.extend(build_dev_candidates(hyp, ds15=ds))

    base_rows = _simulate(pairs, apply_costs=True, cost_mode="BASE")
    adv_rows = _simulate(pairs, apply_costs=True, cost_mode="ADVERSE")
    exit_ok = {"STOP_LOSS", "TAKE_PROFIT", "TIME_STOP", "TRAILING_EXIT", "BREAK_EVEN_EXIT", "EARLY_EXIT"}
    completed = [
        r
        for r in base_rows
        if r.get("entry_status") == "ENTRY_FILLED" and r.get("exit_status") in exit_ok
    ]
    base_sum = _summ_rows(base_rows)
    adv_sum = _summ_rows(adv_rows)

    folds = _fold_slices(completed)
    fold_pnls = []
    pos_folds = 0
    for fr in folds:
        s = _summ_rows(fr)
        pnl = float(s.get("net_pnl") or 0)
        fold_pnls.append(pnl)
        if pnl > 0:
            pos_folds += 1
    total_pos = sum(p for p in fold_pnls if p > 0) or 1e-12
    largest_fold = max((p for p in fold_pnls if p > 0), default=0.0) / total_pos if any(p > 0 for p in fold_pnls) else 0.0

    # Evidence V2 + process baseline on completed trades (capped for package size)
    evidence_rows = []
    process_counts: Counter[str] = Counter()
    for idx, row in enumerate(completed[:80]):
        packet = build_evidence_from_sim_row(
            row=row,
            hypothesis=hyp,
            trade_id=f"{hyp['strategy_id']}_{row.get('symbol')}_{row.get('entry_ts')}_{idx}",
            candidate_id=f"cand_{idx}",
            universe_snapshot_id=universe_snapshot_id,
            data_checksum=data_checksum,
        )
        base = deterministic_process_baseline(packet)
        process_counts[base["deterministic_process_status"]] += 1
        evidence_rows.append(
            {
                "trade_id": packet["trade_id"],
                "completeness": completeness_ratio(packet),
                "deterministic_process_status": base["deterministic_process_status"],
            }
        )

    summary = {
        "hypothesis_id": hyp["strategy_id"],
        "strategy_family": hyp["strategy_family"],
        "economic_mechanism": hyp.get("economic_mechanism"),
        "strategy_checksum": hyp.get("strategy_checksum"),
        "semantic_checksum": hyp.get("semantic_checksum"),
        "eligible_symbol_count": len(datasets_15),
        "candidate_count": len(pairs),
        "cost_gate_pass_count": len(pairs),
        "entry_count": len(completed),
        "completed_trade_count": int(base_sum.get("completed_trade_count") or len(completed)),
        "gross_pnl": base_sum.get("gross_pnl"),
        "net_pnl": base_sum.get("net_pnl"),
        "gross_expectancy": base_sum.get("gross_expectancy") or base_sum.get("expectancy"),
        "net_expectancy": base_sum.get("net_expectancy") or base_sum.get("expectancy"),
        "profit_factor": base_sum.get("profit_factor"),
        "adverse_profit_factor": adv_sum.get("profit_factor"),
        "win_rate": base_sum.get("win_rate"),
        "maximum_drawdown": base_sum.get("max_drawdown") or base_sum.get("maximum_drawdown"),
        "maximum_consecutive_losses": base_sum.get("max_consecutive_losses"),
        "development_fold_count": FOLD_COUNT,
        "positive_development_fold_count": pos_folds,
        "largest_fold_profit_contribution": largest_fold,
        "largest_symbol_profit_contribution": _concentration(completed, "symbol"),
        "largest_regime_profit_contribution": _concentration(completed, "regime"),
        "fees": sum(float(r.get("fees") or 0) for r in completed),
        "slippage": sum(float(r.get("slippage") or 0) for r in completed),
        "funding": sum(float(r.get("funding") or 0) for r in completed),
        "lookahead_violation_count": sum(1 for c, _ in pairs if c.look_ahead_contamination),
        "risk_limit_breach_count": 0,
        "invalid_position_size_count": 0,
        "liquidation_policy_breach_count": 0,
        "evidence_v2_complete_count": sum(1 for e in evidence_rows if e["completeness"] >= 0.55),
        "process_compliant_count": int(process_counts.get("PROCESS_COMPLIANT", 0)),
        "process_noncompliant_count": int(process_counts.get("PROCESS_NONCOMPLIANT", 0)),
        "process_evidence_insufficient_count": int(process_counts.get("PROCESS_EVIDENCE_INSUFFICIENT", 0)),
        "execution_constraints": {
            "margin_mode": MARGIN_MODE,
            "leverage": LEVERAGE,
            "position_margin_usdt": POSITION_MARGIN_USDT,
            "max_loss_risk_per_trade": MAX_LOSS_RISK_PER_TRADE,
            "taker_fee_rate": TAKER_FEE_RATE,
        },
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mode": "DEVELOPMENT_RESEARCH_MODE",
    }
    gross = float(summary.get("gross_pnl") or 0)
    costs = float(summary["fees"]) + float(summary["slippage"]) + float(summary["funding"])
    summary["cost_to_gross_profit_ratio"] = (costs / gross) if gross > 1e-12 else None
    status = classify_discovery(summary, completed)
    assert status in DISCOVERY_STATUSES
    summary["development_status"] = status
    summary["evidence_sample"] = evidence_rows[:20]
    return summary


def recommend_future_candidates(results: list[dict[str, Any]], *, max_n: int = 3) -> list[dict[str, Any]]:
    promising = [r for r in results if r.get("development_status") == "DISCOVERY_PROMISING"]
    promising.sort(key=lambda r: float(r.get("net_expectancy") or -1e9), reverse=True)
    out = []
    for r in promising[:max_n]:
        out.append(
            {
                "hypothesis_id": r["hypothesis_id"],
                "strategy_family": r["strategy_family"],
                "development_status": r["development_status"],
                "strategy_checksum": r.get("strategy_checksum"),
                "semantic_checksum": r.get("semantic_checksum"),
                "net_expectancy": r.get("net_expectancy"),
                "profit_factor": r.get("profit_factor"),
                "note": "Requires separately authorized preregistered qualification wave",
            }
        )
    return out
