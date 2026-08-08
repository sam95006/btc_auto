"""Public Full-Market Live Radar APIs (V18.2.16).

GET /api/nexus/public/radar
GET /api/nexus/public/radar/events
GET /api/nexus/public/radar/<symbol>

Read-only · rank_authority=SERVER · member_execution=0.
"""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.market.live_radar.full_market_radar_service import get_full_market_radar


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def register_public_radar_routes(app: Flask) -> None:
    """Mount public radar routes. Safe to call once at startup."""

    @app.route("/api/nexus/public/radar")
    def nexus_public_radar():
        try:
            limit = int(request.args.get("limit") or 40)
        except ValueError:
            limit = 40
        tab = (request.args.get("tab") or "ALL").strip() or "ALL"
        force = str(request.args.get("force") or "").lower() in ("1", "true", "yes")
        body = get_full_market_radar().public_radar(limit=limit, tab=tab, force=force)
        status = 200 if body.get("ok", True) else 503
        return _no_store(jsonify(body)), status

    @app.route("/api/nexus/public/radar/events")
    def nexus_public_radar_events():
        try:
            limit = int(request.args.get("limit") or 50)
        except ValueError:
            limit = 50
        symbol = (request.args.get("symbol") or "").strip() or None
        body = get_full_market_radar().public_events(limit=limit, symbol=symbol)
        return _no_store(jsonify(body))

    @app.route("/api/nexus/public/radar/<symbol>")
    def nexus_public_radar_symbol(symbol: str):
        body = get_full_market_radar().public_symbol(symbol)
        status = 200 if body.get("ok") else 404
        return _no_store(jsonify(body)), status
