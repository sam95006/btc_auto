"""Phase 6 Gate D — Research Performance Service.

Aggregates simulation/paper trading metrics across separate data streams.

CRITICAL: Streams MUST NOT be merged into one curve:
  LIVE_PAPER       — autonomous paper positions from paper_controller
  SHADOW           — shadow/dry-run records (no real sim positions)
  REPLAY           — historical replay soak results
  MANUAL_VALIDATION — operator-triggered manual research cases

Metrics per stream:
  - Cases, decisions by status, sim entries
  - Open / closed positions
  - PnL: gross, net, fees, slippage (estimated), funding
  - Win rate, expectancy, profit factor
  - Max drawdown, MFE/MAE proxy, average hold time
  - Risk-block effectiveness ratio
  - Sample size + uncertainty label

All outputs: researchOnly=true, privateApi=false.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Stream identifiers ─────────────────────────────────────────────────────────
STREAM_LIVE_PAPER = "LIVE_PAPER"
STREAM_SHADOW = "SHADOW"
STREAM_REPLAY = "REPLAY"
STREAM_MANUAL_VALIDATION = "MANUAL_VALIDATION"
_ALL_STREAMS = (STREAM_LIVE_PAPER, STREAM_SHADOW, STREAM_REPLAY, STREAM_MANUAL_VALIDATION)

# ── Uncertainty thresholds (sample size) ──────────────────────────────────────
_SAMPLE_UNCERTAIN = 10    # <10 → "INSUFFICIENT"
_SAMPLE_LOW = 30          # <30 → "LOW"
_SAMPLE_MODERATE = 100    # <100 → "MODERATE"
# ≥100 → "ADEQUATE"


def _uncertainty_label(n: int) -> str:
    if n < _SAMPLE_UNCERTAIN:
        return "INSUFFICIENT"
    if n < _SAMPLE_LOW:
        return "LOW"
    if n < _SAMPLE_MODERATE:
        return "MODERATE"
    return "ADEQUATE"


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0.0 else default


# ── Stream metrics dataclass ───────────────────────────────────────────────────

class StreamMetrics:
    """Aggregated metrics for one stream."""

    def __init__(self, stream: str) -> None:
        self.stream = stream
        self.reset()

    def reset(self) -> None:
        # Case / decision counts
        self.total_cases: int = 0
        self.decisions_by_status: dict[str, int] = {}
        self.sim_entries: int = 0

        # Position counts
        self.open_positions: int = 0
        self.closed_positions: int = 0

        # PnL components
        self.pnl_gross: float = 0.0     # sum of raw PnL before costs
        self.pnl_net: float = 0.0       # gross - fees - slippage - funding
        self.total_fees: float = 0.0
        self.total_slippage: float = 0.0
        self.total_funding: float = 0.0

        # Trade outcomes (closed only)
        self.winners: int = 0
        self.losers: int = 0
        self.gross_profit: float = 0.0
        self.gross_loss: float = 0.0

        # Hold times (ms)
        self.hold_times_ms: list[float] = []

        # MFE/MAE proxies (recorded per closed position)
        self.mfe_list: list[float] = []
        self.mae_list: list[float] = []

        # Equity curve for drawdown
        self.equity_curve: list[float] = []

        # Risk blocks
        self.risk_block_count: int = 0
        self.risk_allow_count: int = 0

        # Sector / regime / side breakdowns
        self.by_sector: dict[str, dict[str, float]] = {}
        self.by_regime: dict[str, dict[str, float]] = {}
        self.by_side: dict[str, dict[str, float]] = {}

        self._updated_at_ms: int = int(time.time() * 1000)

    def ingest_closed_position(
        self,
        pnl_gross: float,
        fees: float = 0.0,
        slippage: float = 0.0,
        funding: float = 0.0,
        hold_ms: float = 0.0,
        mfe: float | None = None,
        mae: float | None = None,
        sector: str = "UNKNOWN",
        regime: str = "UNKNOWN",
        side: str = "LONG",
    ) -> None:
        """Record one closed position."""
        pnl_net = pnl_gross - fees - slippage - funding
        self.closed_positions += 1
        self.sim_entries += 1
        self.pnl_gross += pnl_gross
        self.pnl_net += pnl_net
        self.total_fees += fees
        self.total_slippage += slippage
        self.total_funding += funding
        if pnl_net > 0:
            self.winners += 1
            self.gross_profit += pnl_net
        else:
            self.losers += 1
            self.gross_loss += abs(pnl_net)
        if hold_ms > 0:
            self.hold_times_ms.append(hold_ms)
        if mfe is not None:
            self.mfe_list.append(mfe)
        if mae is not None:
            self.mae_list.append(mae)

        # Update running equity (simplified)
        last_eq = self.equity_curve[-1] if self.equity_curve else 10_000.0
        self.equity_curve.append(last_eq + pnl_net)

        # Dimension breakdowns
        for dim_dict, key in (
            (self.by_sector, sector),
            (self.by_regime, regime),
            (self.by_side, side),
        ):
            if key not in dim_dict:
                dim_dict[key] = {"count": 0, "pnl_net": 0.0, "winners": 0}
            dim_dict[key]["count"] += 1
            dim_dict[key]["pnl_net"] += pnl_net
            dim_dict[key]["winners"] += 1 if pnl_net > 0 else 0

        self._updated_at_ms = int(time.time() * 1000)

    def ingest_risk_event(self, allowed: bool) -> None:
        if allowed:
            self.risk_allow_count += 1
        else:
            self.risk_block_count += 1

    def ingest_case(self, decision_status: str | None) -> None:
        self.total_cases += 1
        ds = decision_status or "UNKNOWN"
        self.decisions_by_status[ds] = self.decisions_by_status.get(ds, 0) + 1

    def _max_drawdown(self) -> float:
        """Compute max drawdown from equity curve."""
        if len(self.equity_curve) < 2:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def closed_count(self) -> int:
        return self.closed_positions

    @property
    def win_rate(self) -> float:
        total = self.winners + self.losers
        return _safe_div(self.winners, total)

    @property
    def expectancy(self) -> float:
        """Average PnL per closed trade."""
        total = self.winners + self.losers
        return _safe_div(self.pnl_net, total)

    @property
    def profit_factor(self) -> float:
        return _safe_div(self.gross_profit, self.gross_loss, default=float("inf") if self.gross_profit > 0 else 0.0)

    @property
    def avg_hold_time_min(self) -> float:
        if not self.hold_times_ms:
            return 0.0
        return (sum(self.hold_times_ms) / len(self.hold_times_ms)) / 60_000.0

    @property
    def avg_mfe(self) -> float:
        return sum(self.mfe_list) / len(self.mfe_list) if self.mfe_list else 0.0

    @property
    def avg_mae(self) -> float:
        return sum(self.mae_list) / len(self.mae_list) if self.mae_list else 0.0

    @property
    def risk_block_effectiveness(self) -> float:
        """Ratio of blocked to total risk decisions."""
        total = self.risk_block_count + self.risk_allow_count
        return _safe_div(self.risk_block_count, total)

    def sample_size_label(self) -> str:
        return _uncertainty_label(self.closed_count)

    def to_summary(self) -> dict[str, Any]:
        pf = self.profit_factor
        return {
            "stream": self.stream,
            "sampleSize": self.closed_count,
            "uncertaintyLabel": self.sample_size_label(),
            "totalCases": self.total_cases,
            "decisionsByStatus": dict(self.decisions_by_status),
            "simEntries": self.sim_entries,
            "openPositions": self.open_positions,
            "closedPositions": self.closed_positions,
            "pnlGross": round(self.pnl_gross, 4),
            "pnlNet": round(self.pnl_net, 4),
            "totalFees": round(self.total_fees, 4),
            "totalSlippage": round(self.total_slippage, 4),
            "totalFunding": round(self.total_funding, 4),
            "winners": self.winners,
            "losers": self.losers,
            "winRate": round(self.win_rate, 4),
            "expectancy": round(self.expectancy, 4),
            "profitFactor": round(pf, 4) if not math.isinf(pf) else None,
            "maxDrawdownPct": round(self._max_drawdown() * 100, 2),
            "avgMfePct": round(self.avg_mfe * 100, 4),
            "avgMaePct": round(self.avg_mae * 100, 4),
            "avgHoldTimeMin": round(self.avg_hold_time_min, 1),
            "riskBlockCount": self.risk_block_count,
            "riskAllowCount": self.risk_allow_count,
            "riskBlockEffectiveness": round(self.risk_block_effectiveness, 4),
            "updatedAtMs": self._updated_at_ms,
            "researchOnly": True,
            "privateApi": False,
        }


# ── Performance service ────────────────────────────────────────────────────────

class ResearchPerformanceService:
    """Aggregate and serve performance metrics for all research streams.

    Streams are NEVER merged — each has its own StreamMetrics instance.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._streams: dict[str, StreamMetrics] = {
            s: StreamMetrics(s) for s in _ALL_STREAMS
        }
        self._created_at_ms = int(time.time() * 1000)

    def _hydrate_from_storage(self) -> None:
        """Load existing records from storage into stream metrics."""
        try:
            from backend.nexus_research.storage import get_research_store
            store = get_research_store()

            # Paper positions → LIVE_PAPER stream
            paper_positions = store.query("paper_positions", limit=500)
            pm = self._streams[STREAM_LIVE_PAPER]
            for pos in paper_positions:
                ds = pos.get("decisionStatus")
                pm.ingest_case(ds)
                if pos.get("state") == "CLOSED":
                    pm.ingest_closed_position(
                        pnl_gross=float(pos.get("realisedPnl") or 0.0),
                        fees=float(pos.get("exitFee") or 0.0) + float(pos.get("entryFee") or 0.0),
                        funding=float(pos.get("totalFunding") or 0.0),
                        hold_ms=float(pos.get("holdMs") or 0.0),
                        side=str(pos.get("side") or "LONG"),
                    )
                elif pos.get("state") == "OPEN":
                    pm.open_positions += 1

            # Shadow runs → SHADOW stream
            shadow_runs = store.query("paper_shadow_runs", limit=500)
            sm = self._streams[STREAM_SHADOW]
            for run in shadow_runs:
                sm.total_cases += 1
                sm.risk_allow_count += 1  # shadow = allowed-but-dry-run

            # Research decisions → MANUAL_VALIDATION stream
            decisions = store.query("research_decisions", limit=500)
            mm = self._streams[STREAM_MANUAL_VALIDATION]
            for d in decisions:
                ds = d.get("decisionStatus")
                mm.ingest_case(ds)

        except Exception as exc:  # noqa: BLE001
            logger.debug("[performance_service] hydration error: %s", exc)

    def _hydrate_soak_results(self) -> None:
        """Load soak results → REPLAY stream."""
        try:
            from backend.nexus_research.soak import get_soak_framework
            soak = get_soak_framework()
            results = soak.list_results(limit=100)
            rm = self._streams[STREAM_REPLAY]
            for r in results:
                rm.risk_block_count += int(r.get("riskBlocks") or 0)
                rm.risk_allow_count += int(r.get("riskAllows") or 0)
                rm.closed_positions += int(r.get("totalPositionsClosed") or 0)
                rm.open_positions = 0  # soak runs are final
                rm.total_fees += float(r.get("totalFees") or 0.0)
                rm.pnl_gross += float(r.get("finalRealisedPnl") or 0.0)
                rm.sim_entries += int(r.get("totalPositionsOpened") or 0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[performance_service] soak hydration error: %s", exc)

    def refresh(self) -> None:
        """Re-hydrate metrics from storage (called on each summary request)."""
        with self._lock:
            for s in _ALL_STREAMS:
                self._streams[s].reset()
        self._hydrate_from_storage()
        self._hydrate_soak_results()

    def summary(self) -> dict[str, Any]:
        """Return full performance summary for all streams."""
        self.refresh()
        with self._lock:
            streams = {s: self._streams[s].to_summary() for s in _ALL_STREAMS}
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "streams": streams,
            "streamIds": list(_ALL_STREAMS),
            "note": "Streams MUST NOT be merged. Each stream is independently validated.",
            "generatedAt": int(time.time() * 1000),
        }

    def by_sector(self) -> dict[str, Any]:
        self.refresh()
        with self._lock:
            result: dict[str, Any] = {}
            for stream_id in _ALL_STREAMS:
                sm = self._streams[stream_id]
                result[stream_id] = {
                    sector: {
                        "count": v["count"],
                        "pnlNet": round(v["pnl_net"], 4),
                        "winRate": round(
                            _safe_div(v["winners"], v["count"]), 4
                        ) if v["count"] else 0.0,
                    }
                    for sector, v in sm.by_sector.items()
                }
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "bySector": result,
            "generatedAt": int(time.time() * 1000),
        }

    def by_regime(self) -> dict[str, Any]:
        self.refresh()
        with self._lock:
            result: dict[str, Any] = {}
            for stream_id in _ALL_STREAMS:
                sm = self._streams[stream_id]
                result[stream_id] = {
                    regime: {
                        "count": v["count"],
                        "pnlNet": round(v["pnl_net"], 4),
                        "winRate": round(
                            _safe_div(v["winners"], v["count"]), 4
                        ) if v["count"] else 0.0,
                    }
                    for regime, v in sm.by_regime.items()
                }
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "byRegime": result,
            "generatedAt": int(time.time() * 1000),
        }

    def by_side(self) -> dict[str, Any]:
        self.refresh()
        with self._lock:
            result: dict[str, Any] = {}
            for stream_id in _ALL_STREAMS:
                sm = self._streams[stream_id]
                result[stream_id] = {
                    side: {
                        "count": v["count"],
                        "pnlNet": round(v["pnl_net"], 4),
                        "winRate": round(
                            _safe_div(v["winners"], v["count"]), 4
                        ) if v["count"] else 0.0,
                    }
                    for side, v in sm.by_side.items()
                }
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "bySide": result,
            "generatedAt": int(time.time() * 1000),
        }

    def risk_blocks(self) -> dict[str, Any]:
        self.refresh()
        with self._lock:
            result: dict[str, Any] = {}
            for stream_id in _ALL_STREAMS:
                sm = self._streams[stream_id]
                total = sm.risk_block_count + sm.risk_allow_count
                result[stream_id] = {
                    "riskBlockCount": sm.risk_block_count,
                    "riskAllowCount": sm.risk_allow_count,
                    "total": total,
                    "blockRate": round(_safe_div(sm.risk_block_count, total), 4),
                    "effectiveness": round(sm.risk_block_effectiveness, 4),
                    "uncertaintyLabel": _uncertainty_label(total),
                }
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "riskBlocks": result,
            "generatedAt": int(time.time() * 1000),
        }

    def calibration(self) -> dict[str, Any]:
        """Return calibration metrics (win rate vs expectancy per stream)."""
        self.refresh()
        with self._lock:
            result: dict[str, Any] = {}
            for stream_id in _ALL_STREAMS:
                sm = self._streams[stream_id]
                result[stream_id] = {
                    "sampleSize": sm.closed_count,
                    "uncertaintyLabel": sm.sample_size_label(),
                    "winRate": round(sm.win_rate, 4),
                    "expectancy": round(sm.expectancy, 4),
                    "profitFactor": (
                        round(sm.profit_factor, 4) if not math.isinf(sm.profit_factor) else None
                    ),
                    "note": (
                        "Sample size insufficient for calibration conclusions"
                        if sm.closed_count < _SAMPLE_UNCERTAIN
                        else "Calibration data"
                    ),
                }
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "calibration": result,
            "generatedAt": int(time.time() * 1000),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_SERVICE: ResearchPerformanceService | None = None
_SERVICE_LOCK = threading.Lock()


def get_performance_service() -> ResearchPerformanceService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = ResearchPerformanceService()
            logger.info("[performance_service] ResearchPerformanceService initialised (researchOnly=true)")
        return _SERVICE
