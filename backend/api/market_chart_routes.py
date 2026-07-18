"""Chart data APIs — Bybit public only (Phase 3)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.market.charts import bybit_public_charts as charts


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


def register_market_chart_routes(app: Flask) -> None:
    @app.route("/api/market/charts/ohlcv")
    def market_charts_ohlcv():
        symbol = (request.args.get("symbol") or "BTCUSDT").strip()
        interval = (request.args.get("interval") or "5m").strip()
        try:
            limit = int(request.args.get("limit") or 120)
        except ValueError:
            limit = 120
        start = request.args.get("from") or request.args.get("start")
        end = request.args.get("to") or request.args.get("end")
        body = charts.fetch_ohlcv(
            symbol,
            interval=interval,
            limit=limit,
            start=int(start) if start else None,
            end=int(end) if end else None,
        )
        return _no_store(jsonify(body))

    @app.route("/api/market/charts/open-interest")
    def market_charts_oi():
        symbol = (request.args.get("symbol") or "BTCUSDT").strip()
        interval = (request.args.get("interval") or "5m").strip()
        try:
            limit = int(request.args.get("limit") or 100)
        except ValueError:
            limit = 100
        return _no_store(jsonify(charts.fetch_open_interest(symbol, interval=interval, limit=limit)))

    @app.route("/api/market/charts/funding")
    def market_charts_funding():
        return _no_store(jsonify(charts.funding_series_status()))
