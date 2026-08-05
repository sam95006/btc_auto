"""Flask routes for PUB2-B live UI bindings (local/staging, read-only GET)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_public_v2_live_binding import binder


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-NEXUS-Live-E2E-Binding"] = "read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    resp.headers["X-NEXUS-Exchange-Write"] = "false"
    resp.headers["X-NEXUS-Data-Mode"] = "LIVE"
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


def register_public_v2_live_binding_routes(app: Flask) -> None:
    prefix = "/api/public/v2/live-bindings"

    @app.before_request
    def _v2_live_reject_mutations():
        if not request.path.startswith(prefix):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return _method_not_allowed()

    @app.route(f"{prefix}")
    @app.route(f"{prefix}/")
    def v2_live_bindings_all():
        return _no_store(jsonify(binder.bind_all_components(mode="LIVE")))

    @app.route(f"{prefix}/components/<path:component_id>")
    def v2_live_binding_component(component_id: str):
        try:
            return _no_store(jsonify({"ok": True, **binder.bind_component(component_id)}))
        except KeyError:
            return _no_store(
                jsonify({"ok": False, "error": "unknown_component", "component_id": component_id})
            ), 404
