"""Lightweight Binance kline momentum research (no external QC dependency)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from config.backtest_config import (
    KLINE_BACKTEST_ENABLED,
    KLINE_FEE_BPS_PER_SIDE,
    KLINE_INTERVAL,
    KLINE_LOOKBACK,
    KLINE_MIN_BARS,
    KLINE_MIN_EDGE_SCORE,
    KLINE_SLIPPAGE_BPS,
)


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return default


def _parse_closes(klines: List) -> List[float]:
    closes = []
    for row in klines or []:
        if isinstance(row, (list, tuple)) and len(row) >= 5:
            closes.append(_safe_float(row[4]))
        elif isinstance(row, dict):
            closes.append(_safe_float(row.get("close")))
    return [price for price in closes if price > 0]


class KlineBacktestEngine:
    """
    Score proposed direction against recent momentum on Binance klines.
    Uses public/signed kline API only — fits single-exchange testnet scope.
    """

    def __init__(self, futures_client=None):
        self.futures_client = futures_client

    def evaluate(
        self,
        symbol: str,
        side: str,
        *,
        interval: Optional[str] = None,
        lookback: Optional[int] = None,
    ) -> Dict[str, Any]:
        symbol = str(symbol or "").upper()
        side = str(side or "").upper()
        if not KLINE_BACKTEST_ENABLED:
            return {
                "stage": "kline_research",
                "approved": True,
                "score": 0.6,
                "reason": "kline_research_disabled",
                "edge_score": None,
            }
        if not self.futures_client or not symbol:
            return {
                "stage": "kline_research",
                "approved": True,
                "score": 0.55,
                "reason": "kline_client_unavailable_bootstrap",
                "edge_score": None,
            }

        interval = interval or KLINE_INTERVAL
        lookback = int(lookback or KLINE_LOOKBACK)
        try:
            klines = self.futures_client.get_klines(symbol, interval=interval, limit=lookback)
        except Exception as exc:
            return {
                "stage": "kline_research",
                "approved": True,
                "score": 0.5,
                "reason": f"kline_fetch_failed_bootstrap:{exc.__class__.__name__}",
                "edge_score": None,
            }

        closes = _parse_closes(klines)
        if len(closes) < KLINE_MIN_BARS:
            return {
                "stage": "kline_research",
                "approved": True,
                "score": 0.55,
                "reason": "insufficient_kline_bars_bootstrap",
                "edge_score": None,
                "bar_count": len(closes),
            }

        wins = 0
        samples = 0
        cost_bps = (KLINE_FEE_BPS_PER_SIDE + KLINE_SLIPPAGE_BPS) * 2.0
        horizon = 3
        for index in range(5, len(closes) - horizon):
            momentum = closes[index] - closes[index - 5]
            future_move = closes[index + horizon] - closes[index]
            if side == "BUY":
                aligned = momentum > 0 and future_move > 0
            else:
                aligned = momentum < 0 and future_move < 0
            gross_bps = abs(future_move / closes[index]) * 10000.0 if closes[index] > 0 else 0.0
            net_positive = gross_bps > cost_bps if aligned else False
            if aligned and net_positive:
                wins += 1
            elif not aligned and future_move * (1 if side == "BUY" else -1) < 0:
                wins += 1
            samples += 1

        edge_score = wins / samples if samples else 0.5
        approved = edge_score >= KLINE_MIN_EDGE_SCORE
        return {
            "stage": "kline_research",
            "approved": approved,
            "score": round(min(0.95, max(0.15, edge_score)), 4),
            "reason": "kline_edge_ok" if approved else "kline_edge_below_threshold",
            "edge_score": round(edge_score, 4),
            "bar_count": len(closes),
            "interval": interval,
            "fee_slippage_bps_assumed": round(cost_bps, 2),
        }
