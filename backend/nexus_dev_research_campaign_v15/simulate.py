"""PIT simulation of mechanism candidates on development panels with full cost stack."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from backend.nexus_dev_research_campaign_v15.constants import (
    MIN_SAMPLE_OBSERVATIONS,
    MIN_SAMPLE_TRADES,
    REGIME_FRAGILITY_SHARE,
)
from backend.nexus_dev_research_campaign_v15.data import DevelopmentPanel
from backend.nexus_dev_research_campaign_v15.features import (
    attach_cross_asset,
    available_feature_set,
    enrich_symbol_bars,
    missing_required,
    signal_for_spec,
)
from backend.nexus_dev_research_campaign_v15.fdr import two_sided_sign_pvalue
from backend.nexus_mechanism_lab_v4.catalog import MechanismSpec, SPECS
from backend.nexus_strategy_discovery_factory_v3.cost_accounting import account_trade_costs


def build_feature_panel(panel: DevelopmentPanel) -> dict[str, list[dict[str, Any]]]:
    rows_by_symbol = {sym: enrich_symbol_bars(bars) for sym, bars in panel.bars_by_symbol.items()}
    attach_cross_asset(rows_by_symbol, panel.symbols)
    return rows_by_symbol


def _simulate_on_symbol(
    spec: MechanismSpec,
    rows: list[dict[str, Any]],
    *,
    qty: Decimal = Decimal("0.01"),
) -> dict[str, Any]:
    hold = max(1, int(spec.hold_bars))
    cooldown = max(2, int(spec.horizon_bars))
    trades: list[dict[str, Any]] = []
    last_i = -10_000
    dq_blocks = 0
    for i in range(24, len(rows) - hold - 1):
        if i - last_i < cooldown:
            continue
        row = rows[i]
        if not row.get("data_quality_ok", True):
            dq_blocks += 1
            continue
        prev = rows[i - 1] if i > 0 else None
        sig = signal_for_spec(spec, row, prev)
        if sig is None:
            continue
        entry = Decimal(str(row["mid"]))
        exit_row = rows[i + hold]
        exit_px = Decimal(str(exit_row["mid"]))
        side = "LONG" if sig > 0 else "SHORT"
        spread = Decimal(str(max(float(row.get("spread_bps_range_proxy") or 1.0), 0.5)))
        impact = Decimal("2.0")
        fund = row.get("funding_rate")
        fund_d = Decimal(str(fund)) if fund is not None else None
        costed = account_trade_costs(
            side=side,
            qty=qty,
            entry_price=entry,
            exit_price=exit_px,
            spread_bps=spread,
            impact_bps=impact,
            funding_rate=fund_d,
        )
        trades.append(
            {
                "entry_ts": row["ts_ms"],
                "exit_ts": exit_row["ts_ms"],
                "side": side,
                "symbol": row["symbol"],
                "regime": row.get("regime"),
                "gross_pnl": format(costed["gross_pnl"], "f"),
                "net_pnl": format(costed["net_pnl"], "f"),
                "cost_components": costed["cost_components"],
                "_cost_components_decimal": costed["cost_components_decimal"],
            }
        )
        last_i = i

    gross = sum(Decimal(t["gross_pnl"]) for t in trades)
    net = sum(Decimal(t["net_pnl"]) for t in trades)
    regimes = Counter(str(t.get("regime") or "UNKNOWN") for t in trades)
    net_series = [float(t["net_pnl"]) for t in trades]
    return {
        "trade_count": len(trades),
        "observation_count": len(rows),
        "dq_block_events": dq_blocks,
        "gross_pnl": float(gross),
        "net_pnl": float(net),
        "regime_breakdown": dict(regimes),
        "net_series": net_series,
        "p_value": two_sided_sign_pvalue(net_series),
        "trades_sample": trades[:5],
    }


def evaluate_mechanism(
    spec: MechanismSpec,
    panel: DevelopmentPanel,
    rows_by_symbol: dict[str, list[dict[str, Any]]],
    available: set[str],
) -> dict[str, Any]:
    missing = missing_required(spec, available)
    base = {
        "mechanism_id": spec.mechanism_id,
        "family": spec.family,
        "signal_kind": spec.signal_kind,
        "required_data": list(spec.required_data),
        "missing_required_features": missing,
        "qualification_claim": False,
        "qualified": False,
        "qualification_ready": False,
        "profitability_claimed": False,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
        "data_lineage": panel.classification,
        "fixture_used": panel.fixture_used,
    }
    if missing:
        return {
            **base,
            "data_blocked": True,
            "sample_blocked": False,
            "trade_count": 0,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "regime_breakdown": {},
            "symbol_net": {},
            "net_series": [],
            "p_value": 1.0,
            "failure_reasons": [f"missing_feature:{m}" for m in missing],
        }

    symbol_nets: dict[str, float] = {}
    all_trades_net: list[float] = []
    regime_counter: Counter[str] = Counter()
    trade_count = 0
    gross_sum = 0.0
    net_sum = 0.0
    obs = 0
    p_values: list[float] = []
    for sym in panel.symbols:
        rows = rows_by_symbol.get(sym) or []
        if len(rows) < MIN_SAMPLE_OBSERVATIONS:
            continue
        sim = _simulate_on_symbol(spec, rows)
        obs += int(sim["observation_count"])
        trade_count += int(sim["trade_count"])
        gross_sum += float(sim["gross_pnl"])
        net_sum += float(sim["net_pnl"])
        symbol_nets[sym] = float(sim["net_pnl"])
        all_trades_net.extend(list(sim["net_series"]))
        regime_counter.update(sim["regime_breakdown"])
        p_values.append(float(sim["p_value"]))

    # Combined p: mean of per-symbol p (conservative development proxy)
    p_comb = sum(p_values) / len(p_values) if p_values else 1.0
    sample_blocked = trade_count < MIN_SAMPLE_TRADES or obs < MIN_SAMPLE_OBSERVATIONS
    top_regime_share = 0.0
    if trade_count > 0 and regime_counter:
        top_regime_share = max(regime_counter.values()) / trade_count

    return {
        **base,
        "data_blocked": False,
        "sample_blocked": sample_blocked,
        "trade_count": trade_count,
        "observation_count": obs,
        "gross_pnl": gross_sum,
        "net_pnl": net_sum,
        "regime_breakdown": dict(regime_counter),
        "regime_top_share": top_regime_share,
        "regime_fragile": bool(
            trade_count >= MIN_SAMPLE_TRADES and top_regime_share >= REGIME_FRAGILITY_SHARE
        ),
        "symbol_net": symbol_nets,
        "net_series": all_trades_net,
        "p_value": p_comb,
        "failure_reasons": [],
        "cost_destroyed": bool(gross_sum > 0 and net_sum <= 0),
    }


def evaluate_all_mechanisms(panel: DevelopmentPanel) -> list[dict[str, Any]]:
    available = available_feature_set(panel)
    rows_by_symbol = build_feature_panel(panel)
    results = [evaluate_mechanism(spec, panel, rows_by_symbol, available) for spec in SPECS]
    return results


def mechanism_family_count(results: list[dict[str, Any]]) -> int:
    return len({r["family"] for r in results})
