"""NEXUS Phase 6.4 — Order Flow Analysis.

Provides:
- OrderBookState  — snapshot + delta processing with sequence gap detection,
                    resnapshot flag, bounded depth, imbalance, bid/ask depth,
                    liquidity walls.
- TradeFlow       — taker buy/sell volumes, CVD (cumulative + windowed),
                    large trade count.

Quality levels:
  COMPLETE    — full data, no gaps
  DEGRADED    — data present but with gaps or partial info
  UNAVAILABLE — missing / null value
  EXPERIMENTAL — iceberg/absorption/footprint features

Missing values: value=None, quality=UNAVAILABLE, reason=<str>
"""
from __future__ import annotations

import collections
import datetime
import threading
import time
from typing import Any, Optional

# Maximum order book levels retained (default 25)
DEFAULT_MAX_LEVELS = 25

# CVD window (number of recent trades for windowed CVD)
DEFAULT_CVD_WINDOW = 500

# Large trade threshold multiplier (times mean trade size)
DEFAULT_LARGE_TRADE_MULTIPLIER = 5.0


def _utc_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _unavail(reason: str) -> dict[str, Any]:
    return {"value": None, "quality": "UNAVAILABLE", "reason": reason}


def _experimental(reason: str) -> dict[str, Any]:
    return {"value": None, "quality": "EXPERIMENTAL", "reason": reason}


# ─────────────────────────────────────────────────────────────────────────────
# OrderBookState
# ─────────────────────────────────────────────────────────────────────────────

class OrderBookState:
    """Maintains a bounded order book view with gap detection and delta processing.

    Parameters
    ----------
    max_levels:
        Maximum number of bid/ask price levels to retain.
    symbol:
        Optional symbol identifier for logging.
    """

    def __init__(self, max_levels: int = DEFAULT_MAX_LEVELS, symbol: str = "") -> None:
        self._lock = threading.RLock()
        self.max_levels = max_levels
        self.symbol = symbol
        self._bids: dict[float, float] = {}   # price -> qty
        self._asks: dict[float, float] = {}
        self._last_seq: Optional[int] = None
        self._needs_resnapshot: bool = False
        self._snapshot_count: int = 0
        self._delta_count: int = 0
        self._gap_count: int = 0
        self._last_update_ts: Optional[float] = None

    # ── Snapshot application ──────────────────────────────────────────────────

    def apply_snapshot(
        self,
        bids: list[list[float]],
        asks: list[list[float]],
        seq: Optional[int] = None,
        ts: Optional[float] = None,
    ) -> None:
        """Replace book with a full snapshot. Clears resnapshot flag."""
        with self._lock:
            self._bids = {float(p): float(q) for p, q in bids}
            self._asks = {float(p): float(q) for p, q in asks}
            self._trim()
            self._last_seq = seq
            self._needs_resnapshot = False
            self._snapshot_count += 1
            self._last_update_ts = ts or time.time()

    # ── Delta application ─────────────────────────────────────────────────────

    def apply_delta(
        self,
        bids: list[list[float]],
        asks: list[list[float]],
        seq: Optional[int] = None,
        ts: Optional[float] = None,
    ) -> dict[str, Any]:
        """Apply a delta update. Returns a status dict including gap_detected."""
        with self._lock:
            gap_detected = False
            if seq is not None and self._last_seq is not None:
                expected_next = self._last_seq + 1
                if seq > expected_next:
                    gap_detected = True
                    self._gap_count += 1
                    self._needs_resnapshot = True
            for p, q in bids:
                price = float(p)
                qty = float(q)
                if qty == 0.0:
                    self._bids.pop(price, None)
                else:
                    self._bids[price] = qty
            for p, q in asks:
                price = float(p)
                qty = float(q)
                if qty == 0.0:
                    self._asks.pop(price, None)
                else:
                    self._asks[price] = qty
            self._trim()
            if seq is not None:
                self._last_seq = seq
            self._delta_count += 1
            self._last_update_ts = ts or time.time()
            return {"gap_detected": gap_detected, "needs_resnapshot": self._needs_resnapshot}

    # ── Derived metrics ───────────────────────────────────────────────────────

    def _trim(self) -> None:
        """Retain only top N levels by price proximity."""
        if len(self._bids) > self.max_levels:
            top = sorted(self._bids.keys(), reverse=True)[: self.max_levels]
            self._bids = {p: self._bids[p] for p in top}
        if len(self._asks) > self.max_levels:
            top = sorted(self._asks.keys())[: self.max_levels]
            self._asks = {p: self._asks[p] for p in top}

    def top_of_book(self) -> dict[str, Any]:
        """Best bid/ask prices and quantities."""
        with self._lock:
            if not self._bids or not self._asks:
                return _unavail("empty_book")
            best_bid_price = max(self._bids.keys())
            best_ask_price = min(self._asks.keys())
            return {
                "bestBid": best_bid_price,
                "bestBidQty": self._bids[best_bid_price],
                "bestAsk": best_ask_price,
                "bestAskQty": self._asks[best_ask_price],
                "spread": best_ask_price - best_bid_price,
                "midPrice": (best_bid_price + best_ask_price) / 2.0,
                "quality": "DEGRADED" if self._needs_resnapshot else "COMPLETE",
                "needsResnapshot": self._needs_resnapshot,
            }

    def imbalance(self, levels: int = 5) -> dict[str, Any]:
        """Order book imbalance: (bid_depth - ask_depth) / (bid_depth + ask_depth)."""
        with self._lock:
            if not self._bids or not self._asks:
                return _unavail("empty_book")
            top_bids = sorted(self._bids.keys(), reverse=True)[:levels]
            top_asks = sorted(self._asks.keys())[:levels]
            bid_depth = sum(self._bids[p] for p in top_bids)
            ask_depth = sum(self._asks[p] for p in top_asks)
            total = bid_depth + ask_depth
            imb = (bid_depth - ask_depth) / total if total > 0 else 0.0
            quality = "DEGRADED" if self._needs_resnapshot else "COMPLETE"
            return {
                "value": imb,
                "bidDepth": bid_depth,
                "askDepth": ask_depth,
                "levels": levels,
                "quality": quality,
                "needsResnapshot": self._needs_resnapshot,
            }

    def bid_depth(self, levels: int = 5) -> dict[str, Any]:
        """Total bid quantity for top N levels."""
        with self._lock:
            if not self._bids:
                return _unavail("empty_bids")
            top = sorted(self._bids.keys(), reverse=True)[:levels]
            depth = sum(self._bids[p] for p in top)
            return {"value": depth, "levels": levels,
                    "quality": "DEGRADED" if self._needs_resnapshot else "COMPLETE"}

    def ask_depth(self, levels: int = 5) -> dict[str, Any]:
        """Total ask quantity for top N levels."""
        with self._lock:
            if not self._asks:
                return _unavail("empty_asks")
            top = sorted(self._asks.keys())[:levels]
            depth = sum(self._asks[p] for p in top)
            return {"value": depth, "levels": levels,
                    "quality": "DEGRADED" if self._needs_resnapshot else "COMPLETE"}

    def liquidity_walls(self, threshold_multiplier: float = 3.0) -> dict[str, Any]:
        """Detect large clusters of liquidity (qty >= multiplier * mean) as walls."""
        with self._lock:
            if not self._bids and not self._asks:
                return _unavail("empty_book")
            bid_walls: list[dict[str, float]] = []
            ask_walls: list[dict[str, float]] = []
            if self._bids:
                bid_mean = sum(self._bids.values()) / len(self._bids)
                for p, q in sorted(self._bids.items(), reverse=True):
                    if q >= bid_mean * threshold_multiplier:
                        bid_walls.append({"price": p, "qty": q})
            if self._asks:
                ask_mean = sum(self._asks.values()) / len(self._asks)
                for p, q in sorted(self._asks.items()):
                    if q >= ask_mean * threshold_multiplier:
                        ask_walls.append({"price": p, "qty": q})
            return {
                "bidWalls": bid_walls,
                "askWalls": ask_walls,
                "threshold_multiplier": threshold_multiplier,
                "quality": "DEGRADED" if self._needs_resnapshot else "COMPLETE",
            }

    def snapshot(self) -> dict[str, Any]:
        """Full current state snapshot."""
        with self._lock:
            sorted_bids = sorted(self._bids.items(), reverse=True)[:self.max_levels]
            sorted_asks = sorted(self._asks.items())[:self.max_levels]
            return {
                "symbol": self.symbol,
                "bids": [[p, q] for p, q in sorted_bids],
                "asks": [[p, q] for p, q in sorted_asks],
                "lastSeq": self._last_seq,
                "needsResnapshot": self._needs_resnapshot,
                "snapshotCount": self._snapshot_count,
                "deltaCount": self._delta_count,
                "gapCount": self._gap_count,
                "lastUpdateTs": self._last_update_ts,
                "maxLevels": self.max_levels,
                "bidLevels": len(self._bids),
                "askLevels": len(self._asks),
            }

    # ── Experimental features (iceberg / absorption / footprint) ─────────────

    def iceberg_detection(self) -> dict[str, Any]:
        """EXPERIMENTAL — iceberg order detection (not formal signal)."""
        return _experimental("iceberg_detection_not_implemented: requires trade-by-trade footprint data")

    def absorption_analysis(self) -> dict[str, Any]:
        """EXPERIMENTAL — absorption / exhaustion analysis."""
        return _experimental("absorption_analysis_not_implemented: requires tick-level data")

    def footprint(self) -> dict[str, Any]:
        """EXPERIMENTAL — footprint chart data (bid/ask volume per price level per bar)."""
        return _experimental("footprint_not_implemented: requires tick-level trade-to-level mapping")

    def heatmap_data(self) -> dict[str, Any]:
        """EXPERIMENTAL — order book heatmap history."""
        return _experimental("heatmap_not_implemented: requires historical order book snapshots")


# ─────────────────────────────────────────────────────────────────────────────
# TradeFlow
# ─────────────────────────────────────────────────────────────────────────────

class TradeFlow:
    """Tracks taker buy/sell volumes, cumulative volume delta (CVD), large trades.

    Parameters
    ----------
    cvd_window:
        Number of most recent trades to include in windowed CVD.
    large_trade_multiplier:
        A trade is "large" if its qty >= multiplier × recent mean qty.
    """

    def __init__(
        self,
        cvd_window: int = DEFAULT_CVD_WINDOW,
        large_trade_multiplier: float = DEFAULT_LARGE_TRADE_MULTIPLIER,
    ) -> None:
        self._lock = threading.RLock()
        self.cvd_window = cvd_window
        self.large_trade_multiplier = large_trade_multiplier
        # Each trade: {"side": "buy"|"sell", "qty": float, "price": float, "ts": float}
        self._trades: collections.deque[dict[str, Any]] = collections.deque(maxlen=cvd_window)
        self._cumulative_buy_vol: float = 0.0
        self._cumulative_sell_vol: float = 0.0
        self._large_trade_count: int = 0
        self._trade_count: int = 0

    def add_trade(
        self,
        side: str,
        qty: float,
        price: float,
        ts: Optional[float] = None,
    ) -> None:
        """Add a single taker trade. side ∈ {'buy', 'sell'}."""
        side_norm = side.lower().strip()
        if side_norm not in ("buy", "sell"):
            return
        trade: dict[str, Any] = {
            "side": side_norm,
            "qty": float(qty),
            "price": float(price),
            "ts": ts or time.time(),
        }
        with self._lock:
            self._trades.append(trade)
            if side_norm == "buy":
                self._cumulative_buy_vol += float(qty)
            else:
                self._cumulative_sell_vol += float(qty)
            self._trade_count += 1
            # Large trade check against window mean
            if len(self._trades) >= 10:
                mean_qty = sum(t["qty"] for t in self._trades) / len(self._trades)
                if float(qty) >= mean_qty * self.large_trade_multiplier:
                    self._large_trade_count += 1

    def add_trades(self, trades: list[dict[str, Any]]) -> None:
        """Bulk add. Each item: {side, qty, price, ts?}."""
        for t in trades:
            self.add_trade(
                side=str(t.get("side") or ""),
                qty=float(t.get("qty") or 0),
                price=float(t.get("price") or 0),
                ts=t.get("ts"),
            )

    def cumulative_cvd(self) -> dict[str, Any]:
        """Cumulative Volume Delta = total buy volume - total sell volume."""
        with self._lock:
            cvd = self._cumulative_buy_vol - self._cumulative_sell_vol
            return {
                "value": cvd,
                "buyVolume": self._cumulative_buy_vol,
                "sellVolume": self._cumulative_sell_vol,
                "quality": "COMPLETE" if self._trade_count > 0 else "UNAVAILABLE",
                "reason": None if self._trade_count > 0 else "no_trades",
                "tradeCount": self._trade_count,
            }

    def windowed_cvd(self) -> dict[str, Any]:
        """CVD over the rolling window (last `cvd_window` trades)."""
        with self._lock:
            if not self._trades:
                return _unavail("no_trades_in_window")
            buy_vol = sum(t["qty"] for t in self._trades if t["side"] == "buy")
            sell_vol = sum(t["qty"] for t in self._trades if t["side"] == "sell")
            cvd = buy_vol - sell_vol
            return {
                "value": cvd,
                "buyVolume": buy_vol,
                "sellVolume": sell_vol,
                "window": len(self._trades),
                "maxWindow": self.cvd_window,
                "quality": "COMPLETE",
            }

    def taker_summary(self) -> dict[str, Any]:
        """Summary of taker buy/sell volumes in the current window."""
        with self._lock:
            if not self._trades:
                return _unavail("no_trades")
            buy_count = sum(1 for t in self._trades if t["side"] == "buy")
            sell_count = sum(1 for t in self._trades if t["side"] == "sell")
            buy_vol = sum(t["qty"] for t in self._trades if t["side"] == "buy")
            sell_vol = sum(t["qty"] for t in self._trades if t["side"] == "sell")
            total = buy_vol + sell_vol
            buy_pct = buy_vol / total * 100.0 if total > 0 else None
            return {
                "takerBuyVolume": buy_vol,
                "takerSellVolume": sell_vol,
                "takerBuyCount": buy_count,
                "takerSellCount": sell_count,
                "takerBuyPct": buy_pct,
                "quality": "COMPLETE",
            }

    def large_trade_count(self) -> dict[str, Any]:
        """Count of trades classified as large within session."""
        with self._lock:
            return {
                "value": self._large_trade_count,
                "multiplier": self.large_trade_multiplier,
                "quality": "COMPLETE" if self._trade_count > 0 else "UNAVAILABLE",
                "reason": None if self._trade_count > 0 else "no_trades",
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tradeCount": self._trade_count,
                "windowSize": len(self._trades),
                "cvdWindow": self.cvd_window,
                "cumulativeCVD": self._cumulative_buy_vol - self._cumulative_sell_vol,
                "largeTradeCount": self._large_trade_count,
            }
