"""Microstructure scenario kinds and deterministic planning."""
from __future__ import annotations

import random

SCENARIO_KINDS = (
    # Book gates
    "stale_book_reject",
    "missing_book_reject",
    "empty_book_reject",
    # Top-of-book / depth / impact
    "top_of_book_spread_market",
    "depth_ladder_walk",
    "market_impact_partial",
    "market_impact_full",
    # Queue / latency / cancel-replace
    "queue_position_limit",
    "latency_distribution_sample",
    "cancel_replace_latency",
    "partial_fill_progression",
    # Mark / index / funding / liquidation
    "mark_index_divergence",
    "funding_timestamp_debit",
    "funding_timestamp_credit",
    "liquidation_distance_degrade",
    # Canonical fill policy preserved under book bridge
    "no_candle_touch_fill",
    "same_bar_ambiguous_blocked",
    "trade_through_limit_fill",
    # Core execution invariants via book bridge
    "market_buy_via_book",
    "market_sell_via_book",
    "duplicate_intent_no_exposure",
    "reduce_only_cannot_increase",
    "cost_bridge_round_trip",
    "qty_non_negative_close",
)


def plan_scenarios(seed: int, target: int) -> list[tuple[int, str]]:
    """Deterministically choose ``target`` scenarios with balanced kind coverage."""
    rng = random.Random(seed)
    per_kind = max(1, target // len(SCENARIO_KINDS))
    plan: list[tuple[int, str]] = []
    for kind in SCENARIO_KINDS:
        for _ in range(per_kind):
            plan.append((0, kind))
    while len(plan) < target:
        plan.append((0, rng.choice(SCENARIO_KINDS)))
    rng.shuffle(plan)
    return [(i, k) for i, (_, k) in enumerate(plan[:target])]


__all__ = ["SCENARIO_KINDS", "plan_scenarios"]
