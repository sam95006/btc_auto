"""Flask routes for PUB18-A Live Funnel + Market Pulse (read-only GET)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_pub18_live_funnel import service
from backend.nexus_pub18_live_funnel.hard_bans import run_three_passes


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-NEXUS-Live-Funnel"] = "read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    resp.headers["X-NEXUS-Exchange-API"] = "false"
    resp.headers["X-NEXUS-Analysis-Only"] = "true"
    resp.headers["X-NEXUS-Trade-Buttons"] = "false"
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
                "execution_control_count": 0,
                "trade_buttons": False,
            }
        )
    ), 405


def register_pub18_live_funnel_routes(app: Flask) -> None:
    """Mount read-only Live Funnel / Market Pulse routes."""

    prefix = "/api/public/live-funnel"

    @app.before_request
    def _live_funnel_reject_mutations():
        if not request.path.startswith(prefix):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return _method_not_allowed()

    @app.route(f"{prefix}/meta")
    def live_funnel_meta():
        return _no_store(jsonify(service.service_meta()))

    @app.route(f"{prefix}/home")
    def live_funnel_home():
        return _no_store(jsonify(service.default_member_home_screen()))

    @app.route(f"{prefix}/screens")
    def live_funnel_screens():
        return _no_store(jsonify(service.list_first_screens()))

    @app.route(f"{prefix}/screens/<case_id>")
    def live_funnel_screen_detail(case_id: str):
        body = service.get_first_screen(case_id)
        code = 200 if body.get("ok") else 404
        return _no_store(jsonify(body)), code

    @app.route(f"{prefix}/passes")
    def live_funnel_passes():
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return _no_store(jsonify(run_three_passes(root)))
