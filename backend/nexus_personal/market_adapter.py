"""Real member-safe market data binding for Personal Market Intelligence (PERSONAL-2).

PERSONAL-1 left analysis/report/history depending on an unbound generic
callable (`NEXUS_PERSONAL_MARKET_SOURCE`). PERSONAL-2 binds them to the real,
credential-free, member-safe public market services that already exist in the
product backend (`PublicMarketHistoryService`, Binance USDM public read-only
adapter). There is NO second market backend.

Provenance guarantees:
- Real OHLCV series, real provider/candle timestamps, real symbol, explicit
  freshness and source class.
- If the upstream data is unavailable the adapter raises
  `PersonalMarketUnavailable`; the route returns 503 and consumes no quota.
  Data is NEVER fabricated.

Member-safe: this module only reads public market facts. It exposes no
account, order, routing, ARM, position, execution, or provider-secret surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

from backend.nexus_product_backend.market_snapshot import (
    PublicMarketHistoryService,
    build_public_market_history_service,
)

# Freshness values that still carry real, usable (if delayed) data.
USABLE_FRESHNESS = frozenset({"FRESH", "LIVE", "STALE", "DATA_DELAYED"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_from_ms(value: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(value) / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


class PersonalMarketUnavailable(Exception):
    """Raised when no real member-safe market data is available (no fabrication)."""

    def __init__(self, reason: str = "market_data_unavailable") -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PersonalMarketSeries:
    """A real, member-safe price series with explicit provenance."""

    symbol: str
    interval: str
    closes: list[float]
    provider: str
    source_class: str
    freshness: str
    data_timestamp: Optional[str]
    fetched_at: str

    @property
    def points(self) -> int:
        return len(self.closes)

    def metadata(self) -> dict[str, Any]:
        """Member-safe provenance metadata (no execution/secret fields)."""
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "provider": self.provider,
            "source_class": self.source_class,
            "freshness": self.freshness,
            "data_timestamp": self.data_timestamp,
            "analysis_timestamp": self.fetched_at,
            "points": self.points,
        }


class PersonalMarketAdapter:
    """Binds Personal analysis/report/history to the real public history service."""

    def __init__(self, history_service: Optional[PublicMarketHistoryService] = None) -> None:
        self._history = history_service or build_public_market_history_service()

    def fetch_series(self, symbol: str, *, interval: str = "1h", limit: int = 60) -> PersonalMarketSeries:
        payload, status = self._history.history(symbol=symbol, interval=interval, limit=limit)
        if status != 200:
            raise PersonalMarketUnavailable(str(payload.get("error") or "market_data_unavailable"))
        freshness = str(payload.get("freshness") or "UNAVAILABLE")
        if freshness not in USABLE_FRESHNESS:
            raise PersonalMarketUnavailable("market_data_unavailable")
        candles = payload.get("candles")
        if not isinstance(candles, list) or len(candles) < 2:
            raise PersonalMarketUnavailable("insufficient_market_data")
        closes: list[float] = []
        last_close_ms: Any = None
        for candle in candles:
            if isinstance(candle, dict) and isinstance(candle.get("close"), (int, float)):
                closes.append(float(candle["close"]))
                last_close_ms = candle.get("close_time_ms", last_close_ms)
        if len(closes) < 2:
            raise PersonalMarketUnavailable("insufficient_market_data")
        data_ts = _utc_from_ms(last_close_ms) or payload.get("provider_timestamp")
        return PersonalMarketSeries(
            symbol=str(payload.get("symbol") or symbol).upper(),
            interval=str(payload.get("interval") or interval),
            closes=closes,
            provider=str(payload.get("provider") or "binance_usdm_public"),
            source_class=str(payload.get("data_class") or "LIVE_READ_ONLY"),
            freshness=freshness,
            data_timestamp=data_ts,
            fetched_at=_utc_now(),
        )

    def fetch_history(self, symbol: str, *, interval: str = "1d", limit: int = 30) -> tuple[dict[str, Any], int]:
        """Real bounded OHLCV history (member-safe, provider-bounded)."""
        return self._history.history(symbol=symbol, interval=interval, limit=limit)


class _CallableSeriesAdapter:
    """Test/preview adapter that wraps a plain callable returning a price series.

    Preserves the PERSONAL-1 fixture-injection contract
    (`NEXUS_PERSONAL_MARKET_SOURCE`) so tests can inject deterministic data
    without any network. Its series are explicitly marked as a fixture source.
    """

    def __init__(self, source: Callable[[str], Optional[Sequence[float]]]) -> None:
        self._source = source

    def fetch_series(self, symbol: str, *, interval: str = "1h", limit: int = 60) -> PersonalMarketSeries:
        try:
            raw = self._source(symbol)
        except Exception as exc:  # noqa: BLE001 - any source error is unavailable
            raise PersonalMarketUnavailable("market_source_error") from exc
        closes = [float(v) for v in (raw or []) if isinstance(v, (int, float))]
        if len(closes) < 2:
            raise PersonalMarketUnavailable("insufficient_market_data")
        now = _utc_now()
        return PersonalMarketSeries(
            symbol=symbol.upper(),
            interval=interval,
            closes=closes,
            provider="fixture",
            source_class="FIXTURE_TEST",
            freshness="FIXTURE",
            data_timestamp=now,
            fetched_at=now,
        )

    def fetch_history(self, symbol: str, *, interval: str = "1d", limit: int = 30) -> tuple[dict[str, Any], int]:
        try:
            raw = self._source(symbol)
        except Exception:  # noqa: BLE001
            return {"freshness": "UNAVAILABLE", "candles": []}, 503
        closes = [float(v) for v in (raw or []) if isinstance(v, (int, float))]
        if len(closes) < 1:
            return {"freshness": "UNAVAILABLE", "candles": []}, 503
        now = _utc_now()
        candles = [
            {"open": c, "high": c, "low": c, "close": c, "volume": 0.0, "close_time_ms": None}
            for c in closes[-limit:]
        ]
        return (
            {
                "schema": "nexus_public_market_history_v1",
                "data_class": "FIXTURE_TEST",
                "provider": "fixture",
                "symbol": symbol.upper(),
                "interval": interval,
                "freshness": "FIXTURE",
                "server_timestamp": now,
                "candles": candles,
            },
            200,
        )


def build_personal_market_adapter() -> PersonalMarketAdapter:
    return PersonalMarketAdapter()
