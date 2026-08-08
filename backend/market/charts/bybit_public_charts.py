"""Bybit Mainnet public chart data (Phase 3).

OHLCV + open-interest history via public REST only.
No TradingView endpoints · no private API · no secrets.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

BYBIT = "https://api.bybit.com"
_UA = "NEXUS-EATI-Charts/1.0 (read-only-public)"
_BAR_LIMIT = 300
_ALLOWED = {"1", "3", "5", "15", "60", "240", "D", "1m", "5m", "15m", "1h", "4h", "1d"}


def _norm_interval(interval: str) -> str:
    m = {
        "1m": "1",
        "3m": "3",
        "5m": "5",
        "15m": "15",
        "1h": "60",
        "4h": "240",
        "1d": "D",
        "D": "D",
    }
    raw = (interval or "5m").strip()
    return m.get(raw, raw if raw in {"1", "3", "5", "15", "60", "240", "D"} else "5")


def _get(path: str, params: dict[str, Any], timeout: float = 12.0) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    url = f"{BYBIT}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as raw:
        payload = json.loads(raw.read().decode("utf-8"))
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(payload.get("retMsg") or "bybit_error")
    return payload


def fetch_ohlcv(
    symbol: str,
    *,
    interval: str = "5m",
    limit: int = 120,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any]:
    sym = symbol.upper().strip()
    iv = _norm_interval(interval)
    lim = max(1, min(int(limit or 120), _BAR_LIMIT))
    params: dict[str, Any] = {"category": "linear", "symbol": sym, "interval": iv, "limit": lim}
    if start:
        params["start"] = int(start)
    if end:
        params["end"] = int(end)
    try:
        payload = _get("/v5/market/kline", params)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "symbol": sym,
            "interval": interval,
            "bars": [],
            "source": "BYBIT_MAINNET_LINEAR",
        }
    raw = list(((payload.get("result") or {}).get("list")) or [])
    # Bybit returns newest-first
    bars = []
    for row in reversed(raw):
        try:
            bars.append(
                {
                    "time": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                    "turnover": float(row[6]) if len(row) > 6 else None,
                }
            )
        except (TypeError, ValueError, IndexError):
            continue
    return {
        "ok": True,
        "read_only": True,
        "private_api": False,
        "symbol": sym,
        "interval": interval,
        "intervalResolved": iv,
        "barLimit": _BAR_LIMIT,
        "count": len(bars),
        "bars": bars,
        "source": "BYBIT_MAINNET_LINEAR",
        "generatedAt": int(time.time() * 1000),
        "freshness": "LIVE" if bars else "COLLECTING",
        "cache": "no-store",
    }


def fetch_open_interest(
    symbol: str,
    *,
    interval: str = "5min",
    limit: int = 100,
) -> dict[str, Any]:
    sym = symbol.upper().strip()
    # Bybit open-interest endpoints use 5min / 15min / 1h / 4h / 1d
    iv_map = {"1m": "5min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1d"}
    iv = iv_map.get(interval, interval if interval in {"5min", "15min", "1h", "4h", "1d"} else "5min")
    lim = max(1, min(int(limit or 100), _BAR_LIMIT))
    try:
        payload = _get(
            "/v5/market/open-interest",
            {"category": "linear", "symbol": sym, "intervalTime": iv, "limit": lim},
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "symbol": sym,
            "points": [],
            "source": "BYBIT_MAINNET_LINEAR",
            "freshness": "COLLECTING",
        }
    raw = list(((payload.get("result") or {}).get("list")) or [])
    points = []
    for row in reversed(raw):
        try:
            points.append(
                {
                    "time": int(row.get("timestamp")),
                    "openInterest": float(row.get("openInterest")),
                    "openInterestValue": None,
                }
            )
        except (TypeError, ValueError):
            continue
    return {
        "ok": True,
        "read_only": True,
        "private_api": False,
        "symbol": sym,
        "interval": iv,
        "count": len(points),
        "points": points,
        "source": "BYBIT_MAINNET_LINEAR",
        "generatedAt": int(time.time() * 1000),
        "freshness": "LIVE" if points else "COLLECTING",
        "cache": "no-store",
    }


def fetch_funding_history(
    symbol: str,
    *,
    limit: int = 100,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any]:
    """Bybit public GET /v5/market/funding/history — no fabrication, no interpolation."""
    sym = symbol.upper().strip()
    lim = max(1, min(int(limit or 100), _BAR_LIMIT))
    params: dict[str, Any] = {"category": "linear", "symbol": sym, "limit": lim}
    if start:
        params["startTime"] = int(start)
    if end:
        params["endTime"] = int(end)
    try:
        payload = _get("/v5/market/funding/history", params)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "available": False,
            "error": str(exc),
            "symbol": sym,
            "points": [],
            "fabricatedHistory": False,
            "source": "BYBIT_MAINNET_LINEAR",
            "freshness": "COLLECTING",
            "generatedAt": int(time.time() * 1000),
            "cache": "no-store",
        }
    raw = list(((payload.get("result") or {}).get("list")) or [])
    points: list[dict[str, Any]] = []
    for row in reversed(raw):
        try:
            rate = float(row.get("fundingRate"))
            ts = int(row.get("fundingRateTimestamp"))
        except (TypeError, ValueError):
            continue
        points.append(
            {
                "time": ts,
                "fundingRate": rate,
                "fundingRatePct": rate * 100.0,
                "symbol": str(row.get("symbol") or sym),
            }
        )
    return {
        "ok": True,
        "available": bool(points),
        "read_only": True,
        "private_api": False,
        "symbol": sym,
        "count": len(points),
        "points": points,
        "fabricatedHistory": False,
        "interpolated": False,
        "source": "BYBIT_MAINNET_LINEAR",
        "endpoint": "/v5/market/funding/history",
        "generatedAt": int(time.time() * 1000),
        "freshness": "LIVE" if points else "COLLECTING",
        "reason": None if points else "empty_funding_history",
        "cache": "no-store",
    }


def funding_series_status(symbol: str = "BTCUSDT", *, limit: int = 100) -> dict[str, Any]:
    """Return real funding history when Bybit public endpoint succeeds; never fabricate."""
    body = fetch_funding_history(symbol, limit=limit)
    if body.get("ok") and body.get("points"):
        return body
    # Honest unavailable / error path — fabricatedHistory stays false
    return {
        "ok": bool(body.get("ok")),
        "available": False,
        "reason": body.get("error") or body.get("reason") or "funding_history_unavailable",
        "error": body.get("error"),
        "symbol": symbol.upper().strip(),
        "points": [],
        "pointInTimeFunding": "available_via_ticker_and_scanner",
        "fabricatedHistory": False,
        "source": "BYBIT_MAINNET_LINEAR",
        "generatedAt": int(time.time() * 1000),
        "cache": "no-store",
    }


# Public-safe market series contract (V18.2.18) — official OHLCV only, never invent candles.
MARKET_SERIES_CONTRACT = "MARKET_SERIES_CONTRACT_V1"
_SERIES_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SERIES_CACHE_TTL_S = 45.0


def _interval_ms(interval: str) -> int:
    iv = _norm_interval(interval)
    table = {"1": 60_000, "3": 180_000, "5": 300_000, "15": 900_000, "60": 3_600_000, "240": 14_400_000, "D": 86_400_000}
    return table.get(iv, 300_000)


def bars_to_market_series(body: dict[str, Any], *, window_label: str | None = None) -> dict[str, Any]:
    """Normalize Bybit OHLCV into the public market-series contract."""
    bars = list(body.get("bars") or [])
    points: list[dict[str, Any]] = []
    for bar in bars:
        try:
            ts = int(bar["time"])
            o = float(bar["open"])
            h = float(bar["high"])
            low = float(bar["low"])
            c = float(bar["close"])
            vol = bar.get("volume")
            pt: dict[str, Any] = {
                "timestamp": ts,
                "o": o,
                "h": h,
                "l": low,
                "c": c,
            }
            if vol is not None:
                pt["volume"] = float(vol)
            points.append(pt)
        except (KeyError, TypeError, ValueError):
            continue

    interval = str(body.get("interval") or "5m")
    window_start = points[0]["timestamp"] if points else None
    window_end = points[-1]["timestamp"] if points else None
    ok = bool(body.get("ok")) and len(points) >= 2
    return {
        "ok": ok,
        "contract": MARKET_SERIES_CONTRACT,
        "symbol": body.get("symbol"),
        "interval": interval,
        "window_label": window_label,
        "window_start": window_start,
        "window_end": window_end,
        "source": body.get("source") or "BYBIT_MAINNET_LINEAR",
        "freshness": body.get("freshness") or ("LIVE" if points else "NO_DATA"),
        "point_count": len(points),
        "insufficient": len(points) < 2,
        "fabricated": False,
        "invented_candles": False,
        "equal_space_ticks": False,
        "interval_ms": _interval_ms(interval),
        "points": points,
        "error": None if ok else (body.get("error") or ("insufficient_history" if points else "no_data")),
        "generatedAt": body.get("generatedAt") or int(time.time() * 1000),
        "researchOnly": True,
        "private_api": False,
    }


def fetch_market_series(
    symbol: str,
    *,
    interval: str = "15m",
    limit: int = 96,
    window_label: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Fetch official authorized history and return market-series contract."""
    sym = symbol.upper().strip()
    lim = max(1, min(int(limit or 96), _BAR_LIMIT))
    cache_key = f"{sym}|{interval}|{lim}"
    now = time.time()
    if use_cache and cache_key in _SERIES_CACHE:
        exp, cached = _SERIES_CACHE[cache_key]
        if now < exp:
            out = dict(cached)
            out["cache"] = "hit"
            return out

    body = fetch_ohlcv(sym, interval=interval, limit=lim)
    series = bars_to_market_series(body, window_label=window_label)
    series["cache"] = "miss"
    if series.get("ok"):
        _SERIES_CACHE[cache_key] = (now + _SERIES_CACHE_TTL_S, series)
    return series


def fetch_market_series_batch(
    symbols: list[str],
    *,
    interval: str = "5m",
    limit: int = 48,
    window_label: str | None = None,
    max_symbols: int = 24,
) -> dict[str, Any]:
    """Batch public-safe series for Pulse / Radar / Watchlist (capped)."""
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = str(raw or "").upper().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        uniq.append(sym)
        if len(uniq) >= max_symbols:
            break
    series_map: dict[str, Any] = {}
    for sym in uniq:
        series_map[sym] = fetch_market_series(
            sym, interval=interval, limit=limit, window_label=window_label, use_cache=True
        )
    return {
        "ok": True,
        "contract": MARKET_SERIES_CONTRACT,
        "interval": interval,
        "limit": limit,
        "window_label": window_label,
        "count": len(series_map),
        "series": series_map,
        "fabricated": False,
        "source": "BYBIT_MAINNET_LINEAR",
        "generatedAt": int(time.time() * 1000),
        "researchOnly": True,
    }
