"""Flask routes for PUB17-B Market Pulse first screen (read-only GET)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_pub17_market_pulse import service
from backend.nexus_pub17_market_pulse.hard_bans import run_three_passes


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-NEXUS-Market-Pulse"] = "read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    resp.headers["X-NEXUS-Exchange-API"] = "false"
    resp.headers["X-NEXUS-Analysis-Only"] = "true"
    return resp


def _method_not_allowed():
    return _no_store(
        jsonify(
            {
                "ok": False,
                "error": "method_not_allowed",
                "read_only": True,
                "allowed": ["GET", "HEAD", "OPTIONS"],
                "customer_trading": False,
            }
        )
    ), 405


def register_pub17_market_pulse_routes(app: Flask) -> None:
    """Mount read-only Market Pulse / Top Opportunities routes."""

    prefix = "/api/public/market-pulse"

    @app.before_request
    def _market_pulse_reject_mutations():
        if not request.path.startswith(prefix):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return _method_not_allowed()

    @app.route(f"{prefix}/meta")
    def market_pulse_meta():
        return _no_store(jsonify(service.service_meta()))

    @app.route(f"{prefix}/home")
    def market_pulse_home():
        return _no_store(jsonify(service.default_member_home_screen()))

    @app.route(f"{prefix}/screens")
    def market_pulse_screens():
        return _no_store(jsonify(service.list_first_screens()))

    @app.route(f"{prefix}/screens/<case_id>")
    def market_pulse_screen_detail(case_id: str):
        body = service.get_first_screen(case_id)
        code = 200 if body.get("ok") else 404
        return _no_store(jsonify(body)), code

    @app.route(f"{prefix}/passes")
    def market_pulse_passes():
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return _no_store(jsonify(run_three_passes(root)))
