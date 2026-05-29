from __future__ import annotations

from datetime import datetime

from backend.market.technical_context_service import TechnicalContextService
from config.market_data_config import (
    CONTEXT_SLIPPAGE_NOTIONAL,
    DEFAULT_BOOK_LIMIT,
    EXTREME_BASIS_BPS,
    FUTURES_ACCOUNT_MAX_AGE_MS,
    LIQUIDATION_CRITICAL_DISTANCE_PCT,
    LIQUIDATION_WARNING_DISTANCE_PCT,
    LOW_OPEN_INTEREST,
    LOW_OPEN_INTEREST_NOTIONAL,
    ORDER_BOOK_IMBALANCE_ALERT,
    PRICE_MAX_AGE_MS,
    SIMULATION_MAX_BASIS_ABS_BPS,
    SIMULATION_MAX_FUNDING_ABS,
    SIMULATION_MAX_SLIPPAGE_BPS,
    SPOT_ACCOUNT_MAX_AGE_MS,
    STREAM_EVENT_MAX_AGE_MS,
    THIN_LIQUIDITY_NOTIONAL,
    WIDE_SPREAD_BPS,
)


def _safe_float(value):
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _coerce_iso_to_ms(value):
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value)).timestamp() * 1000)
    except Exception:
        return 0


def _freshness_bucket(age_ms, threshold_ms):
    if age_ms <= threshold_ms:
        return "fresh"
    if age_ms <= threshold_ms * 2:
        return "aging"
    return "stale"


class MarketContextService:
    def __init__(self, spot_client=None, futures_client=None, technical_context_service=None):
        self.spot_client = spot_client
        self.futures_client = futures_client
        self.technical_context_service = technical_context_service or TechnicalContextService(futures_client)

    def begin_technical_tick(self):
        if self.technical_context_service:
            self.technical_context_service.begin_tick()

    def build_futures_contexts(self, fleet_symbol_map, prices, futures_account=None):
        contexts = {}
        positions_by_symbol = {
            str(item.get("symbol") or ""): dict(item)
            for item in ((futures_account or {}).get("positions") or [])
            if item.get("symbol")
        }
        if not (self.futures_client and self.futures_client.is_configured()):
            return contexts
        for fleet, symbol in (fleet_symbol_map or {}).items():
            contexts[fleet] = self.build_symbol_context(
                symbol=symbol,
                price_payload=(prices or {}).get(fleet, {}),
                position_payload=positions_by_symbol.get(symbol, {}),
                fleet=fleet,
            )
        return contexts

    def build_symbol_context(self, symbol, price_payload=None, position_payload=None, fleet=None):
        if not (self.futures_client and self.futures_client.is_configured()):
            return {}
        symbol = str(symbol or "").upper()
        if getattr(self.futures_client, "is_tradable_symbol", None) and not self.futures_client.is_tradable_symbol(symbol):
            return {}
        position_payload = dict(position_payload or {})
        signed_qty = _safe_float(position_payload.get("signed_quantity"))
        position_side = "LONG" if signed_qty > 0 else "SHORT" if signed_qty < 0 else None
        context = self._build_single_futures_context(
            fleet or symbol,
            symbol,
            price_payload or {},
            position_payload,
        )
        return self._merge_technical_context(context, symbol, position_side=position_side)

    def _merge_technical_context(self, context, symbol, position_side=None):
        if not context or not self.technical_context_service:
            return context
        technical = self.technical_context_service.analyze(symbol, position_side=position_side) or {}
        flat = dict(technical.get("flat") or {})
        intervals = dict(technical.get("intervals") or {})
        if not flat and not intervals:
            return context
        merged = dict(context)
        if intervals:
            merged["technical"] = intervals
        if flat:
            merged.update(flat)
        return merged

    def build_truth_layer_status(self, prices, spot_account, futures_account, account_sync_status, market_contexts):
        now_ms = int(datetime.now().timestamp() * 1000)
        price_ages = {}
        stale_reasons = []
        for fleet, payload in (prices or {}).items():
            age_ms = max(now_ms - _coerce_iso_to_ms(payload.get("time")), 0)
            price_ages[fleet] = {
                "age_ms": age_ms,
                "status": _freshness_bucket(age_ms, PRICE_MAX_AGE_MS),
                "source": payload.get("source", ""),
            }
            if price_ages[fleet]["status"] == "stale":
                stale_reasons.append(f"{fleet.lower()}_price_stale")

        spot_age_ms = max(now_ms - int((spot_account or {}).get("update_time") or 0), 0) if spot_account else 0
        futures_age_ms = max(now_ms - int((futures_account or {}).get("update_time") or 0), 0) if futures_account else 0
        spot_stream_health = ((account_sync_status or {}).get("spot_stream_health") or {}) if account_sync_status else {}
        spot_stream_last_event = int(spot_stream_health.get("last_event_time") or 0)
        spot_stream_age_ms = max(now_ms - spot_stream_last_event, 0) if spot_stream_last_event else 0

        if _freshness_bucket(spot_age_ms, SPOT_ACCOUNT_MAX_AGE_MS) == "stale":
            stale_reasons.append("spot_account_stale")
        if _freshness_bucket(futures_age_ms, FUTURES_ACCOUNT_MAX_AGE_MS) == "stale":
            stale_reasons.append("futures_account_stale")
        if spot_stream_last_event and _freshness_bucket(spot_stream_age_ms, STREAM_EVENT_MAX_AGE_MS) == "stale":
            stale_reasons.append("spot_stream_event_stale")

        degraded_contexts = sorted(
            fleet
            for fleet, context in (market_contexts or {}).items()
            if context.get("liquidity_status") != "healthy" or context.get("spread_status") != "normal"
        )

        return {
            "fresh_for_ai": not stale_reasons,
            "stale_reasons": stale_reasons,
            "price_freshness": price_ages,
            "spot_account_freshness": {
                "age_ms": spot_age_ms,
                "status": _freshness_bucket(spot_age_ms, SPOT_ACCOUNT_MAX_AGE_MS),
            },
            "futures_account_freshness": {
                "age_ms": futures_age_ms,
                "status": _freshness_bucket(futures_age_ms, FUTURES_ACCOUNT_MAX_AGE_MS),
            },
            "spot_stream_freshness": {
                "age_ms": spot_stream_age_ms,
                "status": _freshness_bucket(spot_stream_age_ms, STREAM_EVENT_MAX_AGE_MS) if spot_stream_last_event else "unknown",
            },
            "degraded_market_contexts": degraded_contexts,
            "last_truth_update_ms": now_ms,
        }

    def _estimate_slippage_bps(self, levels, target_notional, reference_price):
        if not levels or not target_notional or not reference_price:
            return 0.0
        remaining = float(target_notional)
        acquired_qty = 0.0
        spent_notional = 0.0
        for px, qty in levels:
            price = _safe_float(px)
            quantity = _safe_float(qty)
            if price <= 0 or quantity <= 0:
                continue
            level_notional = price * quantity
            consume_notional = min(level_notional, remaining)
            consume_qty = consume_notional / price
            acquired_qty += consume_qty
            spent_notional += consume_notional
            remaining -= consume_notional
            if remaining <= 0:
                break
        if acquired_qty <= 0:
            return 0.0
        avg_fill_price = spent_notional / acquired_qty
        return ((avg_fill_price - reference_price) / reference_price) * 10_000.0

    def _build_single_futures_context(self, fleet, symbol, price_payload, position_payload=None):
        book = self.futures_client.get_order_book(symbol, limit=DEFAULT_BOOK_LIMIT)
        ticker = self.futures_client.get_book_ticker(symbol)
        premium = self.futures_client.get_premium_index(symbol)
        open_interest = self.futures_client.get_open_interest(symbol)

        bid = _safe_float(ticker.get("bidPrice"))
        ask = _safe_float(ticker.get("askPrice"))
        mid = (bid + ask) / 2.0 if bid and ask else _safe_float(price_payload.get("price"))
        spread = max(ask - bid, 0.0) if bid and ask else 0.0
        spread_bps = (spread / mid) * 10_000.0 if mid else 0.0

        bids = book.get("bids") or []
        asks = book.get("asks") or []
        bid_notional = sum(_safe_float(px) * _safe_float(qty) for px, qty in bids[:5])
        ask_notional = sum(_safe_float(px) * _safe_float(qty) for px, qty in asks[:5])
        top5_notional = min(bid_notional, ask_notional)
        oi_value = _safe_float(open_interest.get("openInterest"))
        funding_rate = _safe_float(premium.get("lastFundingRate"))
        mark_price = _safe_float(premium.get("markPrice")) or mid
        index_price = _safe_float(premium.get("indexPrice"))
        oi_notional = oi_value * mark_price if oi_value and mark_price else 0.0
        basis = mark_price - index_price if mark_price and index_price else 0.0
        basis_bps = (basis / index_price) * 10_000.0 if index_price else 0.0
        imbalance_ratio = ((bid_notional - ask_notional) / (bid_notional + ask_notional)) if (bid_notional + ask_notional) else 0.0
        imbalance_bias = "bid" if imbalance_ratio >= ORDER_BOOK_IMBALANCE_ALERT else "ask" if imbalance_ratio <= -ORDER_BOOK_IMBALANCE_ALERT else "balanced"
        buy_slippage_bps = self._estimate_slippage_bps(asks[:5], CONTEXT_SLIPPAGE_NOTIONAL, ask or mark_price or mid)
        sell_slippage_bps = abs(self._estimate_slippage_bps(bids[:5], CONTEXT_SLIPPAGE_NOTIONAL, bid or mark_price or mid))
        worst_slippage_bps = max(abs(buy_slippage_bps), abs(sell_slippage_bps))

        spread_status = "wide" if spread_bps >= WIDE_SPREAD_BPS else "normal"
        liquidity_status = "thin" if top5_notional < THIN_LIQUIDITY_NOTIONAL else "healthy"
        oi_status = "low" if oi_value < LOW_OPEN_INTEREST else "healthy"
        oi_notional_status = "low" if oi_notional < LOW_OPEN_INTEREST_NOTIONAL else "healthy"
        funding_risk = "elevated" if abs(funding_rate) >= SIMULATION_MAX_FUNDING_ABS else "normal"
        basis_risk = "elevated" if abs(basis_bps) >= SIMULATION_MAX_BASIS_ABS_BPS else "normal"
        slippage_risk = "elevated" if worst_slippage_bps >= SIMULATION_MAX_SLIPPAGE_BPS else "normal"

        market_regime = "normal"
        if spread_status == "wide" and liquidity_status == "thin":
            market_regime = "thin_liquidity"
        elif spread_status == "wide":
            market_regime = "wide_spread"
        elif oi_status == "low":
            market_regime = "low_open_interest"
        elif oi_notional_status == "low":
            market_regime = "low_open_interest_notional"
        elif abs(basis_bps) >= EXTREME_BASIS_BPS:
            market_regime = "basis_dislocation"
        elif funding_risk == "elevated":
            market_regime = "funding_dislocation"
        elif slippage_risk == "elevated":
            market_regime = "high_slippage"

        liquidation_price = _safe_float((position_payload or {}).get("liquidation_price"))
        signed_quantity = _safe_float((position_payload or {}).get("signed_quantity"))
        liquidation_distance_pct = 0.0
        liquidation_risk = "none"
        if liquidation_price and mark_price and signed_quantity:
            liquidation_distance_pct = abs(mark_price - liquidation_price) / mark_price
            if liquidation_distance_pct <= LIQUIDATION_CRITICAL_DISTANCE_PCT:
                liquidation_risk = "critical"
                market_regime = "liquidation_risk"
            elif liquidation_distance_pct <= LIQUIDATION_WARNING_DISTANCE_PCT:
                liquidation_risk = "elevated"
                market_regime = "liquidation_risk"

        return {
            "fleet": fleet,
            "symbol": symbol,
            "mark_price": mark_price,
            "index_price": index_price,
            "funding_rate": funding_rate,
            "funding_abs": round(abs(funding_rate), 8),
            "funding_risk": funding_risk,
            "open_interest": oi_value,
            "open_interest_notional": round(oi_notional, 4),
            "bid_price": bid,
            "ask_price": ask,
            "spread": round(spread, 8),
            "spread_bps": round(spread_bps, 4),
            "basis": round(basis, 8),
            "basis_bps": round(basis_bps, 4),
            "basis_risk": basis_risk,
            "top5_bid_notional": round(bid_notional, 4),
            "top5_ask_notional": round(ask_notional, 4),
            "top5_cross_notional": round(top5_notional, 4),
            "order_book_imbalance": round(imbalance_ratio, 4),
            "imbalance_bias": imbalance_bias,
            "estimated_buy_slippage_bps": round(buy_slippage_bps, 4),
            "estimated_sell_slippage_bps": round(sell_slippage_bps, 4),
            "worst_slippage_bps": round(worst_slippage_bps, 4),
            "slippage_risk": slippage_risk,
            "spread_status": spread_status,
            "liquidity_status": liquidity_status,
            "oi_status": oi_status,
            "oi_notional_status": oi_notional_status,
            "market_regime": market_regime,
            "liquidation_distance_pct": round(liquidation_distance_pct, 6),
            "liquidation_risk": liquidation_risk,
            "source": "binance_futures_testnet",
        }
