"""Phase 5 Gate C — Simulated Capital Allocator.

RESEARCH ONLY. Decides how much simulated capital to allocate to a candidate.
Never touches real funds, wallets, or production position sizing.

Strategy:
  - Conservative when sample is insufficient (< min_sample_size trades).
  - Fixed-fraction of equity with score-based scaling.
  - Hard notional cap per symbol and portfolio.
  - Outputs suggested qty (in base asset units) and margin amount.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

_DEFAULT_ALLOC_CONFIG: dict[str, Any] = {
    "equity_fraction_pct": 2.0,        # percent of equity per position baseline
    "max_fraction_pct": 5.0,           # maximum percent of equity (high confidence)
    "min_sample_conservative_fraction": 0.5,  # scale down when sample < min_sample_size
    "min_sample_size": 20,             # minimum closed trades to use full fraction
    "max_notional_per_symbol_usd": 20_000.0,
    "max_total_notional_usd": 100_000.0,
    "score_scale_min": 50.0,           # below this score → no allocation
    "score_scale_max": 90.0,           # above this → full fraction
    "default_leverage": 5.0,
}


class AllocationResult:
    """Result of a capital allocation request."""

    def __init__(
        self,
        symbol: str,
        side: str,
        suggested_qty: float,
        margin_required: float,
        notional: float,
        equity_fraction_used_pct: float,
        leverage: float,
        reason: str,
        score_used: float | None,
        conservative: bool,
    ) -> None:
        self.symbol = symbol
        self.side = side
        self.suggested_qty = suggested_qty
        self.margin_required = margin_required
        self.notional = notional
        self.equity_fraction_used_pct = equity_fraction_used_pct
        self.leverage = leverage
        self.reason = reason
        self.score_used = score_used
        self.conservative = conservative
        self.allocated_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "suggestedQty": self.suggested_qty,
            "marginRequired": self.margin_required,
            "notional": self.notional,
            "equityFractionUsedPct": self.equity_fraction_used_pct,
            "leverage": self.leverage,
            "reason": self.reason,
            "scoreUsed": self.score_used,
            "conservative": self.conservative,
            "allocatedAtMs": self.allocated_at_ms,
            "researchOnly": True,
        }


class SimCapitalAllocator:
    """Simulated capital allocator.

    Usage:
        allocator = SimCapitalAllocator()
        result = allocator.allocate(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=65000.0,
            candidate={"score": 75.0, ...},
            equity=10000.0,
            closed_trades_count=5,
        )
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = {**_DEFAULT_ALLOC_CONFIG, **(config or {})}
        self._total_allocations = 0
        self._total_conservative = 0
        self._total_zero = 0

    def allocate(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        candidate: dict[str, Any] | None = None,
        equity: float = 10_000.0,
        leverage: float | None = None,
        existing_symbol_notional: float = 0.0,
        existing_portfolio_notional: float = 0.0,
        closed_trades_count: int = 0,
    ) -> AllocationResult:
        """Compute simulated allocation. Returns AllocationResult."""
        cfg = self._config
        self._total_allocations += 1

        score = float((candidate or {}).get("score", 60.0))
        _lev = float(leverage or cfg["default_leverage"])

        # Score gate
        if score < cfg["score_scale_min"]:
            self._total_zero += 1
            return AllocationResult(
                symbol=symbol, side=side, suggested_qty=0.0,
                margin_required=0.0, notional=0.0,
                equity_fraction_used_pct=0.0, leverage=_lev,
                reason=f"score {score:.1f} below minimum {cfg['score_scale_min']:.1f}",
                score_used=score, conservative=False,
            )

        # Base fraction (score-scaled between min and max)
        score_range = cfg["score_scale_max"] - cfg["score_scale_min"]
        score_norm = min(1.0, (score - cfg["score_scale_min"]) / max(score_range, 1.0))
        frac_range = cfg["max_fraction_pct"] - cfg["equity_fraction_pct"]
        base_frac_pct = cfg["equity_fraction_pct"] + score_norm * frac_range

        # Conservative scaling when sample is insufficient
        conservative = closed_trades_count < cfg["min_sample_size"]
        if conservative:
            base_frac_pct *= cfg["min_sample_conservative_fraction"]
            self._total_conservative += 1

        target_notional = equity * base_frac_pct / 100.0

        # Cap per-symbol
        remaining_sym = cfg["max_notional_per_symbol_usd"] - existing_symbol_notional
        target_notional = min(target_notional, remaining_sym)

        # Cap portfolio
        remaining_port = cfg["max_total_notional_usd"] - existing_portfolio_notional
        target_notional = min(target_notional, remaining_port)

        target_notional = max(0.0, target_notional)

        if entry_price <= 0 or target_notional <= 0:
            self._total_zero += 1
            return AllocationResult(
                symbol=symbol, side=side, suggested_qty=0.0,
                margin_required=0.0, notional=0.0,
                equity_fraction_used_pct=0.0, leverage=_lev,
                reason="zero notional after caps",
                score_used=score, conservative=conservative,
            )

        suggested_qty = round(target_notional / entry_price, 6)
        margin_required = target_notional / _lev
        actual_frac_pct = (target_notional / equity * 100.0) if equity > 0 else 0.0

        return AllocationResult(
            symbol=symbol,
            side=side,
            suggested_qty=suggested_qty,
            margin_required=margin_required,
            notional=target_notional,
            equity_fraction_used_pct=actual_frac_pct,
            leverage=_lev,
            reason=(
                f"score={score:.1f} frac={base_frac_pct:.2f}% "
                f"{'[conservative]' if conservative else ''}"
            ).strip(),
            score_used=score,
            conservative=conservative,
        )

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "totalAllocations": self._total_allocations,
            "totalConservative": self._total_conservative,
            "totalZero": self._total_zero,
            "config": {
                k: v for k, v in self._config.items()
                if k in (
                    "equity_fraction_pct", "max_fraction_pct",
                    "min_sample_size", "max_notional_per_symbol_usd",
                    "score_scale_min", "score_scale_max",
                )
            },
            "generatedAt": int(time.time() * 1000),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_ALLOC: SimCapitalAllocator | None = None
_ALLOC_LOCK = threading.Lock()


def get_capital_allocator(config: dict[str, Any] | None = None) -> SimCapitalAllocator:
    global _ALLOC
    with _ALLOC_LOCK:
        if _ALLOC is None:
            _ALLOC = SimCapitalAllocator(config=config)
            logger.info("[allocator] SimCapitalAllocator initialised (researchOnly=true)")
        return _ALLOC
