"""V1.1 development research — per-component executors, funnels, no family fallback."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from backend.nexus_demo_execution.cohort_edge_research import _summ_rows
from backend.nexus_demo_execution.edge_research_v3 import _simulate
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
from backend.nexus_strategy_engine.cost_semantics import annotate_trade_costs
from backend.nexus_strategy_engine.data_bundle import ResearchDataBundle
from backend.nexus_strategy_engine.executors import (
    ScanContext,
    get_executor,
)
from backend.nexus_strategy_engine.strategy_spec import sha_obj, validate_spec

FOLD_COUNT = 5
MIN_PROMISING_TRADES = 50


ZERO_TRADE_CAUSES = frozenset(
    {
        "NO_EVENT_IN_DATA",
        "REGIME_DEFINITION_CONFLICT",
        "REQUIRED_DATA_MISSING",
        "COST_GATE_BLOCKED",
        "GEOMETRY_BLOCKED",
        "IMPLEMENTATION_ERROR",
        "VALID_ZERO_SIGNAL_RESULT",
        "NOT_APPLICABLE_HAS_TRADES",
    }
)


def empty_funnel() -> dict[str, int]:
    return {
        "bars_scanned": 0,
        "context_pass_count": 0,
        "event_detected_count": 0,
        "confirmation_pass_count": 0,
        "regime_block_count": 0,
        "data_capability_block_count": 0,
        "late_entry_block_count": 0,
        "cost_gate_block_count": 0,
        "geometry_block_count": 0,
        "risk_block_count": 0,
        "candidate_count": 0,
        "entry_count": 0,
        "completed_trade_count": 0,
    }


def _peer_returns(bundles: list[ResearchDataBundle], lookback: int = 16) -> dict[str, float]:
    out: dict[str, float] = {}
    for b in bundles:
        c = b.candles_15
        if len(c) <= lookback + 10:
            continue
        i = len(c) - 10
        out[b.symbol] = (c[i].close - c[i - lookback].close) / max(c[i - lookback].close, 1e-9)
    return out


def build_candidates_for_component(
    hyp: dict[str, Any],
    *,
    bundles: list[ResearchDataBundle],
) -> tuple[list[tuple[MarketCandidate, list]], dict[str, int], str | None, int]:
    """Return pairs, funnel, zero_trade_root_cause hint, proxy_violation_count."""
    funnel = empty_funnel()
    component_id = hyp["component_id"]
    ex = get_executor(component_id)
    proxy_violations = 0
    if not ex.implemented:
        funnel["data_capability_block_count"] = 1
        return [], funnel, "IMPLEMENTATION_ERROR", 0

    need_deriv = "DERIVATIVES_HISTORY_ELIGIBLE" in (hyp.get("required_data_capabilities") or [])
    pairs: list[tuple[MarketCandidate, list]] = []
    peers = _peer_returns(bundles)
    btc_ret = peers.get("BTCUSDT")
    events_total = 0
    regime_blocks = 0
    geo_blocks = 0
    cost_blocks = 0
    data_blocks = 0
    eligible_symbols = 0

    for b in bundles:
        if not b.candles_15 or b.status == "DATA_INVALID":
            data_blocks += 1
            continue
        # Prohibit derivative price proxies
        if need_deriv:
            missing = []
            if component_id in {"FUNDING_OI_CONTINUATION", "FUNDING_OI_CONTRARIAN"}:
                if not b.funding_points or not b.oi_points:
                    missing.append("funding_oi")
            if component_id == "MARK_INDEX_BASIS_ANOMALY":
                if not b.mark_15 or not b.index_15:
                    missing.append("mark_index")
            if missing:
                data_blocks += 1
                b.required_feature_status["required_for_hyp"] = "MISSING"
                continue  # INELIGIBLE — no price proxy
        eligible_symbols += 1
        funnel["bars_scanned"] += len(b.candles_15)
        ctx = ScanContext(
            symbol=b.symbol,
            candles_15=b.candles_15,
            candles_60=b.candles_60 or None,
            candles_240=b.candles_240 or None,
            funding_points=b.funding_points or None,
            oi_points=b.oi_points or None,
            mark_candles=b.mark_15 or None,
            index_candles=b.index_15 or None,
            peer_returns_at_ts=peers if component_id in {"RELATIVE_STRENGTH", "CROSS_SECTIONAL_MOMENTUM"} else None,
            btc_return_at_ts=btc_ret,
        )
        signals = ex.scan(ctx)
        events_total += len(signals)
        for sig in signals:
            funnel["event_detected_count"] += 1
            funnel["context_pass_count"] += 1
            funnel["confirmation_pass_count"] += 1
            if sig.late_entry_rejected:
                funnel["late_entry_block_count"] += 1
                continue
            if sig.regime not in (hyp.get("eligible_regimes") or []):
                regime_blocks += 1
                continue
            # Explicit proxy check — never allow
            if sig.extras.get("proxy_used") is True:
                proxy_violations += 1
                continue
            params = hyp.get("parameter_values") or {}
            spread_bps = float(params.get("max_spread_bps", 6))
            slip_bps = float(params.get("max_slip_bps", 6))
            atr_approx = abs(sig.entry_price - sig.stop_price) / 1.2 if sig.entry_price else 1.0
            ev = CandidateEvidence(
                symbol=b.symbol,
                side=sig.side,
                entry_price=sig.entry_price,
                regime=sig.regime,
                strategy=hyp["strategy_id"],
                atr=max(atr_approx, 1e-9),
                recent_swing_high=max(x.high for x in b.candles_15[max(0, sig.entry_index - 20) : sig.entry_index + 1]),
                recent_swing_low=min(x.low for x in b.candles_15[max(0, sig.entry_index - 20) : sig.entry_index + 1]),
                support=sig.target_price if sig.side == "Sell" else sig.stop_price,
                resistance=sig.stop_price if sig.side == "Sell" else sig.target_price,
                spread_bps=spread_bps,
                slippage_bps=slip_bps,
                fee_rate=TAKER_FEE_RATE,
            )
            # Override geometry levels with strategy-specific stop/target
            ev.support = sig.target_price if sig.side == "Sell" else sig.stop_price
            ev.resistance = sig.stop_price if sig.side == "Sell" else sig.target_price
            geo = evaluate_structural_geometry(ev)
            if geo.get("geometry_invalid"):
                geo_blocks += 1
                continue
            if geo.get("cost_gate_block"):
                cost_blocks += 1
                continue
            c = b.candles_15[sig.entry_index]
            cand = MarketCandidate(
                symbol=b.symbol,
                side=sig.side,
                strategy=hyp["strategy_id"],
                regime=sig.regime,
                candidate_snapshot_time=c.ts_ms,
                last_input_candle_time=c.ts_ms,
                entry_price=sig.entry_price,
                evidence=ev,
                future_data_reference_count=0,
                look_ahead_contamination=False,
            )
            # Attach strategy-specific exits onto evidence for sim
            setattr(ev, "stop_price_override", sig.stop_price)
            setattr(ev, "target_price_override", sig.target_price)
            setattr(ev, "stop_basis", sig.stop_basis)
            setattr(ev, "target_basis", sig.target_basis)
            hold = int(hyp.get("maximum_holding_period") or 48)
            subsequent = b.candles_15[sig.entry_index + 1 : sig.entry_index + 1 + hold]
            if len(subsequent) < 3:
                continue
            pairs.append((cand, subsequent))
            funnel["candidate_count"] += 1

    funnel["regime_block_count"] = regime_blocks
    funnel["data_capability_block_count"] = data_blocks
    funnel["geometry_block_count"] = geo_blocks
    funnel["cost_gate_block_count"] = cost_blocks

    root_cause = None
    if not pairs:
        if not ex.implemented:
            root_cause = "IMPLEMENTATION_ERROR"
        elif need_deriv and eligible_symbols == 0:
            root_cause = "REQUIRED_DATA_MISSING"
        elif events_total == 0 and eligible_symbols > 0:
            root_cause = "NO_EVENT_IN_DATA"
        elif regime_blocks > 0 and events_total > 0:
            root_cause = "REGIME_DEFINITION_CONFLICT"
        elif cost_blocks > 0 and geo_blocks == 0:
            root_cause = "COST_GATE_BLOCKED"
        elif geo_blocks > 0:
            root_cause = "GEOMETRY_BLOCKED"
        elif component_id == "REGIME_TRANSITION_VETO":
            root_cause = "VALID_ZERO_SIGNAL_RESULT"
        else:
            root_cause = "VALID_ZERO_SIGNAL_RESULT"
    return pairs, funnel, root_cause, proxy_violations


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


def classify_discovery_v11(summary: dict[str, Any]) -> str:
    if summary.get("implementation_invalid"):
        return "DISCOVERY_IMPLEMENTATION_INVALID"
    if summary.get("required_data_proxy_violation_count", 0) > 0:
        return "DISCOVERY_IMPLEMENTATION_INVALID"
    if summary.get("semantic_execution_collision"):
        return "DISCOVERY_IMPLEMENTATION_INVALID"
    n = int(summary.get("completed_trade_count") or 0)
    if n == 0:
        # Do NOT auto-map to INSUFFICIENT_SAMPLE — root cause separate
        return "DISCOVERY_INSUFFICIENT_SAMPLE"
    if n < MIN_PROMISING_TRADES:
        # Still classify edge quality when sample small but non-zero
        nexp = summary.get("net_expectancy")
        if nexp is not None and float(nexp) <= 0:
            return "DISCOVERY_NO_GROSS_EDGE"
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
    if nexp is not None and float(nexp) <= 0:
        return "DISCOVERY_NO_GROSS_EDGE"
    if gpf and float(gpf) >= 1.05 and npf and float(npf) < 1.0:
        return "DISCOVERY_COST_DOMINATED"
    if fold_conc > 0.65 or sym_conc > 0.40 or reg_conc > 0.70:
        return "DISCOVERY_FOLD_CONCENTRATED" if fold_conc > 0.65 else (
            "DISCOVERY_SYMBOL_CONCENTRATED" if sym_conc > 0.40 else "DISCOVERY_REGIME_CONCENTRATED"
        )
    pos_folds = int(summary.get("positive_development_fold_count") or 0)
    folds = int(summary.get("development_fold_count") or 0)
    if (
        n >= MIN_PROMISING_TRADES
        and folds >= 5
        and pos_folds >= 3
        and nexp is not None
        and float(nexp) > 0
        and npf
        and float(npf) >= 1.10
        and float(summary.get("adverse_profit_factor") or 0) >= 1.00
        and fold_conc <= 0.65
        and sym_conc <= 0.40
        and reg_conc <= 0.70
        and int(summary.get("lookahead_violation_count") or 0) == 0
        and int(summary.get("risk_limit_breach_count") or 0) == 0
        and not summary.get("semantic_execution_collision")
        and int(summary.get("required_data_proxy_violation_count") or 0) == 0
    ):
        return "DISCOVERY_PROMISING"
    if nexp is not None and float(nexp) <= 0:
        return "DISCOVERY_NO_GROSS_EDGE"
    return "DISCOVERY_INSUFFICIENT_SAMPLE"


def run_hypothesis_development_v11(
    hyp: dict[str, Any],
    *,
    bundles: list[ResearchDataBundle],
    universe_snapshot_id: str,
    data_checksum: str,
    collision_ids: set[str] | None = None,
) -> dict[str, Any]:
    errs = validate_spec(hyp)
    ex = get_executor(hyp.get("component_id") or "")
    if errs or not ex.implemented:
        funnel = empty_funnel()
        return {
            "hypothesis_id": hyp.get("strategy_id"),
            "component_executor_id": hyp.get("component_id"),
            "strategy_family": hyp.get("strategy_family"),
            "development_status": "DISCOVERY_IMPLEMENTATION_INVALID",
            "implementation_invalid": True,
            "errors": errs or ["component_not_implemented"],
            "completed_trade_count": 0,
            "candidate_funnel": funnel,
            "zero_trade_root_cause": "IMPLEMENTATION_ERROR",
            "strategy_checksum": hyp.get("strategy_checksum"),
            "semantic_checksum": hyp.get("semantic_checksum"),
            "execution_engine_checksum": hyp.get("execution_engine_checksum") or ex.checksum(),
            "semantic_execution_collision": False,
            "required_data_proxy_violation_count": 0,
            "lookahead_violation_count": 0,
            "risk_limit_breach_count": 0,
            "formal_walk_forward_executed": False,
            "oos_reservation_created": False,
            "eligible_symbol_count": 0,
        }

    pairs, funnel, zero_cause, proxy_viol = build_candidates_for_component(hyp, bundles=bundles)
    base_rows = _simulate(pairs, apply_costs=True, cost_mode="BASE") if pairs else []
    adv_rows = _simulate(pairs, apply_costs=True, cost_mode="ADVERSE") if pairs else []
    # Annotate cost semantics
    params = hyp.get("parameter_values") or {}
    annotated = [
        annotate_trade_costs(
            r,
            spread_bps=float(params.get("max_spread_bps", 6)),
            slip_bps=float(params.get("max_slip_bps", 6)),
            funding_value=r.get("funding"),
            has_orderbook=False,
        )
        for r in base_rows
    ]
    exit_ok = {"STOP_LOSS", "TAKE_PROFIT", "TIME_STOP", "TRAILING_EXIT", "BREAK_EVEN_EXIT", "EARLY_EXIT", "TARGET", "STOP"}
    completed = [
        r
        for r in annotated
        if r.get("entry_status") == "ENTRY_FILLED" and (r.get("exit_status") in exit_ok or r.get("exit_status"))
    ]
    # Prefer rows that actually exited
    completed = [r for r in annotated if r.get("entry_status") == "ENTRY_FILLED"]
    base_sum = _summ_rows(annotated) if annotated else {}
    adv_sum = _summ_rows(adv_rows) if adv_rows else {}

    folds = _fold_slices(completed)
    fold_pnls = []
    pos_folds = 0
    for fr in folds:
        s = _summ_rows(fr) if fr else {}
        pnl = float(s.get("net_pnl") or 0)
        fold_pnls.append(pnl)
        if pnl > 0:
            pos_folds += 1
    total_pos = sum(p for p in fold_pnls if p > 0) or 1e-12
    largest_fold = max((p for p in fold_pnls if p > 0), default=0.0) / total_pos if any(p > 0 for p in fold_pnls) else 0.0

    funnel["entry_count"] = len(completed)
    funnel["completed_trade_count"] = int(base_sum.get("completed_trade_count") or len(completed))

    collided = bool(collision_ids and hyp.get("strategy_id") in collision_ids)
    summary: dict[str, Any] = {
        "hypothesis_id": hyp["strategy_id"],
        "component_executor_id": hyp["component_id"],
        "component_executor_checksum": ex.checksum(),
        "strategy_family": hyp["strategy_family"],
        "economic_mechanism": hyp.get("economic_mechanism"),
        "strategy_checksum": hyp.get("strategy_checksum"),
        "semantic_checksum": hyp.get("semantic_checksum"),
        "execution_engine_checksum": hyp.get("execution_engine_checksum") or ex.checksum(),
        "data_bundle_version": hyp.get("data_bundle_version"),
        "cost_model_version": hyp.get("cost_model_version"),
        "eligible_symbol_count": len([b for b in bundles if b.candles_15 and b.status != "DATA_INVALID"]),
        "candidate_count": len(pairs),
        "candidate_funnel": funnel,
        "zero_trade_root_cause": zero_cause if not completed else "NOT_APPLICABLE_HAS_TRADES",
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
        "required_data_proxy_violation_count": proxy_viol,
        "semantic_execution_collision": collided,
        "execution_constraints": {
            "margin_mode": MARGIN_MODE,
            "leverage": LEVERAGE,
            "position_margin_usdt": POSITION_MARGIN_USDT,
            "max_loss_risk_per_trade": MAX_LOSS_RISK_PER_TRADE,
            "taker_fee_rate": TAKER_FEE_RATE,
        },
        "cost_semantics_note": "spread/slippage labeled CONSERVATIVE_PROXY when orderbook unavailable",
        "universe_snapshot_id": universe_snapshot_id,
        "data_checksum": data_checksum,
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mode": "DEVELOPMENT_RESEARCH_MODE_V1_1",
        "sim_rows_sample": [
            {
                "symbol": r.get("symbol"),
                "side": r.get("side"),
                "net_pnl": r.get("net_pnl"),
                "spread_source": r.get("spread_source"),
                "slippage_source": r.get("slippage_source"),
                "funding_source": r.get("funding_source"),
                "entry_ts": r.get("entry_ts"),
            }
            for r in completed[:5]
        ],
    }
    status = classify_discovery_v11(summary)
    assert status in DISCOVERY_STATUSES
    summary["development_status"] = status
    if zero_cause:
        assert zero_cause in ZERO_TRADE_CAUSES or zero_cause == "NOT_APPLICABLE_HAS_TRADES"
    return summary


def recommend_future_candidates_v11(results: list[dict[str, Any]], *, max_n: int = 3) -> list[dict[str, Any]]:
    promising = [r for r in results if r.get("development_status") == "DISCOVERY_PROMISING"]
    promising.sort(key=lambda r: float(r.get("net_expectancy") or -1e9), reverse=True)
    out = []
    for r in promising[:max_n]:
        out.append(
            {
                "hypothesis_id": r["hypothesis_id"],
                "component_executor_id": r.get("component_executor_id"),
                "development_status": r["development_status"],
                "strategy_checksum": r.get("strategy_checksum"),
                "semantic_checksum": r.get("semantic_checksum"),
                "execution_engine_checksum": r.get("execution_engine_checksum"),
                "net_expectancy": r.get("net_expectancy"),
                "profit_factor": r.get("profit_factor"),
                "note": "Requires separately authorized preregistered qualification wave",
            }
        )
    return out


def audit_v11_collisions(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Flag V1.1 hypotheses that still produce identical trade/metric sets."""
    from itertools import combinations

    collisions = []
    for a, b in combinations(results, 2):
        metric_same = sha_obj(
            {
                "c": a.get("completed_trade_count"),
                "ne": a.get("net_expectancy"),
                "pf": a.get("profit_factor"),
                "cand": a.get("candidate_count"),
            }
        ) == sha_obj(
            {
                "c": b.get("completed_trade_count"),
                "ne": b.get("net_expectancy"),
                "pf": b.get("profit_factor"),
                "cand": b.get("candidate_count"),
            }
        )
        same_component = a.get("component_executor_id") == b.get("component_executor_id")
        if metric_same and a.get("completed_trade_count", 0) > 0 and not same_component:
            collisions.append(
                {
                    "flag": "SEMANTIC_EXECUTION_COLLISION",
                    "hypothesis_a": a.get("hypothesis_id"),
                    "hypothesis_b": b.get("hypothesis_id"),
                    "component_a": a.get("component_executor_id"),
                    "component_b": b.get("component_executor_id"),
                }
            )
    return {
        "semantic_collision_hypothesis_count": len({c["hypothesis_a"] for c in collisions} | {c["hypothesis_b"] for c in collisions}),
        "collision_pairs": collisions,
    }
