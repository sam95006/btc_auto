"""Phase 5 Gate C — Accelerated Smoke Soak Framework.

RESEARCH ONLY. Runs abbreviated accelerated simulation soaks to verify
that the sim stack holds up under configurable time windows:
  - 1h  smoke (quick sanity)
  - 6h  standard soak
  - 24h daily soak
  - 72h extended soak

Each config defines:
  - duration_hours: nominal time window
  - bar_interval: replay interval
  - symbol_count: how many symbols to include
  - synthetic: whether to use synthetic data
  - max_positions_per_symbol: concurrency cap for soak
  - seed: deterministic seed

The verify function runs a short accelerated smoke (≤30 seconds wall-clock)
suitable for CI/verify scripts.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.replay import (
    INTERVAL_1M,
    INTERVAL_5M,
    INTERVAL_1H,
    REPLAY_COMPLETED,
    ReplayEngine,
    _generate_synthetic_bars,
    get_replay_engine,
)
from backend.nexus_research.simulator import (
    SIDE_LONG,
    SIDE_SHORT,
    ORDER_MARKET,
    SimulatedExchange,
    get_simulator,
    reset_simulator,
)
from backend.nexus_research.sim_ledger import get_sim_ledger, reset_sim_ledger
from backend.nexus_research.risk_engine import RiskRequest, get_risk_engine
from backend.nexus_research.capital_allocator import get_capital_allocator

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Soak profiles ─────────────────────────────────────────────────────────────
SOAK_1H = "1h"
SOAK_6H = "6h"
SOAK_24H = "24h"
SOAK_72H = "72h"
SOAK_SMOKE = "smoke"  # short accelerated smoke for verify

_SOAK_PROFILES: dict[str, dict[str, Any]] = {
    SOAK_SMOKE: {
        "duration_hours": 0.5,
        "bar_interval": INTERVAL_1M,
        "symbol_count": 2,
        "synthetic": True,
        "max_positions_per_symbol": 1,
        "seed": 42,
        "entry_every_n_bars": 10,
        "description": "Quick smoke soak (~30 seconds wall-clock)",
    },
    SOAK_1H: {
        "duration_hours": 1.0,
        "bar_interval": INTERVAL_5M,
        "symbol_count": 3,
        "synthetic": True,
        "max_positions_per_symbol": 2,
        "seed": 100,
        "entry_every_n_bars": 6,
        "description": "1-hour standard smoke soak",
    },
    SOAK_6H: {
        "duration_hours": 6.0,
        "bar_interval": INTERVAL_5M,
        "symbol_count": 5,
        "synthetic": True,
        "max_positions_per_symbol": 3,
        "seed": 200,
        "entry_every_n_bars": 12,
        "description": "6-hour standard soak",
    },
    SOAK_24H: {
        "duration_hours": 24.0,
        "bar_interval": INTERVAL_1H,
        "symbol_count": 8,
        "synthetic": True,
        "max_positions_per_symbol": 3,
        "seed": 300,
        "entry_every_n_bars": 4,
        "description": "24-hour daily soak",
    },
    SOAK_72H: {
        "duration_hours": 72.0,
        "bar_interval": INTERVAL_1H,
        "symbol_count": 10,
        "synthetic": True,
        "max_positions_per_symbol": 4,
        "seed": 400,
        "entry_every_n_bars": 6,
        "description": "72-hour extended soak",
    },
}

_DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOTUSDT", "AVAXUSDT", "MATICUSDT", "LINKUSDT",
]


@dataclass
class SoakResult:
    soak_id: str
    profile: str
    state: str
    total_bars: int
    bars_processed: int
    total_orders: int
    total_fills: int
    total_positions_opened: int
    total_positions_closed: int
    final_equity: float
    final_realised_pnl: float
    final_unrealised_pnl: float
    total_fees: float
    risk_blocks: int
    risk_allows: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    started_at_ms: int = 0
    completed_at_ms: int = 0
    wall_clock_ms: int = 0

    def verdict(self) -> str:
        """Simple PASS/FAIL based on soak integrity."""
        if self.state != "COMPLETED":
            return "FAIL"
        if self.errors:
            return "FAIL"
        if self.final_equity <= 0:
            return "FAIL"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "soakId": self.soak_id,
            "profile": self.profile,
            "state": self.state,
            "verdict": self.verdict(),
            "totalBars": self.total_bars,
            "barsProcessed": self.bars_processed,
            "totalOrders": self.total_orders,
            "totalFills": self.total_fills,
            "totalPositionsOpened": self.total_positions_opened,
            "totalPositionsClosed": self.total_positions_closed,
            "finalEquity": self.final_equity,
            "finalRealisedPnl": self.final_realised_pnl,
            "finalUnrealisedPnl": self.final_unrealised_pnl,
            "totalFees": self.total_fees,
            "riskBlocks": self.risk_blocks,
            "riskAllows": self.risk_allows,
            "errors": self.errors,
            "warnings": self.warnings,
            "startedAtMs": self.started_at_ms,
            "completedAtMs": self.completed_at_ms,
            "wallClockMs": self.wall_clock_ms,
            "researchOnly": True,
        }


class SoakFramework:
    """Runs accelerated smoke soaks against the sim stack."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._results: dict[str, SoakResult] = {}
        self._total_soaks = 0

    def run_soak(
        self,
        profile: str = SOAK_SMOKE,
        symbols: list[str] | None = None,
        isolated: bool = True,
    ) -> SoakResult:
        """Run a soak. If isolated=True uses fresh sim/ledger instances (recommended)."""
        soak_id = str(uuid.uuid4())
        cfg = _SOAK_PROFILES.get(profile, _SOAK_PROFILES[SOAK_SMOKE])
        started = int(time.time() * 1000)

        used_symbols = (symbols or _DEFAULT_SYMBOLS)[:cfg["symbol_count"]]
        seed = cfg["seed"]
        interval = cfg["bar_interval"]
        duration_hours = cfg["duration_hours"]
        entry_every = cfg["entry_every_n_bars"]

        # Build synthetic bars
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - int(duration_hours * 3_600_000)
        end_ms = now_ms

        all_bars: list[Any] = []
        for sym in used_symbols:
            bars = _generate_synthetic_bars(sym, start_ms, end_ms, interval, seed)
            all_bars.extend(bars)
        all_bars.sort(key=lambda b: b.timestamp_ms)

        # Isolated or shared sim/ledger
        if isolated:
            sim = SimulatedExchange(config={"default_leverage": 3.0, "max_open_positions": 20})
            from backend.nexus_research.sim_ledger import SimLedger
            ledger = SimLedger(initial_cash=100_000.0)
        else:
            sim = get_simulator()
            ledger = get_sim_ledger()

        risk = get_risk_engine()
        allocator = get_capital_allocator()

        errors: list[str] = []
        warnings: list[str] = []
        positions_opened = 0
        positions_closed = 0
        risk_blocks = 0
        risk_allows = 0

        try:
            for i, bar in enumerate(all_bars):
                mark_prices = {bar.symbol: bar.close}
                funding_rates = {bar.symbol: bar.funding_rate}

                # Fill pending orders
                filled = sim.process_pending_orders(mark_prices, funding_rates)

                # Close some positions periodically
                open_pos = sim.list_open_positions(symbol=bar.symbol)
                for pos in open_pos:
                    pos_age_bars = i - 0  # simplified; just close after 20 bars
                    age_key = pos.get("openedAtMs", 0)
                    if (now_ms - age_key) > 20 * 60_000:
                        pnl = sim.close_position(pos["positionId"], mark_prices)
                        if pnl is not None:
                            positions_closed += 1
                            ledger.record_position_closed(
                                position_id=pos["positionId"],
                                symbol=bar.symbol,
                                side=pos["side"],
                                qty=pos.get("qty", 0.0),
                                entry_price=pos.get("entryPrice", bar.close),
                                exit_price=bar.close,
                                realised_pnl=pnl,
                                exit_fee=pos.get("qty", 0.0) * bar.close * 5 / 10_000,
                            )

                # Submit new orders every N bars
                if i % entry_every == 0 and not sim._kill_switch:
                    side = SIDE_LONG if (i // entry_every) % 2 == 0 else SIDE_SHORT
                    fake_candidate = {"score": 65.0 + (i % 20), "side": side}
                    snap = ledger.snapshot(unrealised_pnl=sim.total_unrealised_pnl())
                    equity = snap.get("equity", 10_000.0)

                    alloc = allocator.allocate(
                        symbol=bar.symbol,
                        side=side,
                        entry_price=bar.close,
                        candidate=fake_candidate,
                        equity=equity,
                        closed_trades_count=positions_closed,
                    )

                    if alloc.suggested_qty <= 0:
                        continue

                    req = RiskRequest(
                        symbol=bar.symbol,
                        side=side,
                        qty=alloc.suggested_qty,
                        entry_price=bar.close,
                        leverage=alloc.leverage,
                        candidate=fake_candidate,
                    )
                    verdict = risk.check(req, sim=sim, ledger=ledger)
                    if verdict.allowed:
                        risk_allows += 1
                        oid = sim.submit_order(
                            bar.symbol, side, ORDER_MARKET,
                            qty=alloc.suggested_qty,
                            leverage=alloc.leverage,
                        )
                        positions_opened += 1
                    else:
                        risk_blocks += 1

        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            logger.error("[soak] soak %s error: %s", soak_id, exc)

        completed = int(time.time() * 1000)
        sim_st = sim.status()
        ledger_snap = ledger.snapshot(unrealised_pnl=sim.total_unrealised_pnl())

        result = SoakResult(
            soak_id=soak_id,
            profile=profile,
            state="COMPLETED" if not errors else "FAILED",
            total_bars=len(all_bars),
            bars_processed=len(all_bars) if not errors else 0,
            total_orders=sim_st.get("totalOrders", 0),
            total_fills=sim_st.get("totalFills", 0),
            total_positions_opened=positions_opened,
            total_positions_closed=positions_closed,
            final_equity=ledger_snap.get("equity", 0.0),
            final_realised_pnl=ledger_snap.get("totalRealisedPnl", 0.0),
            final_unrealised_pnl=ledger_snap.get("totalFees", 0.0),
            total_fees=ledger_snap.get("totalFees", 0.0),
            risk_blocks=risk_blocks,
            risk_allows=risk_allows,
            errors=errors,
            warnings=warnings,
            started_at_ms=started,
            completed_at_ms=completed,
            wall_clock_ms=completed - started,
        )

        with self._lock:
            self._results[soak_id] = result
            self._total_soaks += 1

        logger.info(
            "[soak] %s %s verdict=%s bars=%d orders=%d fills=%d time=%dms",
            soak_id, profile, result.verdict(),
            len(all_bars), sim_st.get("totalOrders", 0),
            sim_st.get("totalFills", 0), completed - started,
        )
        return result

    def run_smoke_verify(self) -> SoakResult:
        """Short accelerated smoke for verify scripts. Always isolated."""
        return self.run_soak(profile=SOAK_SMOKE, isolated=True)

    def list_results(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            results = list(self._results.values())
        results.sort(key=lambda r: r.started_at_ms, reverse=True)
        return [r.to_dict() for r in results[:limit]]

    def status(self) -> dict[str, Any]:
        with self._lock:
            latest = max(
                self._results.values(),
                key=lambda r: r.started_at_ms,
                default=None,
            )
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "totalSoaks": self._total_soaks,
            "latestVerdict": latest.verdict() if latest else None,
            "latestProfile": latest.profile if latest else None,
            "latestWallClockMs": latest.wall_clock_ms if latest else None,
            "profiles": list(_SOAK_PROFILES.keys()),
            "generatedAt": int(time.time() * 1000),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_SOAK: SoakFramework | None = None
_SOAK_LOCK = threading.Lock()


def get_soak_framework() -> SoakFramework:
    global _SOAK
    with _SOAK_LOCK:
        if _SOAK is None:
            _SOAK = SoakFramework()
            logger.info("[soak] SoakFramework initialised (researchOnly=true)")
        return _SOAK
