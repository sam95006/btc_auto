"""Aggregate CoinGecko / CoinMarketCap / CryptoQuant for fleet + RADAR context."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from backend.market.coingecko_market_service import CoinGeckoMarketService
from backend.market.coinmarketcap_market_service import CoinMarketCapMarketService
from backend.market.cryptoquant_market_service import CryptoQuantMarketService
from config.external_market_config import (
    CMC_ALT_LEVERAGE_MULTIPLIER,
    EXTERNAL_MARKET_ENABLED,
)
from config.fleet_routing_config import CORE_FLEET_SYMBOLS, normalize_symbol


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ExternalMarketIntelService:
    def __init__(
        self,
        coingecko=None,
        coinmarketcap=None,
        cryptoquant=None,
    ):
        self.coingecko = coingecko or CoinGeckoMarketService()
        self.coinmarketcap = coinmarketcap or CoinMarketCapMarketService()
        self.cryptoquant = cryptoquant or CryptoQuantMarketService()
        self._last_snapshot: Dict[str, Any] = {}

    def refresh(self) -> Dict[str, Any]:
        if not EXTERNAL_MARKET_ENABLED:
            self._last_snapshot = {"enabled": False, "updated_at": _now()}
            return self._last_snapshot

        coingecko = self.coingecko.fetch_top_markets()
        cmc = self.coinmarketcap.fetch_global_metrics()
        cq = self.cryptoquant.fetch_risk_signals()

        alerts: List[str] = []
        if coingecko.get("ok"):
            low_liq = [
                sym
                for sym, row in (coingecko.get("by_symbol") or {}).items()
                if not row.get("liquidity_ok")
            ]
            if low_liq:
                alerts.append(f"coingecko_low_liquidity:{','.join(low_liq[:6])}")
        if cmc.get("alt_leverage_reduce"):
            alerts.append(f"btc_dominance_high:{cmc.get('btc_dominance')}")
        if cq.get("whale_dump_alert"):
            alerts.append(f"btc_exchange_inflow_spike:{cq.get('btc_exchange_inflow')}")
        if cq.get("oi_stress"):
            alerts.append("cryptoquant_oi_stress")

        self._last_snapshot = {
            "enabled": True,
            "updated_at": _now(),
            "coingecko": coingecko,
            "coinmarketcap": cmc,
            "cryptoquant": cq,
            "alerts": alerts,
            "providers_configured": {
                "coingecko": self.coingecko.configured(),
                "coinmarketcap": self.coinmarketcap.configured(),
                "cryptoquant": self.cryptoquant.configured(),
            },
        }
        return self._last_snapshot

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._last_snapshot or {})

    def top_radar_symbols(self, futures_client=None, limit: int = 50) -> List[str]:
        intel = self._last_snapshot or self.refresh()
        coingecko = intel.get("coingecko") or {}
        symbols = [normalize_symbol(item) for item in (coingecko.get("symbols") or [])]
        merged: List[str] = []
        seen = set()
        tradable = set()
        if futures_client and getattr(futures_client, "is_tradable_symbol", None):
            try:
                tradable = futures_client.tradable_symbols()
            except Exception:
                tradable = set()

        def _accept(symbol: str) -> bool:
            if not symbol.endswith("USDT") or symbol in CORE_FLEET_SYMBOLS:
                return False
            if tradable and symbol not in tradable:
                return False
            return True

        for symbol in symbols:
            if not _accept(symbol) or symbol in seen:
                continue
            seen.add(symbol)
            merged.append(symbol)
            if len(merged) >= limit:
                return merged

        if futures_client and getattr(futures_client, "is_configured", lambda: False)():
            try:
                for item in futures_client.fetch_24h_tickers() or []:
                    symbol = normalize_symbol(item.get("symbol"))
                    if _accept(symbol) and symbol not in seen:
                        seen.add(symbol)
                        merged.append(symbol)
                    if len(merged) >= limit:
                        break
            except Exception:
                pass
        return merged

    def apply_to_contexts(self, market_contexts: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        intel = self._last_snapshot or {}
        if not intel.get("enabled"):
            return market_contexts

        coingecko = intel.get("coingecko") or {}
        cmc = intel.get("coinmarketcap") or {}
        cq = intel.get("cryptoquant") or {}
        by_symbol = coingecko.get("by_symbol") or {}

        global_flat = {
            "btc_dominance": cmc.get("btc_dominance"),
            "total_market_cap_usd": cmc.get("total_market_cap_usd"),
            "btc_exchange_inflow": cq.get("btc_exchange_inflow"),
            "external_whale_dump_alert": bool(cq.get("whale_dump_alert")),
            "external_oi_stress": bool(cq.get("oi_stress")),
            "external_exit_pressure": float(cq.get("external_exit_pressure") or 0.0),
            "external_market_alerts": list(intel.get("alerts") or []),
        }

        updated: Dict[str, Dict[str, Any]] = {}
        for key, ctx in (market_contexts or {}).items():
            merged = dict(ctx or {})
            symbol = str(merged.get("symbol") or key or "").upper()
            if not symbol.endswith("USDT") and key in {"BTC", "ETH", "SOL", "PEPE"}:
                symbol = f"{key}USDT"
            coin_row = by_symbol.get(symbol) or {}
            if coin_row:
                merged["coingecko_rank"] = coin_row.get("rank")
                merged["coingecko_volume_24h_usd"] = coin_row.get("volume_24h_usd")
                merged["coingecko_liquidity_ok"] = bool(coin_row.get("liquidity_ok"))
            merged.update(global_flat)
            if cmc.get("alt_leverage_reduce") and key not in {"BTC", "BTCUSDT"}:
                merged["alt_leverage_multiplier"] = CMC_ALT_LEVERAGE_MULTIPLIER
            if cq.get("oi_stress"):
                merged["market_regime"] = merged.get("market_regime") or "external_oi_stress"
            updated[key] = merged
        return updated

    def apply_growth_directives(self, growth_status: Dict[str, Any]) -> Dict[str, Any]:
        intel = self._last_snapshot or {}
        growth_status = dict(growth_status or {})
        cq = intel.get("cryptoquant") or {}
        cmc = intel.get("coinmarketcap") or {}
        if cq.get("oi_stress"):
            growth_status["external_risk"] = "oi_stress"
            growth_status.setdefault("block_reason", "cryptoquant_oi_stress")
        if cmc.get("alt_leverage_reduce"):
            growth_status["btc_dominance"] = cmc.get("btc_dominance")
            growth_status["alt_leverage_multiplier"] = CMC_ALT_LEVERAGE_MULTIPLIER
        growth_status["external_market_intel"] = {
            "alerts": list(intel.get("alerts") or []),
            "providers": intel.get("providers_configured") or {},
        }
        return growth_status

    def liquidity_ok_for_symbol(self, symbol: str) -> bool:
        intel = self._last_snapshot or {}
        row = ((intel.get("coingecko") or {}).get("by_symbol") or {}).get(str(symbol).upper())
        if not row:
            return True
        return bool(row.get("liquidity_ok", True))
