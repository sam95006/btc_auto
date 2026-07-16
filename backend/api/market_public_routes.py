"""Public Mainnet market data proxy (MVP-22A).

Read-only Bybit Mainnet public REST only.
No API keys, no private endpoints, no orders, no account.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from flask import Flask, Response, jsonify, request

BYBIT_MAINNET_REST = "https://api.bybit.com"
ALLOWED_CATEGORY = "linear"
ALLOWED_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
_UA = "NEXUS-EATI-MVP22A-PublicMarket/1.0 (read-only)"


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _fetch_ticker(symbol: str) -> dict[str, Any]:
    qs = urllib.parse.urlencode({"category": ALLOWED_CATEGORY, "symbol": symbol})
    url = f"{BYBIT_MAINNET_REST}/v5/market/tickers?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as raw:
        payload = json.loads(raw.read().decode("utf-8"))
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(payload.get("retMsg") or "bybit_error")
    rows = ((payload.get("result") or {}).get("list")) or []
    if not rows:
        raise RuntimeError(f"empty_ticker:{symbol}")
    row = rows[0]
    return {
        "symbol": symbol,
        "source": "BYBIT_MAINNET_LINEAR",
        "priceType": "LAST",
        "lastPrice": float(row["lastPrice"]),
        "markPrice": float(row["markPrice"]) if row.get("markPrice") not in (None, "") else None,
        "indexPrice": float(row["indexPrice"]) if row.get("indexPrice") not in (None, "") else None,
        "bidPrice": float(row["bid1Price"]) if row.get("bid1Price") not in (None, "") else None,
        "askPrice": float(row["ask1Price"]) if row.get("ask1Price") not in (None, "") else None,
        "change24hPct": float(row["price24hPcnt"]) * 100.0
        if row.get("price24hPcnt") not in (None, "")
        else None,
        "exchangeTimestamp": int(row["ts"]) if row.get("ts") not in (None, "") else None,
        "raw": {
            "lastPrice": row.get("lastPrice"),
            "markPrice": row.get("markPrice"),
            "indexPrice": row.get("indexPrice"),
            "bid1Price": row.get("bid1Price"),
            "ask1Price": row.get("ask1Price"),
            "price24hPcnt": row.get("price24hPcnt"),
            "ts": row.get("ts"),
        },
    }


def register_market_public_routes(app: Flask) -> None:
    """Mount read-only public market routes. Safe to call once at startup."""

    @app.route("/api/market/tickers")
    def market_tickers_public():
        category = (request.args.get("category") or ALLOWED_CATEGORY).strip().lower()
        if category != ALLOWED_CATEGORY:
            return _no_store(jsonify({"ok": False, "error": "category_must_be_linear"})), 400
        raw_symbols = (request.args.get("symbols") or ",".join(ALLOWED_SYMBOLS)).upper()
        wanted = [s.strip() for s in raw_symbols.split(",") if s.strip()]
        if not wanted:
            wanted = list(ALLOWED_SYMBOLS)
        for sym in wanted:
            if sym not in ALLOWED_SYMBOLS:
                return _no_store(jsonify({"ok": False, "error": f"symbol_not_allowed:{sym}"})), 400
        tickers = []
        errors = []
        for sym in wanted:
            try:
                tickers.append(_fetch_ticker(sym))
            except (urllib.error.URLError, TimeoutError, RuntimeError, KeyError, ValueError, TypeError) as exc:
                errors.append({"symbol": sym, "error": str(exc)})
        status = 200 if tickers else 502
        body = {
            "ok": bool(tickers),
            "read_only": True,
            "private_api": False,
            "api_key_used": False,
            "environment": "BYBIT_MAINNET_PUBLIC",
            "category": ALLOWED_CATEGORY,
            "headline_price_field": "lastPrice",
            "tickers": tickers,
            "errors": errors,
            "cache": "no-store",
        }
        return _no_store(jsonify(body)), status

    @app.route("/api/market/health")
    def market_public_health():
        return _no_store(
            jsonify(
                {
                    "ok": True,
                    "read_only": True,
                    "environment": "BYBIT_MAINNET_PUBLIC",
                    "category": ALLOWED_CATEGORY,
                    "symbols": list(ALLOWED_SYMBOLS),
                    "private_api": False,
                }
            )
        )
