"""Flask routes for Public Live Data Adapter (local/staging, read-only GET)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_public_live_data import adapter
from backend.nexus_public_live_data.constants import MODE_FIXTURE


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-NEXUS-Live-Data-Adapter"] = "read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    resp.headers["X-NEXUS-Exchange-Write"] = "false"
    mode = request.args.get("mode")
    resolved = adapter.resolve_mode(mode)
    resp.headers["X-NEXUS-Data-Mode"] = resolved
    if resolved == MODE_FIXTURE:
        resp.headers["X-NEXUS-DEMO-DATA"] = "DEMO_DATA"
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


def register_public_live_data_routes(app: Flask) -> None:
    """Mount read-only live data adapter routes. Safe for local/staging."""

    prefix = "/api/public/live-data"

    @app.before_request
    def _live_data_reject_mutations():
        if not request.path.startswith(prefix):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return _method_not_allowed()

    @app.route(f"{prefix}/meta")
    def live_data_meta():
        mode = request.args.get("mode")
        return _no_store(jsonify(adapter.service_meta(mode=mode)))

    @app.route(f"{prefix}/catalog")
    def live_data_catalog():
        mode = request.args.get("mode")
        return _no_store(jsonify(adapter.field_catalog(mode=mode)))

    @app.route(f"{prefix}/bindings")
    def live_data_bindings():
        mode = request.args.get("mode")
        return _no_store(jsonify(adapter.bind_all(mode=mode)))

    @app.route(f"{prefix}/fields/<path:field_id>")
    def live_data_field(field_id: str):
        mode = request.args.get("mode")
        try:
            return _no_store(jsonify(adapter.bind_field_response(field_id, mode=mode)))
        except KeyError:
            return _no_store(
                jsonify(
                    {
                        "ok": False,
                        "error": "unknown_field",
                        "field_id": field_id,
                        "read_only": True,
                    }
                )
            ), 404
