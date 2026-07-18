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
