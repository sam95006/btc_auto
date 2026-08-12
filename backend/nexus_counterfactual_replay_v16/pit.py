"""Point-in-time guards — no future leakage."""
from __future__ import annotations

from typing import Any, Iterable

from backend.nexus_counterfactual_replay_v16.hard_bans import HardBanViolation, refuse_future_leakage
from backend.nexus_counterfactual_replay_v16.types import Bar, DecisionTrade


def bar_pit_eligible(bar: Bar, *, as_of_ms: int) -> bool:
    recv = bar.receive_ts_ms if bar.receive_ts_ms > 0 else bar.ts_ms
    if bar.ts_ms <= 0 or recv <= 0:
        return False
    return bar.ts_ms <= as_of_ms and recv <= as_of_ms


def filter_bars_pit(bars: Iterable[Bar], *, as_of_ms: int) -> list[Bar]:
    return [b for b in bars if bar_pit_eligible(b, as_of_ms=as_of_ms)]


def assert_no_future_bars(bars: Iterable[Bar], *, as_of_ms: int) -> None:
    leaked = [b for b in bars if not bar_pit_eligible(b, as_of_ms=as_of_ms)]
    if leaked:
        refuse_future_leakage()


def prove_pit_excludes_future(
    bars: list[Bar],
    *,
    as_of_ms: int,
) -> dict[str, Any]:
    eligible = filter_bars_pit(bars, as_of_ms=as_of_ms)
    eligible_ts = {b.ts_ms for b in eligible}
    future = [
        b
        for b in bars
        if b.ts_ms > as_of_ms or (b.receive_ts_ms > 0 and b.receive_ts_ms > as_of_ms)
    ]
    leaked = [b.ts_ms for b in future if b.ts_ms in eligible_ts]
    return {
        "schema": "v16_b_pit_proof",
        "as_of_ms": as_of_ms,
        "input_count": len(bars),
        "eligible_count": len(eligible),
        "future_count": len(future),
        "leaked_ts": leaked,
        "pit_holds": len(leaked) == 0,
        "rule": "bar.ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
    }


def decision_as_of(decision: DecisionTrade) -> int:
    """Decision-time ceiling — counterfactual paths may not see later facts."""
    return int(decision.decision_ts_ms)


def path_as_of(decision: DecisionTrade, *, exit_ts_ms: int | None) -> int:
    """During path simulation, as_of advances only to the simulated exit, never beyond available PIT."""
    if exit_ts_ms is None:
        return decision_as_of(decision)
    return max(int(decision.decision_ts_ms), int(exit_ts_ms))


def refuse_if_uses_future_price(
    *,
    decision: DecisionTrade,
    price_ts_ms: int,
    as_of_ms: int,
) -> None:
    if price_ts_ms > as_of_ms:
        raise HardBanViolation(
            f"no_future_leakage:price_ts={price_ts_ms}>as_of={as_of_ms}:decision={decision.decision_id}"
        )
