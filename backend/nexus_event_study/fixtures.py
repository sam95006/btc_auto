"""Synthetic fixtures for V14-B Event Study Engine (no live exchange / no real 14d)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_event_study.constants import EVENT_DEFINITION_IDS
from backend.nexus_event_study.types import StudyEvent


def _seed_int(seed: str) -> int:
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)


def _obs_id(symbol: str, event_id: str, ts_ms: int, seq: int) -> str:
    raw = f"{event_id}|{symbol}|{ts_ms}|{seq}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def make_study_event(
    *,
    event_id: str,
    symbol: str,
    decision_ts_ms: int,
    seq: int,
    side: str = "BUY",
    entry_price: float = 100.0,
    regime: str = "TREND",
    receive_lag_ms: int = 2,
    source: str = "synthetic",
    payload: dict[str, Any] | None = None,
) -> StudyEvent:
    base_payload: dict[str, Any] = {
        "notional": 1_000.0,
        "liq_notional": 2_500.0,
        "spread_bps": 4.0,
        "funding_rate": 0.0001,
        "basis_bps": 12.0,
        "oi_delta": 150.0,
        "price_delta": 0.15,
        "depth_delta": -800.0,
    }
    if payload:
        base_payload.update(payload)
    return StudyEvent(
        observation_id=_obs_id(symbol, event_id, decision_ts_ms, seq),
        event_id=event_id,
        symbol=symbol,
        regime=regime,
        decision_ts_ms=int(decision_ts_ms),
        exchange_ts_ms=int(decision_ts_ms),
        receive_ts_ms=int(decision_ts_ms) + int(receive_lag_ms),
        side=side,
        entry_price=float(entry_price),
        source=source,
        payload=base_payload,
        is_trade=False,
    )


def _forward_path(
    *,
    entry: float,
    side: str,
    seed_n: int,
    seq: int,
    bars: int = 40,
) -> list[float]:
    """Deterministic synthetic forward path (descriptive only — not a trade)."""
    path = [float(entry)]
    px = float(entry)
    for h in range(1, bars + 1):
        # Tiny deterministic drift / noise from seed+seq+h — never RNG.
        amp = ((seed_n + seq * 17 + h * 31) % 97) / 10_000.0
        sign = 1.0 if (seed_n + seq + h) % 2 == 0 else -1.0
        if side.upper() in {"SELL", "SHORT"}:
            sign = -sign
        px = px * (1.0 + sign * amp)
        path.append(px)
    return path


def build_synthetic_cohort(
    *,
    seed: str = "v14b-default",
    base_ts_ms: int = 1_720_000_000_000,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    regimes: tuple[str, ...] = ("TREND", "RANGE", "SHOCK"),
    events_per_symbol: int = 4,
    include_overlap_pair: bool = True,
    include_incomplete: bool = True,
    include_future: bool = True,
) -> dict[str, Any]:
    """Deterministic multi-symbol cohort with intentional edge cases."""
    seed_n = _seed_int(seed)
    events: list[StudyEvent] = []
    paths: dict[str, list[float]] = {}
    seq = 0
    bar_ms = 60_000

    for si, sym in enumerate(symbols):
        for ei in range(events_per_symbol):
            event_id = EVENT_DEFINITION_IDS[(si + ei + seed_n) % len(EVENT_DEFINITION_IDS)]
            regime = regimes[(si + ei) % len(regimes)]
            decision = base_ts_ms + (si * 10 + ei * 40) * bar_ms + (seed_n % 1000)
            side = "BUY" if (si + ei) % 2 == 0 else "SELL"
            entry = 100.0 + 10.0 * si + (seed_n % 23) * 0.01 + ei
            seq += 1
            ev = make_study_event(
                event_id=event_id,
                symbol=sym,
                decision_ts_ms=decision,
                seq=seq,
                side=side,
                entry_price=entry,
                regime=regime,
            )
            events.append(ev)
            paths[ev.observation_id] = _forward_path(
                entry=entry, side=side, seed_n=seed_n, seq=seq
            )

    if include_overlap_pair and events:
        # Near-duplicate decision shortly after first event on same symbol/event_id.
        base = events[0]
        seq += 1
        overlap = make_study_event(
            event_id=base.event_id,
            symbol=base.symbol,
            decision_ts_ms=base.decision_ts_ms + 3 * bar_ms,
            seq=seq,
            side=base.side,
            entry_price=base.entry_price,
            regime=base.regime,
        )
        events.append(overlap)
        paths[overlap.observation_id] = _forward_path(
            entry=base.entry_price, side=base.side, seed_n=seed_n, seq=seq
        )

    if include_incomplete:
        seq += 1
        incomplete = make_study_event(
            event_id="spread_shock",
            symbol=symbols[0],
            decision_ts_ms=base_ts_ms + 500 * bar_ms,
            seq=seq,
            side="BUY",
            entry_price=101.0,
            regime="RANGE",
            payload={"spread_bps": 9.0},
        )
        events.append(incomplete)
        # Truncated path — fails completeness for long horizons.
        paths[incomplete.observation_id] = [101.0, 101.1, 101.2]

    if include_future:
        seq += 1
        future = make_study_event(
            event_id="funding_dislocation",
            symbol=symbols[-1],
            decision_ts_ms=base_ts_ms + 900 * bar_ms,
            seq=seq,
            side="SELL",
            entry_price=95.0,
            regime="SHOCK",
            payload={"funding_rate": 0.001},
        )
        # Force receive/exchange into the future relative to default as_of.
        future = StudyEvent(
            observation_id=future.observation_id,
            event_id=future.event_id,
            symbol=future.symbol,
            regime=future.regime,
            decision_ts_ms=future.decision_ts_ms,
            exchange_ts_ms=base_ts_ms + 2_000 * bar_ms,
            receive_ts_ms=base_ts_ms + 2_000 * bar_ms + 5,
            side=future.side,
            entry_price=future.entry_price,
            source=future.source,
            payload=future.payload,
            is_trade=False,
        )
        events.append(future)
        paths[future.observation_id] = _forward_path(
            entry=95.0, side="SELL", seed_n=seed_n, seq=seq
        )

    # One deliberately missing-field event.
    seq += 1
    broken = make_study_event(
        event_id="oi_step_change",
        symbol=symbols[0],
        decision_ts_ms=base_ts_ms + 50 * bar_ms,
        seq=seq,
        payload={},  # missing oi_delta
    )
    broken = StudyEvent(
        observation_id=broken.observation_id,
        event_id=broken.event_id,
        symbol=broken.symbol,
        regime=broken.regime,
        decision_ts_ms=broken.decision_ts_ms,
        exchange_ts_ms=broken.exchange_ts_ms,
        receive_ts_ms=broken.receive_ts_ms,
        side=broken.side,
        entry_price=broken.entry_price,
        source=broken.source,
        payload={},
        is_trade=False,
    )
    events.append(broken)
    paths[broken.observation_id] = _forward_path(
        entry=broken.entry_price, side=broken.side, seed_n=seed_n, seq=seq
    )

    payload = {
        "schema": "v14_b_synthetic_cohort",
        "seed": seed,
        "base_ts_ms": base_ts_ms,
        "symbols": list(symbols),
        "regimes": list(regimes),
        "event_count": len(events),
        "events": [e.to_dict() for e in events],
        "price_paths": {k: list(v) for k, v in paths.items()},
        "real_event_study_execution": False,
        "is_trade": False,
        "profitability_claimed": False,
    }
    digest = hashlib.sha256(
        json.dumps(
            {
                "seed": seed,
                "event_count": len(events),
                "ids": [e.observation_id for e in events],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    payload["fixture_checksum"] = digest
    payload["_events_objs"] = events
    payload["_paths_objs"] = paths
    return payload
