from __future__ import annotations

import time
from datetime import datetime

from config.fleet_routing_config import CORE_FLEET_SYMBOLS, normalize_symbol
from config.radar_config import (
    RADAR_MAX_CANDIDATES,
    RADAR_MAX_WHALE_NOTES,
    RADAR_MIN_CANDIDATE_NOTIONAL,
    RADAR_SCAN_CACHE_SECONDS,
    RADAR_SCAN_SYMBOLS,
)


def _safe_float(value) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


class RadarMarketScanService:
    def __init__(self, futures_client, market_context_service, symbols=None, cache_seconds=RADAR_SCAN_CACHE_SECONDS):
        self.futures_client = futures_client
        self.market_context_service = market_context_service
        self.symbols = tuple(symbols or RADAR_SCAN_SYMBOLS)
        self.cache_seconds = int(cache_seconds or RADAR_SCAN_CACHE_SECONDS)
        self._cache = {"expires_at": 0.0, "snapshot": None}

    def scan(self):
        now = time.time()
        if self._cache["snapshot"] and now < self._cache["expires_at"]:
            return self._cache["snapshot"]

        if not self.futures_client or not self.futures_client.is_configured():
            snapshot = {
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "scan_status": "disabled",
                "candidates": [],
                "whale_watch": [],
                "market_board": [],
            }
            self._cache = {"expires_at": now + self.cache_seconds, "snapshot": snapshot}
            return snapshot

        board = []
        whale_watch = []
        for symbol in self.symbols:
            symbol = normalize_symbol(symbol)
            if getattr(self.futures_client, "is_tradable_symbol", None) and not self.futures_client.is_tradable_symbol(symbol):
                continue
            try:
                context = self.market_context_service.build_symbol_context(symbol, {})
            except Exception:
                continue
            if not context:
                continue
            whale_note = self._to_whale_note(context)
            if whale_note:
                whale_watch.append(whale_note)
            if symbol in CORE_FLEET_SYMBOLS:
                continue
            candidate = self._to_candidate(context)
            board.append(candidate)

        candidates = sorted(
            [item for item in board if item["candidate_score"] > 0],
            key=lambda item: item["candidate_score"],
            reverse=True,
        )[:RADAR_MAX_CANDIDATES]

        snapshot = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "scan_status": "ok",
            "candidates": candidates,
            "whale_watch": sorted(whale_watch, key=lambda item: item["priority"], reverse=True)[:RADAR_MAX_WHALE_NOTES],
            "market_board": sorted(board, key=lambda item: item["candidate_score"], reverse=True),
        }
        self._cache = {"expires_at": now + self.cache_seconds, "snapshot": snapshot}
        return snapshot

    def _to_candidate(self, context):
        spread_ok = str(context.get("spread_status", "normal")) == "normal"
        liquidity_ok = str(context.get("liquidity_status", "healthy")) == "healthy"
        slippage_ok = str(context.get("slippage_risk", "normal")) == "normal"
        funding_ok = str(context.get("funding_risk", "normal")) == "normal"
        basis_ok = str(context.get("basis_risk", "normal")) == "normal"
        oi_ok = str(context.get("oi_notional_status", "healthy")) == "healthy"
        top5_notional = _safe_float(context.get("top5_cross_notional"))
        imbalance = _safe_float(context.get("order_book_imbalance"))
        bias = str(context.get("imbalance_bias", "balanced"))
        funding_rate = _safe_float(context.get("funding_rate"))
        basis_bps = _safe_float(context.get("basis_bps"))
        liquidation_risk = str(context.get("liquidation_risk", "none"))

        long_edge = 0.0
        short_edge = 0.0
        if bias == "bid":
            long_edge += abs(imbalance) * 100.0
        elif bias == "ask":
            short_edge += abs(imbalance) * 100.0
        if funding_rate < 0:
            long_edge += min(25.0, abs(funding_rate) * 10_000.0)
        elif funding_rate > 0:
            short_edge += min(25.0, abs(funding_rate) * 10_000.0)
        if basis_bps < 0:
            long_edge += min(20.0, abs(basis_bps))
        elif basis_bps > 0:
            short_edge += min(20.0, abs(basis_bps))

        structural_ok = all([spread_ok, liquidity_ok, slippage_ok, funding_ok, basis_ok, oi_ok]) and top5_notional >= RADAR_MIN_CANDIDATE_NOTIONAL
        candidate_side = "LONG" if long_edge >= short_edge else "SHORT"
        edge_score = max(long_edge, short_edge)
        candidate_score = 0.0
        if structural_ok and liquidation_risk == "none":
            candidate_score = round(min(100.0, 35.0 + edge_score), 2)

        return {
            "symbol": context.get("symbol"),
            "mark_price": round(_safe_float(context.get("mark_price")), 10),
            "candidate_side": candidate_side,
            "candidate_score": candidate_score,
            "reason": (
                "healthy_structure"
                if candidate_score > 0
                else "watch_only"
            ),
            "market_regime": context.get("market_regime", "normal"),
            "spread_bps": round(_safe_float(context.get("spread_bps")), 4),
            "top5_cross_notional": round(top5_notional, 4),
            "funding_rate": round(funding_rate, 8),
            "basis_bps": round(basis_bps, 4),
            "order_book_imbalance": round(imbalance, 4),
            "liquidation_risk": liquidation_risk,
        }

    def _to_whale_note(self, context):
        imbalance = _safe_float(context.get("order_book_imbalance"))
        basis_bps = _safe_float(context.get("basis_bps"))
        funding_rate = _safe_float(context.get("funding_rate"))
        if abs(imbalance) < 0.35 and abs(basis_bps) < 12 and abs(funding_rate) < 0.0008:
            return None
        summary_bits = []
        if abs(imbalance) >= 0.35:
            summary_bits.append(f"order_book_{context.get('imbalance_bias', 'balanced')}")
        if abs(basis_bps) >= 12:
            summary_bits.append("basis_stretched")
        if abs(funding_rate) >= 0.0008:
            summary_bits.append("funding_skewed")
        priority = round(abs(imbalance) * 100 + abs(basis_bps) + abs(funding_rate) * 10_000, 2)
        return {
            "symbol": context.get("symbol"),
            "summary": ",".join(summary_bits),
            "priority": priority,
            "bias": context.get("imbalance_bias", "balanced"),
            "basis_bps": round(basis_bps, 4),
            "funding_rate": round(funding_rate, 8),
        }
