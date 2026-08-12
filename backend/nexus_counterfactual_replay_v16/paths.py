"""Alternate-path evaluators for each Decision/Trade."""
from __future__ import annotations

from typing import Any, Callable

from backend.nexus_counterfactual_replay_v16.comparability import mark_comparability
from backend.nexus_counterfactual_replay_v16.constants import (
    ALTERNATE_PATHS,
    DATA_TRUST_BLOCK_THRESHOLD,
    DEFAULT_ALT_SIZE_SCALE,
    DEFAULT_ALT_STOP_MULT,
    DEFAULT_ALT_TP_MULT,
    DEFAULT_CONFIRM_BARS,
    DEFAULT_DELAY_BARS,
    DEFAULT_EARLY_BARS,
    DISCLAIMER,
    SCHEMA_PATH,
)
from backend.nexus_counterfactual_replay_v16.costs import apply_round_trip_costs
from backend.nexus_counterfactual_replay_v16.pit import bar_pit_eligible, filter_bars_pit
from backend.nexus_counterfactual_replay_v16.types import Bar, DecisionTrade, PathOutcome


def _index_at(bars: list[Bar], ts_ms: int) -> int | None:
    for i, b in enumerate(bars):
        if b.ts_ms == ts_ms:
            return i
    # nearest <= ts
    best = None
    for i, b in enumerate(bars):
        if b.ts_ms <= ts_ms:
            best = i
    return best


def _simulate_exit(
    bars: list[Bar],
    *,
    side: str,
    entry_i: int,
    stop: float,
    tp: float,
    hard_exit_i: int,
    regime_exit: bool = False,
) -> tuple[int, float, str]:
    """Walk forward from entry; hit stop/TP/regime/hard exit. Bars must already be PIT-filtered."""
    for i in range(entry_i + 1, min(hard_exit_i, len(bars) - 1) + 1):
        b = bars[i]
        if regime_exit and b.regime_transition:
            return i, b.close, "regime_transition"
        if side == "LONG":
            if b.low <= stop:
                return i, stop, "stop"
            if b.high >= tp:
                return i, tp, "take_profit"
        else:
            if b.high >= stop:
                return i, stop, "stop"
            if b.low <= tp:
                return i, tp, "take_profit"
    i = min(hard_exit_i, len(bars) - 1)
    return i, bars[i].close, "time_exit"


def _blocked_outcome(
    path_id: str,
    decision: DecisionTrade,
    *,
    reason: str,
    coverage: str,
    comparability: str,
    pit_ok: bool,
) -> PathOutcome:
    return PathOutcome(
        path_id=path_id,
        decision_id=decision.decision_id,
        trade_id=decision.trade_id,
        executed=False,
        blocked=True,
        block_reason=reason,
        entry_ts_ms=None,
        exit_ts_ms=None,
        entry_price=None,
        exit_price=None,
        size=0.0,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        gross_pnl=0.0,
        cost_total=0.0,
        net_pnl=0.0,
        slippage_cost=0.0,
        fee_cost=0.0,
        spread_cost=0.0,
        comparability=comparability,
        coverage=coverage,
        pit_ok=pit_ok,
        cost_included=True,
        notes=f"{reason}; {DISCLAIMER}",
        is_counterfactual=True,
        is_real_performance=False,
    )


def _filled_outcome(
    path_id: str,
    decision: DecisionTrade,
    *,
    entry_bar: Bar,
    exit_i: int,
    exit_price: float,
    size: float,
    side: str,
    strategy_expert: str,
    bars: list[Bar],
    same_side_semantics: bool = True,
    note: str = "",
) -> PathOutcome:
    exit_bar = bars[exit_i]
    entry_px = entry_bar.close
    costs = apply_round_trip_costs(
        side=side,
        size=size,
        entry_price=entry_px,
        exit_price=exit_price,
    )
    marks = mark_comparability(
        pit_ok=True,
        cost_included=True,
        path_series_complete=True,
        data_trust_ok=decision.data_trust_at_decision >= DATA_TRUST_BLOCK_THRESHOLD,
        same_symbol=True,
        same_side_semantics=same_side_semantics,
    )
    return PathOutcome(
        path_id=path_id,
        decision_id=decision.decision_id,
        trade_id=decision.trade_id,
        executed=True,
        blocked=False,
        block_reason=None,
        entry_ts_ms=entry_bar.ts_ms,
        exit_ts_ms=exit_bar.ts_ms,
        entry_price=entry_px,
        exit_price=exit_price,
        size=size,
        side=side,
        strategy_expert=strategy_expert,
        gross_pnl=costs["gross_pnl"],
        cost_total=costs["cost_total"],
        net_pnl=costs["net_pnl"],
        slippage_cost=costs["slippage_cost"],
        fee_cost=costs["fee_cost"],
        spread_cost=costs["spread_cost"],
        comparability=marks["comparability"],
        coverage=marks["coverage"],
        pit_ok=True,
        cost_included=True,
        notes=f"{note}; {DISCLAIMER}".strip("; "),
        is_counterfactual=path_id != "observed_baseline",
        is_real_performance=False,
    )


def evaluate_observed_baseline(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    """Cost-adjusted baseline of the observed trade — still NOT real performance claim."""
    as_of = decision.exit_ts_ms
    pit_bars = filter_bars_pit(bars, as_of_ms=as_of)
    entry_i = _index_at(pit_bars, decision.entry_ts_ms)
    exit_i = _index_at(pit_bars, decision.exit_ts_ms)
    if entry_i is None or exit_i is None:
        marks = mark_comparability(
            pit_ok=False,
            cost_included=False,
            path_series_complete=False,
            data_trust_ok=False,
        )
        return _blocked_outcome(
            "observed_baseline",
            decision,
            reason="missing_pit_bars_for_baseline",
            coverage=marks["coverage"],
            comparability=marks["comparability"],
            pit_ok=False,
        )
    costs = apply_round_trip_costs(
        side=decision.side,
        size=decision.size,
        entry_price=decision.entry_price,
        exit_price=decision.exit_price,
    )
    marks = mark_comparability(
        pit_ok=True,
        cost_included=True,
        path_series_complete=True,
        data_trust_ok=True,
    )
    return PathOutcome(
        path_id="observed_baseline",
        decision_id=decision.decision_id,
        trade_id=decision.trade_id,
        executed=True,
        blocked=False,
        block_reason=None,
        entry_ts_ms=decision.entry_ts_ms,
        exit_ts_ms=decision.exit_ts_ms,
        entry_price=decision.entry_price,
        exit_price=decision.exit_price,
        size=decision.size,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        gross_pnl=costs["gross_pnl"],
        cost_total=costs["cost_total"],
        net_pnl=costs["net_pnl"],
        slippage_cost=costs["slippage_cost"],
        fee_cost=costs["fee_cost"],
        spread_cost=costs["spread_cost"],
        comparability=marks["comparability"],
        coverage=marks["coverage"],
        pit_ok=True,
        cost_included=True,
        notes=f"baseline_cost_adjusted; {DISCLAIMER}",
        is_counterfactual=False,
        is_real_performance=False,
    )


def path_no_entry(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    marks = mark_comparability(
        pit_ok=True,
        cost_included=True,
        path_series_complete=True,
        data_trust_ok=True,
    )
    return PathOutcome(
        path_id="no_entry",
        decision_id=decision.decision_id,
        trade_id=decision.trade_id,
        executed=False,
        blocked=False,
        block_reason=None,
        entry_ts_ms=None,
        exit_ts_ms=None,
        entry_price=None,
        exit_price=None,
        size=0.0,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        gross_pnl=0.0,
        cost_total=0.0,
        net_pnl=0.0,
        slippage_cost=0.0,
        fee_cost=0.0,
        spread_cost=0.0,
        comparability=marks["comparability"],
        coverage=marks["coverage"],
        pit_ok=True,
        cost_included=True,
        notes=f"skipped_entry; {DISCLAIMER}",
        is_counterfactual=True,
        is_real_performance=False,
    )


def path_delay_entry(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    as_of = decision.exit_ts_ms
    pit_bars = filter_bars_pit(bars, as_of_ms=as_of)
    entry_i = _index_at(pit_bars, decision.entry_ts_ms)
    hard_exit = _index_at(pit_bars, decision.exit_ts_ms)
    if entry_i is None or hard_exit is None:
        return _blocked_outcome(
            "delay_entry",
            decision,
            reason="missing_path_series",
            coverage="MISSING_PATH_SERIES",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=entry_i is not None,
        )
    new_i = entry_i + DEFAULT_DELAY_BARS
    if new_i >= hard_exit or new_i >= len(pit_bars):
        return _blocked_outcome(
            "delay_entry",
            decision,
            reason="delay_exceeds_horizon",
            coverage="PARTIAL",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=True,
        )
    exit_i, exit_px, why = _simulate_exit(
        pit_bars,
        side=decision.side,
        entry_i=new_i,
        stop=decision.stop_price,
        tp=decision.take_profit_price,
        hard_exit_i=hard_exit,
    )
    return _filled_outcome(
        "delay_entry",
        decision,
        entry_bar=pit_bars[new_i],
        exit_i=exit_i,
        exit_price=exit_px,
        size=decision.size,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        bars=pit_bars,
        note=f"delayed_{DEFAULT_DELAY_BARS}_bars;exit={why}",
    )


def path_early_entry(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    as_of = decision.exit_ts_ms
    pit_bars = filter_bars_pit(bars, as_of_ms=as_of)
    entry_i = _index_at(pit_bars, decision.entry_ts_ms)
    hard_exit = _index_at(pit_bars, decision.exit_ts_ms)
    if entry_i is None or hard_exit is None:
        return _blocked_outcome(
            "early_entry",
            decision,
            reason="missing_path_series",
            coverage="MISSING_PATH_SERIES",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=False,
        )
    new_i = max(0, entry_i - DEFAULT_EARLY_BARS)
    # Early entry still may only use bars known by decision time for the *decision*,
    # but price path after early entry is simulated under exit as_of (PIT to exit).
    # Guard: early bar receive must be <= decision_ts for decision-time knowledge;
    # if not, mark partial comparability but still simulate with available series.
    early_bar = pit_bars[new_i]
    decision_time_ok = bar_pit_eligible(early_bar, as_of_ms=decision.decision_ts_ms)
    exit_i, exit_px, why = _simulate_exit(
        pit_bars,
        side=decision.side,
        entry_i=new_i,
        stop=decision.stop_price,
        tp=decision.take_profit_price,
        hard_exit_i=hard_exit,
    )
    out = _filled_outcome(
        "early_entry",
        decision,
        entry_bar=early_bar,
        exit_i=exit_i,
        exit_price=exit_px,
        size=decision.size,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        bars=pit_bars,
        note=f"early_{DEFAULT_EARLY_BARS}_bars;exit={why};decision_time_visible={decision_time_ok}",
    )
    if not decision_time_ok:
        marks = mark_comparability(
            pit_ok=True,
            cost_included=True,
            path_series_complete=True,
            data_trust_ok=True,
            same_side_semantics=True,
        )
        # Re-mark as partial: early entry assumes pre-decision prices (historical known).
        out.comparability = "PARTIALLY_COMPARABLE"
        out.coverage = "PARTIAL"
        out.notes += f";comparability={marks['comparability']}_downgraded_for_pre_decision_entry"
    return out


def path_reverse(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    as_of = decision.exit_ts_ms
    pit_bars = filter_bars_pit(bars, as_of_ms=as_of)
    entry_i = _index_at(pit_bars, decision.entry_ts_ms)
    hard_exit = _index_at(pit_bars, decision.exit_ts_ms)
    if entry_i is None or hard_exit is None:
        return _blocked_outcome(
            "reverse",
            decision,
            reason="missing_path_series",
            coverage="MISSING_PATH_SERIES",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=False,
        )
    side = "SHORT" if decision.side == "LONG" else "LONG"
    # Mirror stop/TP around entry.
    entry_px = pit_bars[entry_i].close
    if side == "SHORT":
        stop = entry_px * (1.0 + abs(decision.entry_price - decision.stop_price) / decision.entry_price)
        tp = entry_px * (1.0 - abs(decision.take_profit_price - decision.entry_price) / decision.entry_price)
    else:
        stop = entry_px * (1.0 - abs(decision.stop_price - decision.entry_price) / decision.entry_price)
        tp = entry_px * (1.0 + abs(decision.take_profit_price - decision.entry_price) / decision.entry_price)
    exit_i, exit_px, why = _simulate_exit(
        pit_bars, side=side, entry_i=entry_i, stop=stop, tp=tp, hard_exit_i=hard_exit
    )
    return _filled_outcome(
        "reverse",
        decision,
        entry_bar=pit_bars[entry_i],
        exit_i=exit_i,
        exit_price=exit_px,
        size=decision.size,
        side=side,
        strategy_expert=decision.strategy_expert,
        bars=pit_bars,
        same_side_semantics=False,
        note=f"reversed_side;exit={why}",
    )


def path_alt_stop(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    as_of = decision.exit_ts_ms
    pit_bars = filter_bars_pit(bars, as_of_ms=as_of)
    entry_i = _index_at(pit_bars, decision.entry_ts_ms)
    hard_exit = _index_at(pit_bars, decision.exit_ts_ms)
    if entry_i is None or hard_exit is None:
        return _blocked_outcome(
            "alt_stop",
            decision,
            reason="missing_path_series",
            coverage="MISSING_PATH_SERIES",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=False,
        )
    entry_px = pit_bars[entry_i].close
    dist = abs(decision.entry_price - decision.stop_price) * DEFAULT_ALT_STOP_MULT
    stop = entry_px - dist if decision.side == "LONG" else entry_px + dist
    exit_i, exit_px, why = _simulate_exit(
        pit_bars,
        side=decision.side,
        entry_i=entry_i,
        stop=stop,
        tp=decision.take_profit_price,
        hard_exit_i=hard_exit,
    )
    return _filled_outcome(
        "alt_stop",
        decision,
        entry_bar=pit_bars[entry_i],
        exit_i=exit_i,
        exit_price=exit_px,
        size=decision.size,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        bars=pit_bars,
        note=f"alt_stop_mult={DEFAULT_ALT_STOP_MULT};exit={why}",
    )


def path_alt_take_profit(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    as_of = decision.exit_ts_ms
    pit_bars = filter_bars_pit(bars, as_of_ms=as_of)
    entry_i = _index_at(pit_bars, decision.entry_ts_ms)
    hard_exit = _index_at(pit_bars, decision.exit_ts_ms)
    if entry_i is None or hard_exit is None:
        return _blocked_outcome(
            "alt_take_profit",
            decision,
            reason="missing_path_series",
            coverage="MISSING_PATH_SERIES",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=False,
        )
    entry_px = pit_bars[entry_i].close
    dist = abs(decision.take_profit_price - decision.entry_price) * DEFAULT_ALT_TP_MULT
    tp = entry_px + dist if decision.side == "LONG" else entry_px - dist
    exit_i, exit_px, why = _simulate_exit(
        pit_bars,
        side=decision.side,
        entry_i=entry_i,
        stop=decision.stop_price,
        tp=tp,
        hard_exit_i=hard_exit,
    )
    return _filled_outcome(
        "alt_take_profit",
        decision,
        entry_bar=pit_bars[entry_i],
        exit_i=exit_i,
        exit_price=exit_px,
        size=decision.size,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        bars=pit_bars,
        note=f"alt_tp_mult={DEFAULT_ALT_TP_MULT};exit={why}",
    )


def path_alt_size(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    as_of = decision.exit_ts_ms
    pit_bars = filter_bars_pit(bars, as_of_ms=as_of)
    entry_i = _index_at(pit_bars, decision.entry_ts_ms)
    hard_exit = _index_at(pit_bars, decision.exit_ts_ms)
    if entry_i is None or hard_exit is None:
        return _blocked_outcome(
            "alt_size",
            decision,
            reason="missing_path_series",
            coverage="MISSING_PATH_SERIES",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=False,
        )
    size = decision.size * DEFAULT_ALT_SIZE_SCALE
    exit_i, exit_px, why = _simulate_exit(
        pit_bars,
        side=decision.side,
        entry_i=entry_i,
        stop=decision.stop_price,
        tp=decision.take_profit_price,
        hard_exit_i=hard_exit,
    )
    return _filled_outcome(
        "alt_size",
        decision,
        entry_bar=pit_bars[entry_i],
        exit_i=exit_i,
        exit_price=exit_px,
        size=size,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        bars=pit_bars,
        note=f"size_scale={DEFAULT_ALT_SIZE_SCALE};exit={why}",
    )


def path_wait_confirm(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    as_of = decision.exit_ts_ms
    pit_bars = filter_bars_pit(bars, as_of_ms=as_of)
    entry_i = _index_at(pit_bars, decision.entry_ts_ms)
    hard_exit = _index_at(pit_bars, decision.exit_ts_ms)
    if entry_i is None or hard_exit is None:
        return _blocked_outcome(
            "wait_confirm",
            decision,
            reason="missing_path_series",
            coverage="MISSING_PATH_SERIES",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=False,
        )
    confirm_i = entry_i + DEFAULT_CONFIRM_BARS
    if decision.confirmation_ready_ts_ms:
        ci = _index_at(pit_bars, decision.confirmation_ready_ts_ms)
        if ci is not None:
            confirm_i = ci
    if confirm_i >= hard_exit or confirm_i >= len(pit_bars):
        return _blocked_outcome(
            "wait_confirm",
            decision,
            reason="confirmation_never_arrived",
            coverage="PARTIAL",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=True,
        )
    exit_i, exit_px, why = _simulate_exit(
        pit_bars,
        side=decision.side,
        entry_i=confirm_i,
        stop=decision.stop_price,
        tp=decision.take_profit_price,
        hard_exit_i=hard_exit,
    )
    return _filled_outcome(
        "wait_confirm",
        decision,
        entry_bar=pit_bars[confirm_i],
        exit_i=exit_i,
        exit_price=exit_px,
        size=decision.size,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        bars=pit_bars,
        note=f"wait_confirm;exit={why}",
    )


def path_alt_strategy_expert(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    """Route to DEFENSIVE_NO_TRADE when original was aggressive; else TREND."""
    alt = "DEFENSIVE_NO_TRADE" if decision.strategy_expert != "DEFENSIVE_NO_TRADE" else "TREND"
    if alt == "DEFENSIVE_NO_TRADE":
        marks = mark_comparability(
            pit_ok=True,
            cost_included=True,
            path_series_complete=True,
            data_trust_ok=True,
            same_side_semantics=True,
        )
        return PathOutcome(
            path_id="alt_strategy_expert",
            decision_id=decision.decision_id,
            trade_id=decision.trade_id,
            executed=False,
            blocked=False,
            block_reason=None,
            entry_ts_ms=None,
            exit_ts_ms=None,
            entry_price=None,
            exit_price=None,
            size=0.0,
            side=decision.side,
            strategy_expert=alt,
            gross_pnl=0.0,
            cost_total=0.0,
            net_pnl=0.0,
            slippage_cost=0.0,
            fee_cost=0.0,
            spread_cost=0.0,
            comparability=marks["comparability"],
            coverage=marks["coverage"],
            pit_ok=True,
            cost_included=True,
            notes=f"alt_expert={alt};no_trade; {DISCLAIMER}",
            is_counterfactual=True,
            is_real_performance=False,
        )
    # Fallback: treat as delayed confirm under TREND semantics.
    out = path_wait_confirm(decision, bars)
    out.path_id = "alt_strategy_expert"
    out.strategy_expert = alt
    out.notes = f"alt_expert={alt}; {out.notes}"
    return out


def path_exit_on_regime_transition(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    as_of = decision.exit_ts_ms
    pit_bars = filter_bars_pit(bars, as_of_ms=as_of)
    entry_i = _index_at(pit_bars, decision.entry_ts_ms)
    hard_exit = _index_at(pit_bars, decision.exit_ts_ms)
    if entry_i is None or hard_exit is None:
        return _blocked_outcome(
            "exit_on_regime_transition",
            decision,
            reason="missing_path_series",
            coverage="MISSING_PATH_SERIES",
            comparability="PARTIALLY_COMPARABLE",
            pit_ok=False,
        )
    exit_i, exit_px, why = _simulate_exit(
        pit_bars,
        side=decision.side,
        entry_i=entry_i,
        stop=decision.stop_price,
        tp=decision.take_profit_price,
        hard_exit_i=hard_exit,
        regime_exit=True,
    )
    return _filled_outcome(
        "exit_on_regime_transition",
        decision,
        entry_bar=pit_bars[entry_i],
        exit_i=exit_i,
        exit_price=exit_px,
        size=decision.size,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        bars=pit_bars,
        note=f"regime_aware_exit;exit={why}",
    )


def path_block_low_data_trust(decision: DecisionTrade, bars: list[Bar]) -> PathOutcome:
    if decision.data_trust_at_decision < DATA_TRUST_BLOCK_THRESHOLD:
        marks = mark_comparability(
            pit_ok=True,
            cost_included=True,
            path_series_complete=True,
            data_trust_ok=False,
        )
        return _blocked_outcome(
            "block_low_data_trust",
            decision,
            reason=f"data_trust={decision.data_trust_at_decision}<{DATA_TRUST_BLOCK_THRESHOLD}",
            coverage=marks["coverage"],
            comparability=marks["comparability"],
            pit_ok=True,
        )
    # Trust OK — path records that BLOCK would not fire; no alternate trade.
    marks = mark_comparability(
        pit_ok=True,
        cost_included=True,
        path_series_complete=True,
        data_trust_ok=True,
    )
    return PathOutcome(
        path_id="block_low_data_trust",
        decision_id=decision.decision_id,
        trade_id=decision.trade_id,
        executed=False,
        blocked=False,
        block_reason=None,
        entry_ts_ms=None,
        exit_ts_ms=None,
        entry_price=None,
        exit_price=None,
        size=0.0,
        side=decision.side,
        strategy_expert=decision.strategy_expert,
        gross_pnl=None,
        cost_total=None,
        net_pnl=None,
        slippage_cost=None,
        fee_cost=None,
        spread_cost=None,
        comparability="NOT_COMPARABLE",
        coverage=marks["coverage"],
        pit_ok=True,
        cost_included=True,
        notes=f"trust_above_threshold_block_not_triggered; {DISCLAIMER}",
        is_counterfactual=True,
        is_real_performance=False,
    )


PATH_EVALUATORS: dict[str, Callable[[DecisionTrade, list[Bar]], PathOutcome]] = {
    "no_entry": path_no_entry,
    "delay_entry": path_delay_entry,
    "early_entry": path_early_entry,
    "reverse": path_reverse,
    "alt_stop": path_alt_stop,
    "alt_take_profit": path_alt_take_profit,
    "alt_size": path_alt_size,
    "wait_confirm": path_wait_confirm,
    "alt_strategy_expert": path_alt_strategy_expert,
    "exit_on_regime_transition": path_exit_on_regime_transition,
    "block_low_data_trust": path_block_low_data_trust,
}


def assert_path_inventory_complete() -> None:
    missing = [p for p in ALTERNATE_PATHS if p not in PATH_EVALUATORS]
    if missing:
        raise RuntimeError(f"missing_path_evaluators:{missing}")


def evaluate_all_paths(decision: DecisionTrade, bars: list[Bar]) -> list[PathOutcome]:
    assert_path_inventory_complete()
    outcomes = [evaluate_observed_baseline(decision, bars)]
    for path_id in ALTERNATE_PATHS:
        outcomes.append(PATH_EVALUATORS[path_id](decision, bars))
    for o in outcomes:
        assert o.is_real_performance is False
        d = o.to_dict()
        d["schema"] = SCHEMA_PATH
    return outcomes
