"""Phase 5 Gate C — Simulator-Only Risk Engine.

RESEARCH ONLY. Evaluates proposed simulated positions before they enter
the SimulatedExchange. Never touches real orders, real positions, or production
risk systems.

Verdicts:
  ALLOW_SIMULATION      — request passes all checks
  REDUCE_SIZE           — size too large; caller may rescale
  BLOCK_KILL_SWITCH     — kill switch active
  BLOCK_MAX_LEVERAGE    — leverage exceeds limit
  BLOCK_MAX_POSITION    — max open positions reached
  BLOCK_MAX_NOTIONAL    — per-symbol or portfolio notional exceeded
  BLOCK_DAILY_LOSS      — daily loss limit breached
  BLOCK_DRAWDOWN        — drawdown limit breached
  BLOCK_DUPLICATE       — identical (symbol, side) already open
  BLOCK_SPREAD          — spread too wide (stale market data guard)
  BLOCK_STALE_DATA      — market data too old
  BLOCK_MISSING_EVIDENCE — required evidence fields absent
  BLOCK_CANDIDATE_EXPIRY — candidate is expired
  BLOCK_FUNDING_CROWDING — funding rate exceeds crowding threshold
  BLOCK_CORRELATION     — correlated positions exceed sector cap
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Verdict constants ─────────────────────────────────────────────────────────
ALLOW_SIMULATION = "ALLOW_SIMULATION"
REDUCE_SIZE = "REDUCE_SIZE"
BLOCK_KILL_SWITCH = "BLOCK_KILL_SWITCH"
BLOCK_MAX_LEVERAGE = "BLOCK_MAX_LEVERAGE"
BLOCK_MAX_POSITION = "BLOCK_MAX_POSITION"
BLOCK_MAX_NOTIONAL = "BLOCK_MAX_NOTIONAL"
BLOCK_DAILY_LOSS = "BLOCK_DAILY_LOSS"
BLOCK_DRAWDOWN = "BLOCK_DRAWDOWN"
BLOCK_DUPLICATE = "BLOCK_DUPLICATE"
BLOCK_SPREAD = "BLOCK_SPREAD"
BLOCK_STALE_DATA = "BLOCK_STALE_DATA"
BLOCK_MISSING_EVIDENCE = "BLOCK_MISSING_EVIDENCE"
BLOCK_CANDIDATE_EXPIRY = "BLOCK_CANDIDATE_EXPIRY"
BLOCK_FUNDING_CROWDING = "BLOCK_FUNDING_CROWDING"
BLOCK_CORRELATION = "BLOCK_CORRELATION"

_ALLOW_VERDICTS = {ALLOW_SIMULATION, REDUCE_SIZE}

# ── Default risk config ───────────────────────────────────────────────────────
_DEFAULT_RISK_CONFIG: dict[str, Any] = {
    "max_open_positions": 10,
    "max_leverage": 10.0,
    "max_notional_per_symbol_usd": 50_000.0,
    "max_portfolio_notional_usd": 200_000.0,
    "max_sector_notional_usd": 80_000.0,
    "max_daily_loss_usd": 1_000.0,
    "max_drawdown_pct": 20.0,          # percent of peak equity
    "spread_max_bps": 15.0,            # block if spread > this
    "stale_data_age_ms": 60_000,       # block if market data older than this
    "candidate_expiry_grace_ms": 5_000, # grace period after candidate expires
    "funding_crowding_threshold_pct": 0.1,  # percent per 8h
    "required_evidence_fields": ["score", "side"],
    "allow_duplicate_same_symbol": False,
    "max_concurrent_same_symbol": 1,
    "sector_map": {},  # symbol -> sector string; used for correlation cap
}


@dataclass
class RiskRequest:
    """Input for a risk check."""
    symbol: str
    side: str                       # LONG / SHORT
    qty: float
    entry_price: float
    leverage: float
    candidate: dict[str, Any] | None = None
    market_snapshot: dict[str, Any] | None = None
    spread_bps: float | None = None
    data_age_ms: int | None = None
    funding_rate_8h_pct: float | None = None


@dataclass
class RiskVerdict:
    """Output of a risk check."""
    verdict: str
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)
    suggested_qty: float | None = None
    evaluated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "allowed": self.allowed,
            "reasons": self.reasons,
            "checks": self.checks,
            "suggestedQty": self.suggested_qty,
            "evaluatedAtMs": self.evaluated_at_ms,
            "researchOnly": True,
        }


class SimRiskEngine:
    """Simulator-only risk engine.

    Call check(request, sim_state) to get a RiskVerdict.
    sim_state must expose:
        .list_open_positions() -> list[dict]
        .total_unrealised_pnl() -> float
        ._kill_switch -> bool
    And ledger must expose:
        .snapshot() -> dict with cashBalance, equity, totalRealisedPnl
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = {**_DEFAULT_RISK_CONFIG, **(config or {})}
        self._daily_loss_usd: float = 0.0
        self._session_start_ms: int = int(time.time() * 1000)
        self._peak_equity: float = 0.0
        self._total_checks: int = 0
        self._total_allows: int = 0
        self._total_blocks: int = 0

    def check(
        self,
        request: RiskRequest,
        sim=None,   # SimulatedExchange or None
        ledger=None,  # SimLedger or None
    ) -> RiskVerdict:
        """Run all risk checks and return a verdict."""
        self._total_checks += 1
        cfg = self._config
        reasons: list[str] = []
        checks: dict[str, str] = {}
        verdict = ALLOW_SIMULATION
        suggested_qty: float | None = None

        notional = request.qty * request.entry_price

        # 1. Kill switch
        if sim is not None and getattr(sim, "_kill_switch", False):
            checks["kill_switch"] = "FAIL"
            self._total_blocks += 1
            return RiskVerdict(
                verdict=BLOCK_KILL_SWITCH, allowed=False,
                reasons=["kill switch active"], checks=checks,
            )
        checks["kill_switch"] = "OK"

        # 2. Leverage
        if request.leverage > cfg["max_leverage"]:
            checks["leverage"] = "FAIL"
            reasons.append(
                f"leverage {request.leverage:.1f}x > max {cfg['max_leverage']:.1f}x"
            )
            verdict = BLOCK_MAX_LEVERAGE
        else:
            checks["leverage"] = "OK"

        # 3. Missing evidence
        if request.candidate is not None:
            missing = [
                f for f in cfg["required_evidence_fields"]
                if f not in request.candidate
            ]
            if missing:
                checks["evidence"] = "FAIL"
                reasons.append(f"missing evidence fields: {missing}")
                if verdict == ALLOW_SIMULATION:
                    verdict = BLOCK_MISSING_EVIDENCE
            else:
                checks["evidence"] = "OK"

            # 4. Candidate expiry
            expiry = request.candidate.get("expiresAt") or request.candidate.get("expires_at")
            if expiry:
                grace = cfg["candidate_expiry_grace_ms"]
                now_ms = int(time.time() * 1000)
                if isinstance(expiry, (int, float)) and now_ms > expiry + grace:
                    checks["candidate_expiry"] = "FAIL"
                    reasons.append("candidate is expired")
                    if verdict == ALLOW_SIMULATION:
                        verdict = BLOCK_CANDIDATE_EXPIRY
                else:
                    checks["candidate_expiry"] = "OK"
        else:
            checks["evidence"] = "SKIP"
            checks["candidate_expiry"] = "SKIP"

        # 5. Stale data
        if request.data_age_ms is not None:
            if request.data_age_ms > cfg["stale_data_age_ms"]:
                checks["stale_data"] = "FAIL"
                reasons.append(
                    f"market data age {request.data_age_ms}ms > max {cfg['stale_data_age_ms']}ms"
                )
                if verdict == ALLOW_SIMULATION:
                    verdict = BLOCK_STALE_DATA
            else:
                checks["stale_data"] = "OK"
        else:
            checks["stale_data"] = "SKIP"

        # 6. Spread
        if request.spread_bps is not None:
            if request.spread_bps > cfg["spread_max_bps"]:
                checks["spread"] = "FAIL"
                reasons.append(
                    f"spread {request.spread_bps:.1f}bps > max {cfg['spread_max_bps']:.1f}bps"
                )
                if verdict == ALLOW_SIMULATION:
                    verdict = BLOCK_SPREAD
            else:
                checks["spread"] = "OK"
        else:
            checks["spread"] = "SKIP"

        # 7. Funding crowding
        if request.funding_rate_8h_pct is not None:
            threshold = cfg["funding_crowding_threshold_pct"]
            if abs(request.funding_rate_8h_pct) > threshold:
                checks["funding_crowding"] = "WARN"
                reasons.append(
                    f"funding {request.funding_rate_8h_pct:.4f}% > crowding threshold {threshold:.4f}%"
                )
                if verdict == ALLOW_SIMULATION:
                    verdict = BLOCK_FUNDING_CROWDING
            else:
                checks["funding_crowding"] = "OK"
        else:
            checks["funding_crowding"] = "SKIP"

        # From sim state
        if sim is not None:
            open_positions = sim.list_open_positions()

            # 8. Max open positions
            if len(open_positions) >= cfg["max_open_positions"]:
                checks["max_positions"] = "FAIL"
                reasons.append(
                    f"open positions {len(open_positions)} >= max {cfg['max_open_positions']}"
                )
                if verdict == ALLOW_SIMULATION:
                    verdict = BLOCK_MAX_POSITION
            else:
                checks["max_positions"] = "OK"

            # 9. Duplicate / concurrent same symbol
            same_symbol = [
                p for p in open_positions
                if p.get("symbol") == request.symbol
            ]
            if not cfg["allow_duplicate_same_symbol"] and same_symbol:
                same_side = [p for p in same_symbol if p.get("side") == request.side]
                if same_side:
                    checks["duplicate"] = "FAIL"
                    reasons.append(f"duplicate {request.symbol} {request.side} already open")
                    if verdict == ALLOW_SIMULATION:
                        verdict = BLOCK_DUPLICATE
                else:
                    checks["duplicate"] = "OK"
            elif len(same_symbol) >= cfg["max_concurrent_same_symbol"]:
                checks["duplicate"] = "FAIL"
                reasons.append(
                    f"concurrent {request.symbol} positions {len(same_symbol)} >= max"
                )
                if verdict == ALLOW_SIMULATION:
                    verdict = BLOCK_DUPLICATE
            else:
                checks["duplicate"] = "OK"

            # 10. Per-symbol notional
            existing_sym_notional = sum(
                p.get("notional", 0.0) for p in open_positions
                if p.get("symbol") == request.symbol
            )
            total_sym_notional = existing_sym_notional + notional
            if total_sym_notional > cfg["max_notional_per_symbol_usd"]:
                checks["symbol_notional"] = "FAIL"
                reasons.append(
                    f"symbol notional ${total_sym_notional:.0f} > max ${cfg['max_notional_per_symbol_usd']:.0f}"
                )
                # suggest reduced qty
                headroom = cfg["max_notional_per_symbol_usd"] - existing_sym_notional
                if headroom > 0 and request.entry_price > 0:
                    suggested_qty = round(headroom / request.entry_price, 4)
                if verdict == ALLOW_SIMULATION:
                    verdict = REDUCE_SIZE if suggested_qty and suggested_qty > 0 else BLOCK_MAX_NOTIONAL
            else:
                checks["symbol_notional"] = "OK"

            # 11. Portfolio notional
            total_portfolio_notional = sum(
                p.get("notional", 0.0) for p in open_positions
            ) + notional
            if total_portfolio_notional > cfg["max_portfolio_notional_usd"]:
                checks["portfolio_notional"] = "FAIL"
                reasons.append(
                    f"portfolio notional ${total_portfolio_notional:.0f} > max ${cfg['max_portfolio_notional_usd']:.0f}"
                )
                if verdict == ALLOW_SIMULATION:
                    verdict = BLOCK_MAX_NOTIONAL
            else:
                checks["portfolio_notional"] = "OK"

            # 12. Sector correlation
            sector_map: dict[str, str] = cfg.get("sector_map", {})
            sector = sector_map.get(request.symbol, "DEFAULT")
            sector_notional = sum(
                p.get("notional", 0.0) for p in open_positions
                if sector_map.get(p.get("symbol", ""), "DEFAULT") == sector
            ) + notional
            if sector_notional > cfg["max_sector_notional_usd"]:
                checks["correlation"] = "FAIL"
                reasons.append(
                    f"sector '{sector}' notional ${sector_notional:.0f} > max ${cfg['max_sector_notional_usd']:.0f}"
                )
                if verdict == ALLOW_SIMULATION:
                    verdict = BLOCK_CORRELATION
            else:
                checks["correlation"] = "OK"

        # 13. Daily loss + drawdown (from ledger)
        if ledger is not None:
            snap = ledger.snapshot(
                unrealised_pnl=sim.total_unrealised_pnl() if sim else 0.0
            )
            equity = snap.get("equity", 0.0)
            realised_pnl = snap.get("totalRealisedPnl", 0.0)

            # Approximate daily loss as negative realised PnL this session
            session_loss = min(0.0, realised_pnl)
            if abs(session_loss) > cfg["max_daily_loss_usd"]:
                checks["daily_loss"] = "FAIL"
                reasons.append(
                    f"daily loss ${abs(session_loss):.2f} > max ${cfg['max_daily_loss_usd']:.2f}"
                )
                if verdict == ALLOW_SIMULATION:
                    verdict = BLOCK_DAILY_LOSS
            else:
                checks["daily_loss"] = "OK"

            if equity > self._peak_equity:
                self._peak_equity = equity
            if self._peak_equity > 0:
                drawdown_pct = (self._peak_equity - equity) / self._peak_equity * 100.0
                if drawdown_pct > cfg["max_drawdown_pct"]:
                    checks["drawdown"] = "FAIL"
                    reasons.append(
                        f"drawdown {drawdown_pct:.1f}% > max {cfg['max_drawdown_pct']:.1f}%"
                    )
                    if verdict == ALLOW_SIMULATION:
                        verdict = BLOCK_DRAWDOWN
                else:
                    checks["drawdown"] = "OK"
        else:
            checks["daily_loss"] = "SKIP"
            checks["drawdown"] = "SKIP"

        allowed = verdict in _ALLOW_VERDICTS
        if allowed:
            self._total_allows += 1
        else:
            self._total_blocks += 1

        return RiskVerdict(
            verdict=verdict,
            allowed=allowed,
            reasons=reasons,
            checks=checks,
            suggested_qty=suggested_qty,
        )

    def update_config(self, patch: dict[str, Any]) -> None:
        self._config.update(patch)

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "totalChecks": self._total_checks,
            "totalAllows": self._total_allows,
            "totalBlocks": self._total_blocks,
            "peakEquity": self._peak_equity,
            "sessionStartMs": self._session_start_ms,
            "configSummary": {
                k: v for k, v in self._config.items()
                if k in (
                    "max_open_positions", "max_leverage",
                    "max_notional_per_symbol_usd", "max_portfolio_notional_usd",
                    "max_daily_loss_usd", "max_drawdown_pct",
                    "spread_max_bps", "stale_data_age_ms",
                )
            },
            "generatedAt": int(time.time() * 1000),
        }

    def reset(self) -> None:
        self._daily_loss_usd = 0.0
        self._peak_equity = 0.0
        self._total_checks = 0
        self._total_allows = 0
        self._total_blocks = 0
        self._session_start_ms = int(time.time() * 1000)


# ── Singleton ─────────────────────────────────────────────────────────────────
import threading  # noqa: E402

_RISK: SimRiskEngine | None = None
_RISK_LOCK = threading.Lock()


def get_risk_engine(config: dict[str, Any] | None = None) -> SimRiskEngine:
    global _RISK
    with _RISK_LOCK:
        if _RISK is None:
            _RISK = SimRiskEngine(config=config)
            logger.info("[risk] SimRiskEngine initialised (researchOnly=true)")
        return _RISK
