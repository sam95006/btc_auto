"""Read-only Market Scanner APIs (Product Transformation Phase 1).

No private API · no trading · no Recommendation coupling.
"""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.market.scanner.scanner_service import get_market_scanner


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def register_market_scanner_routes(app: Flask) -> None:
    """Mount scanner routes. Safe to call once at startup."""

    @app.route("/api/market/scanner/status")
    def market_scanner_status():
        scanner = get_market_scanner()
        return _no_store(jsonify(scanner.status()))

    @app.route("/api/market/scanner/universe")
    def market_scanner_universe():
        scanner = get_market_scanner()
        return _no_store(jsonify(scanner.universe()))

    @app.route("/api/market/scanner/candidates")
    def market_scanner_candidates():
        scanner = get_market_scanner()
        side = (request.args.get("side") or "").strip() or None
        try:
            limit = int(request.args.get("limit") or 40)
        except ValueError:
            limit = 40
        return _no_store(jsonify(scanner.candidates(side=side, limit=limit)))

    @app.route("/api/market/scanner/symbol/<symbol>")
    def market_scanner_symbol(symbol: str):
        scanner = get_market_scanner()
        body = scanner.symbol_detail(symbol)
        status = 200 if body.get("ok") else 404
        return _no_store(jsonify(body)), status

    @app.route("/api/market/scanner/events")
    def market_scanner_events():
        scanner = get_market_scanner()
        try:
            limit = int(request.args.get("limit") or 30)
        except ValueError:
            limit = 30
        return _no_store(jsonify(scanner.events(limit=limit)))

    @app.route("/api/market/scanner/charts")
    def market_scanner_charts():
        scanner = get_market_scanner()
        return _no_store(jsonify(scanner.charts()))
