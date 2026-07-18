"""Phase 5 Gate C — Deterministic Replay Engine.

RESEARCH ONLY. Replays historical or synthetic market events through the
simulation stack using only public data inputs:
  - OHLCV bars
  - Open Interest (OI)
  - Funding rates
  - Candidate signals
  - Anomaly events

Features:
  - Date range selection
  - Deterministic random seed
  - Pause / resume / checkpoint
  - GET status endpoint (no private API)
  - Isolated from production execution

Never uses private API keys, real wallet data, or real positions.
"""
from __future__ import annotations

import logging
import random
import threading
import time
import uuid
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Replay states ─────────────────────────────────────────────────────────────
REPLAY_IDLE = "IDLE"
REPLAY_RUNNING = "RUNNING"
REPLAY_PAUSED = "PAUSED"
REPLAY_COMPLETED = "COMPLETED"
REPLAY_FAILED = "FAILED"

# ── Bar interval ──────────────────────────────────────────────────────────────
INTERVAL_1M = "1m"
INTERVAL_5M = "5m"
INTERVAL_15M = "15m"
INTERVAL_1H = "1h"

_INTERVAL_MS = {
    INTERVAL_1M: 60_000,
    INTERVAL_5M: 300_000,
    INTERVAL_15M: 900_000,
    INTERVAL_1H: 3_600_000,
}

_MAX_CHECKPOINT_HISTORY = 20
_MAX_REPLAY_EVENTS_LOG = 2000


class OHLCVBar:
    """A single OHLCV bar for replay."""

    def __init__(
        self,
        symbol: str,
        timestamp_ms: int,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        oi: float = 0.0,
        funding_rate: float = 0.0,
    ) -> None:
        self.symbol = symbol
        self.timestamp_ms = timestamp_ms
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.oi = oi
        self.funding_rate = funding_rate

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestampMs": self.timestamp_ms,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "oi": self.oi,
            "fundingRate": self.funding_rate,
        }


class ReplayCheckpoint:
    """Snapshot of replay state at a specific bar index."""

    def __init__(
        self,
        checkpoint_id: str,
        bar_index: int,
        timestamp_ms: int,
        sim_status: dict[str, Any],
        ledger_snapshot: dict[str, Any],
    ) -> None:
        self.checkpoint_id = checkpoint_id
        self.bar_index = bar_index
        self.timestamp_ms = timestamp_ms
        self.sim_status = sim_status
        self.ledger_snapshot = ledger_snapshot
        self.created_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpointId": self.checkpoint_id,
            "barIndex": self.bar_index,
            "timestampMs": self.timestamp_ms,
            "simStatus": self.sim_status,
            "ledgerSnapshot": self.ledger_snapshot,
            "createdAtMs": self.created_at_ms,
            "researchOnly": True,
        }


class ReplaySession:
    """A single replay run."""

    def __init__(
        self,
        session_id: str,
        symbols: list[str],
        start_ms: int,
        end_ms: int,
        interval: str,
        seed: int,
        bars: list[OHLCVBar],
        candidate_events: list[dict[str, Any]],
        anomaly_events: list[dict[str, Any]],
    ) -> None:
        self.session_id = session_id
        self.symbols = symbols
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.interval = interval
        self.seed = seed
        self.bars = bars
        self.candidate_events = candidate_events
        self.anomaly_events = anomaly_events

        self.state = REPLAY_IDLE
        self.current_bar_index = 0
        self.total_bars = len(bars)
        self.events_log: deque[dict[str, Any]] = deque(maxlen=_MAX_REPLAY_EVENTS_LOG)
        self.checkpoints: deque[ReplayCheckpoint] = deque(maxlen=_MAX_CHECKPOINT_HISTORY)
        self.error: str | None = None
        self.started_at_ms: int | None = None
        self.completed_at_ms: int | None = None
        self.created_at_ms = int(time.time() * 1000)
        self._rng = random.Random(seed)

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events_log.append({
            "eventType": event_type,
            "barIndex": self.current_bar_index,
            "ts": int(time.time() * 1000),
            "payload": payload,
        })

    def save_checkpoint(self, sim=None, ledger=None) -> ReplayCheckpoint:
        bar_ts = self.bars[self.current_bar_index].timestamp_ms if self.bars else 0
        cp = ReplayCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            bar_index=self.current_bar_index,
            timestamp_ms=bar_ts,
            sim_status=sim.status() if sim is not None else {},
            ledger_snapshot=ledger.snapshot() if ledger is not None else {},
        )
        self.checkpoints.append(cp)
        return cp

    def status_dict(self) -> dict[str, Any]:
        progress_pct = (
            round(self.current_bar_index / self.total_bars * 100, 1)
            if self.total_bars > 0 else 0.0
        )
        return {
            "sessionId": self.session_id,
            "state": self.state,
            "symbols": self.symbols,
            "startMs": self.start_ms,
            "endMs": self.end_ms,
            "interval": self.interval,
            "seed": self.seed,
            "totalBars": self.total_bars,
            "currentBarIndex": self.current_bar_index,
            "progressPct": progress_pct,
            "checkpointCount": len(self.checkpoints),
            "eventsLogged": len(self.events_log),
            "error": self.error,
            "startedAtMs": self.started_at_ms,
            "completedAtMs": self.completed_at_ms,
            "createdAtMs": self.created_at_ms,
            "researchOnly": True,
        }


def _generate_synthetic_bars(
    symbol: str,
    start_ms: int,
    end_ms: int,
    interval: str,
    seed: int,
    base_price: float = 65000.0,
) -> list[OHLCVBar]:
    """Generate synthetic OHLCV bars for testing/replay when real data unavailable."""
    rng = random.Random(seed)
    interval_ms = _INTERVAL_MS.get(interval, 300_000)
    bars: list[OHLCVBar] = []
    price = base_price
    ts = start_ms

    while ts <= end_ms:
        drift = rng.gauss(0, price * 0.003)
        open_p = price
        close_p = max(price * 0.5, price + drift)
        high_p = max(open_p, close_p) * (1 + rng.uniform(0.0, 0.003))
        low_p = min(open_p, close_p) * (1 - rng.uniform(0.0, 0.003))
        volume = rng.uniform(100, 2000)
        oi = rng.uniform(50_000, 200_000)
        funding = rng.gauss(0.01, 0.02)

        bars.append(OHLCVBar(
            symbol=symbol,
            timestamp_ms=ts,
            open=round(open_p, 2),
            high=round(high_p, 2),
            low=round(low_p, 2),
            close=round(close_p, 2),
            volume=round(volume, 4),
            oi=round(oi, 2),
            funding_rate=round(funding, 6),
        ))
        price = close_p
        ts += interval_ms

    return bars


class ReplayEngine:
    """Deterministic replay engine. Runs replay sessions step-by-step or in a thread."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, ReplaySession] = {}
        self._active_session_id: str | None = None
        self._replay_thread: threading.Thread | None = None
        self._stop_flag: threading.Event = threading.Event()
        self._total_sessions = 0

    def create_session(
        self,
        symbols: list[str],
        start_ms: int,
        end_ms: int,
        interval: str = INTERVAL_5M,
        seed: int = 42,
        bars: list[OHLCVBar] | None = None,
        candidate_events: list[dict[str, Any]] | None = None,
        anomaly_events: list[dict[str, Any]] | None = None,
        synthetic: bool = True,
        base_price: float = 65000.0,
    ) -> str:
        """Create a new replay session. Returns session_id."""
        session_id = str(uuid.uuid4())

        if bars is None:
            if synthetic:
                all_bars: list[OHLCVBar] = []
                for sym in symbols:
                    all_bars.extend(
                        _generate_synthetic_bars(sym, start_ms, end_ms, interval, seed, base_price)
                    )
                all_bars.sort(key=lambda b: b.timestamp_ms)
                bars = all_bars
            else:
                bars = []

        session = ReplaySession(
            session_id=session_id,
            symbols=symbols,
            start_ms=start_ms,
            end_ms=end_ms,
            interval=interval,
            seed=seed,
            bars=bars or [],
            candidate_events=candidate_events or [],
            anomaly_events=anomaly_events or [],
        )

        with self._lock:
            self._sessions[session_id] = session
            self._total_sessions += 1

        logger.info(
            "[replay] session %s created: %d bars %s %s→%s",
            session_id, len(bars), interval, start_ms, end_ms,
        )
        return session_id

    def run_session(
        self,
        session_id: str,
        sim=None,
        ledger=None,
        checkpoint_every_n_bars: int = 100,
        max_bars: int | None = None,
        on_bar_callback=None,
    ) -> dict[str, Any]:
        """Run a replay session synchronously. Returns final status dict."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return {"ok": False, "error": f"session {session_id} not found"}

        if session.state == REPLAY_RUNNING:
            return {"ok": False, "error": "session already running"}

        session.state = REPLAY_RUNNING
        session.started_at_ms = int(time.time() * 1000)
        self._stop_flag.clear()

        try:
            for i, bar in enumerate(session.bars):
                if self._stop_flag.is_set():
                    session.state = REPLAY_PAUSED
                    break

                if max_bars is not None and i >= max_bars:
                    break

                session.current_bar_index = i

                mark_prices = {bar.symbol: bar.close}
                funding_rates = {bar.symbol: bar.funding_rate}

                # Process pending orders through simulator
                if sim is not None:
                    filled = sim.process_pending_orders(mark_prices, funding_rates)
                    for oid in filled:
                        session.log_event("ORDER_FILLED", {"orderId": oid, "barIndex": i})

                # Dispatch candidate events for this bar
                bar_candidates = [
                    e for e in session.candidate_events
                    if abs(e.get("timestampMs", 0) - bar.timestamp_ms) < _INTERVAL_MS.get(session.interval, 300_000)
                ]
                for cand_event in bar_candidates:
                    session.log_event("CANDIDATE_EVENT", cand_event)

                # Dispatch anomaly events
                bar_anomalies = [
                    e for e in session.anomaly_events
                    if abs(e.get("timestampMs", 0) - bar.timestamp_ms) < _INTERVAL_MS.get(session.interval, 300_000)
                ]
                for anm in bar_anomalies:
                    session.log_event("ANOMALY_EVENT", anm)

                # Checkpoint
                if checkpoint_every_n_bars > 0 and (i + 1) % checkpoint_every_n_bars == 0:
                    session.save_checkpoint(sim=sim, ledger=ledger)

                # User callback
                if on_bar_callback is not None:
                    try:
                        on_bar_callback(bar, session)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("[replay] on_bar_callback error: %s", exc)

            else:
                session.state = REPLAY_COMPLETED
                session.completed_at_ms = int(time.time() * 1000)

        except Exception as exc:  # noqa: BLE001
            session.state = REPLAY_FAILED
            session.error = str(exc)
            logger.error("[replay] session %s failed: %s", session_id, exc)

        return session.status_dict()

    def pause(self) -> None:
        self._stop_flag.set()
        logger.info("[replay] pause requested")

    def resume(self, session_id: str, sim=None, ledger=None, max_bars: int | None = None) -> dict[str, Any]:
        """Resume a paused session from current bar index."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return {"ok": False, "error": "session not found"}
        if session.state != REPLAY_PAUSED:
            return {"ok": False, "error": f"session not paused (state={session.state})"}

        # Trim bars to resume from current position
        remaining = session.bars[session.current_bar_index:]
        session.bars = session.bars  # keep original
        self._stop_flag.clear()
        session.state = REPLAY_RUNNING

        try:
            for i, bar in enumerate(session.bars[session.current_bar_index:], start=session.current_bar_index):
                if self._stop_flag.is_set():
                    session.state = REPLAY_PAUSED
                    break
                if max_bars is not None and (i - session.current_bar_index) >= max_bars:
                    break
                session.current_bar_index = i
                if sim is not None:
                    sim.process_pending_orders(
                        {bar.symbol: bar.close},
                        {bar.symbol: bar.funding_rate},
                    )
            else:
                session.state = REPLAY_COMPLETED
                session.completed_at_ms = int(time.time() * 1000)
        except Exception as exc:  # noqa: BLE001
            session.state = REPLAY_FAILED
            session.error = str(exc)

        return session.status_dict()

    def get_session(self, session_id: str) -> ReplaySession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def status(self) -> dict[str, Any]:
        with self._lock:
            active_states: dict[str, int] = {}
            for s in self._sessions.values():
                active_states[s.state] = active_states.get(s.state, 0) + 1
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "totalSessions": self._total_sessions,
            "activeSessionsCount": len(self._sessions),
            "sessionStates": active_states,
            "generatedAt": int(time.time() * 1000),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_ENGINE: ReplayEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_replay_engine() -> ReplayEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = ReplayEngine()
            logger.info("[replay] ReplayEngine initialised (researchOnly=true)")
        return _ENGINE
