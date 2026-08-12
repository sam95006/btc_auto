"""Public market data parsers and coordinator — missing values stay null/MISSING."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_real_shadow.instruments import load_fixture


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_ticker_row(row: dict[str, Any]) -> dict[str, Any]:
    bid = _safe_float(row.get("bid1Price"))
    ask = _safe_float(row.get("ask1Price"))
    spread_bps = None
    if bid is not None and ask is not None and bid > 0:
        spread_bps = ((ask - bid) / bid) * 10_000
    prev = _safe_float(row.get("prevPrice24h"))
    last = _safe_float(row.get("lastPrice"))
    momentum = None
    if prev is not None and prev > 0 and last is not None:
        momentum = (last - prev) / prev
    return {
        "symbol": row.get("symbol"),
        "last_price": last,
        "turnover_24h": _safe_float(row.get("turnover24h")),
        "volume_24h": _safe_float(row.get("volume24h")),
        "funding_rate": _safe_float(row.get("fundingRate")),
        "bid1_price": bid,
        "ask1_price": ask,
        "spread_bps": spread_bps,
        "momentum": momentum,
        "freshness": "FRESH" if last is not None else "MISSING",
    }


def parse_tickers_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = (payload.get("result") or {}).get("list") or []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        sym = str(row.get("symbol") or "")
        if sym:
            out[sym] = parse_ticker_row(row)
    return out


def parse_orderbook_payload(payload: dict[str, Any], symbol: str) -> dict[str, Any]:
    result = payload.get("result") or {}
    bids = result.get("b") or []
    asks = result.get("a") or []
    bid_depth = sum(_safe_float(x[1]) or 0 for x in bids if isinstance(x, list) and len(x) >= 2)
    ask_depth = sum(_safe_float(x[1]) or 0 for x in asks if isinstance(x, list) and len(x) >= 2)
    return {
        "symbol": symbol,
        "bid_depth": bid_depth if bids else None,
        "ask_depth": ask_depth if asks else None,
        "freshness": "FRESH" if bids or asks else "MISSING",
    }


def parse_funding_payload(payload: dict[str, Any]) -> dict[str, float | None]:
    rows = (payload.get("result") or {}).get("list") or []
    out: dict[str, float | None] = {}
    for row in rows:
        sym = str(row.get("symbol") or "")
        if sym:
            out[sym] = _safe_float(row.get("fundingRate"))
    return out


def parse_open_interest_payload(payload: dict[str, Any]) -> dict[str, float | None]:
    rows = (payload.get("result") or {}).get("list") or []
    out: dict[str, float | None] = {}
    for row in rows:
        sym = str(row.get("symbol") or "")
        if sym:
            out[sym] = _safe_float(row.get("openInterest"))
    return out


def parse_kline_rows(rows: list[list[Any]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        parsed.append(
            {
                "open": _safe_float(row[1]),
                "high": _safe_float(row[2]),
                "low": _safe_float(row[3]),
                "close": _safe_float(row[4]),
                "volume": _safe_float(row[5]) if len(row) > 5 else None,
            }
        )
    return parsed


@dataclass
class MarketDataBundle:
    symbol: str
    ticker: dict[str, Any] = field(default_factory=dict)
    orderbook: dict[str, Any] = field(default_factory=dict)
    funding_rate: float | None = None
    open_interest: float | None = None
    status: str = "OK"

    def merged_quality_input(self) -> dict[str, Any]:
        t = self.ticker
        ob = self.orderbook
        return {
            "last_price": t.get("last_price"),
            "turnover_24h": t.get("turnover_24h"),
            "volume_24h": t.get("volume_24h"),
            "spread_bps": t.get("spread_bps"),
            "bid_depth": ob.get("bid_depth"),
            "ask_depth": ob.get("ask_depth"),
            "funding_rate": self.funding_rate if self.funding_rate is not None else t.get("funding_rate"),
            "open_interest": self.open_interest,
            "momentum": t.get("momentum"),
            "freshness": t.get("freshness") or "MISSING",
            "orderbook_freshness": ob.get("freshness") or "MISSING",
        }


class MarketDataCoordinator:
    """Load fixture-backed or injected public market data for symbols."""

    def __init__(self, *, use_fixtures: bool = True) -> None:
        self.use_fixtures = use_fixtures
        self._tickers: dict[str, dict[str, Any]] | None = None
        self._funding: dict[str, float | None] | None = None
        self._oi: dict[str, float | None] | None = None

    def _ensure_loaded(self) -> None:
        if self._tickers is None:
            self._tickers = parse_tickers_payload(load_fixture("tickers.json"))
        if self._funding is None:
            self._funding = parse_funding_payload(load_fixture("funding.json"))
        if self._oi is None:
            self._oi = parse_open_interest_payload(load_fixture("open_interest.json"))

    def fetch_symbol(self, symbol: str) -> MarketDataBundle:
        self._ensure_loaded()
        ticker = dict(self._tickers.get(symbol) or {})
        if not ticker:
            return MarketDataBundle(symbol=symbol, status="UNAVAILABLE")
        ob = parse_orderbook_payload(load_fixture("orderbook.json"), symbol)
        funding = (self._funding or {}).get(symbol)
        oi = (self._oi or {}).get(symbol)
        return MarketDataBundle(
            symbol=symbol,
            ticker=ticker,
            orderbook=ob,
            funding_rate=funding,
            open_interest=oi,
            status="OK",
        )

    def fetch_many(self, symbols: list[str]) -> dict[str, MarketDataBundle]:
        return {sym: self.fetch_symbol(sym) for sym in symbols}

    def to_market_dicts(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        bundles = self.fetch_many(symbols)
        out: dict[str, dict[str, Any]] = {}
        for sym, bundle in bundles.items():
            merged = bundle.merged_quality_input()
            merged["symbol"] = sym
            merged["status"] = bundle.status
            out[sym] = merged
        return out
