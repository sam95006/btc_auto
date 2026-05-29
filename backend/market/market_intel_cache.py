"""Background refresh for external market intel — no HTTP on the trading tick path."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from backend.market.external_market_intel_service import ExternalMarketIntelService

logger = logging.getLogger(__name__)


class MarketIntelCache:
    """
    Polls CoinGecko / CMC / CryptoQuant on a daemon thread.
    Trading code must only call snapshot(), apply_to_contexts(), etc.
    """

    def __init__(self, intel_service: Optional[ExternalMarketIntelService] = None, poll_seconds: float = 60.0):
        self._intel = intel_service or ExternalMarketIntelService()
        self._poll_seconds = max(15.0, float(poll_seconds or 60.0))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_refresh_at = 0.0
        self._last_error = ""

    def start(self, *, bootstrap: bool = True) -> None:
        if self._thread and self._thread.is_alive():
            return
        if bootstrap:
            try:
                self.refresh_now()
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning("market_intel bootstrap refresh failed: %s", exc)
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="market-intel-cache", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def refresh_now(self) -> Dict[str, Any]:
        snap = self._intel.refresh()
        self._last_refresh_at = time.time()
        self._last_error = ""
        return snap

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.refresh_now()
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning("market_intel poll failed: %s", exc)
            self._stop.wait(self._poll_seconds)

    def status(self) -> Dict[str, Any]:
        return {
            "poll_seconds": self._poll_seconds,
            "last_refresh_at": self._last_refresh_at,
            "last_error": self._last_error,
            "thread_alive": bool(self._thread and self._thread.is_alive()),
            "providers": (self.snapshot().get("providers_configured") or {}),
        }

    def snapshot(self) -> Dict[str, Any]:
        return self._intel.snapshot()

    def top_radar_symbols(self, futures_client=None, limit: int = 50) -> List[str]:
        return self._intel.top_radar_symbols(futures_client, limit=limit)

    def apply_to_contexts(self, market_contexts):
        return self._intel.apply_to_contexts(market_contexts)

    def apply_growth_directives(self, growth_status):
        return self._intel.apply_growth_directives(growth_status)

    def liquidity_ok_for_symbol(self, symbol: str) -> bool:
        return self._intel.liquidity_ok_for_symbol(symbol)
