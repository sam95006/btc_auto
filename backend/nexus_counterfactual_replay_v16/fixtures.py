"""Deterministic fixtures for V16-B Counterfactual Replay Engine."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_counterfactual_replay_v16.constants import (
    DEFAULT_SEED,
    FIXTURE_LABEL,
    SCHEMA_FIXTURES,
    STRATEGY_EXPERTS,
)
from backend.nexus_counterfactual_replay_v16.ledger_guard import ledger_fingerprint
from backend.nexus_counterfactual_replay_v16.types import Bar, DecisionTrade


def _bar(
    i: int,
    *,
    base_ts: int,
    base_px: float,
    path: list[float],
    regime: str = "TREND",
    trust: float = 0.9,
    transition_at: int | None = None,
) -> Bar:
    px = base_px * path[i]
    ts = base_ts + i * 60_000
    return Bar(
        ts_ms=ts,
        open=px * 0.999,
        high=px * 1.004,
        low=px * 0.996,
        close=px,
        volume=1000.0 + i,
        receive_ts_ms=ts + 50,
        data_trust=trust,
        regime=regime if transition_at is None or i < transition_at else "VOL_EXPANSION",
        regime_transition=transition_at is not None and i == transition_at,
    )


def build_price_path(seed: str = DEFAULT_SEED) -> list[float]:
    """Deterministic multiplicative path (no RNG drift)."""
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    out = [1.0]
    for i in range(1, 48):
        b = h[i % len(h)]
        # mild up then down — stop/TP exercisable
        step = ((b / 255.0) - 0.45) * 0.004
        if 12 <= i <= 20:
            step = abs(step) + 0.002
        if 28 <= i <= 36:
            step = -abs(step) - 0.0025
        out.append(out[-1] * (1.0 + step))
    return out


def build_fixture_bars(*, seed: str = DEFAULT_SEED, base_ts: int = 1_700_000_000_000) -> list[Bar]:
    path = build_price_path(seed)
    bars: list[Bar] = []
    for i in range(len(path)):
        trust = 0.92 if i < 40 else 0.30  # late bars low trust for BLOCK path
        bars.append(
            _bar(
                i,
                base_ts=base_ts,
                base_px=100.0,
                path=path,
                regime="TREND",
                trust=trust,
                transition_at=24,
            )
        )
    # Inject one future-leakage bar (must be excluded by PIT).
    future_ts = base_ts + 10_000 * 60_000
    bars.append(
        Bar(
            ts_ms=future_ts,
            open=120.0,
            high=121.0,
            low=119.0,
            close=120.5,
            volume=1.0,
            receive_ts_ms=future_ts + 10,
            data_trust=1.0,
            regime="FUTURE_LEAK",
            regime_transition=False,
        )
    )
    return bars


def build_fixture_decisions(*, seed: str = DEFAULT_SEED, base_ts: int = 1_700_000_000_000) -> list[DecisionTrade]:
    bars = build_fixture_bars(seed=seed, base_ts=base_ts)
    # Primary decision enters at bar 10, exits at bar 30.
    entry_i, exit_i = 10, 30
    entry = bars[entry_i]
    exit_b = bars[exit_i]
    stop = entry.close * 0.985
    tp = entry.close * 1.025

    d1 = DecisionTrade(
        decision_id="V16B_DEC_001",
        trade_id="V16B_TRD_001",
        symbol="BTCUSDT",
        side="LONG",
        strategy_expert="TREND",
        decision_ts_ms=entry.ts_ms,
        entry_ts_ms=entry.ts_ms,
        exit_ts_ms=exit_b.ts_ms,
        entry_price=entry.close,
        exit_price=exit_b.close,
        stop_price=stop,
        take_profit_price=tp,
        size=1.0,
        data_trust_at_decision=entry.data_trust,
        regime_at_decision=entry.regime,
        confirmation_ready_ts_ms=bars[entry_i + 1].ts_ms,
        is_fixture=True,
        labels=(FIXTURE_LABEL,),
    )
    d1 = DecisionTrade(**{**d1.to_dict(), "ledger_fingerprint": ledger_fingerprint(d1), "labels": d1.labels})

    # Second decision with low data trust at decision time.
    low_i = 42
    low = bars[low_i]
    d2 = DecisionTrade(
        decision_id="V16B_DEC_002",
        trade_id="V16B_TRD_002",
        symbol="BTCUSDT",
        side="LONG",
        strategy_expert="BREAKOUT",
        decision_ts_ms=low.ts_ms,
        entry_ts_ms=low.ts_ms,
        exit_ts_ms=bars[min(low_i + 3, len(bars) - 2)].ts_ms,
        entry_price=low.close,
        exit_price=bars[min(low_i + 3, len(bars) - 2)].close,
        stop_price=low.close * 0.99,
        take_profit_price=low.close * 1.02,
        size=0.5,
        data_trust_at_decision=low.data_trust,
        regime_at_decision=low.regime,
        confirmation_ready_ts_ms=None,
        is_fixture=True,
        labels=(FIXTURE_LABEL,),
    )
    d2 = DecisionTrade(**{**d2.to_dict(), "ledger_fingerprint": ledger_fingerprint(d2), "labels": d2.labels})

    # Short trade for reverse/early paths.
    short_i, short_exit = 14, 26
    se = bars[short_i]
    sx = bars[short_exit]
    d3 = DecisionTrade(
        decision_id="V16B_DEC_003",
        trade_id="V16B_TRD_003",
        symbol="ETHUSDT",
        side="SHORT",
        strategy_expert="MEAN_REVERSION",
        decision_ts_ms=se.ts_ms,
        entry_ts_ms=se.ts_ms,
        exit_ts_ms=sx.ts_ms,
        entry_price=se.close,
        exit_price=sx.close,
        stop_price=se.close * 1.02,
        take_profit_price=se.close * 0.97,
        size=2.0,
        data_trust_at_decision=se.data_trust,
        regime_at_decision=se.regime,
        confirmation_ready_ts_ms=bars[short_i + 1].ts_ms,
        is_fixture=True,
        labels=(FIXTURE_LABEL,),
    )
    d3 = DecisionTrade(**{**d3.to_dict(), "ledger_fingerprint": ledger_fingerprint(d3), "labels": d3.labels})

    return [d1, d2, d3]


def fixture_manifest(*, seed: str = DEFAULT_SEED) -> dict[str, Any]:
    bars = build_fixture_bars(seed=seed)
    decisions = build_fixture_decisions(seed=seed)
    payload = {
        "schema": SCHEMA_FIXTURES,
        "seed": seed,
        "fixture_label": FIXTURE_LABEL,
        "bar_count": len(bars),
        "decision_count": len(decisions),
        "strategy_experts_catalog": list(STRATEGY_EXPERTS),
        "decisions": [d.to_dict() for d in decisions],
        "is_real_ledger": False,
        "is_fixture": True,
        "real_performance": False,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    payload["fixture_checksum"] = digest
    return payload
