"""Flask routes for UX-B Member Web Intelligence Experience (read-only GET)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_public_member_intel import service
from backend.nexus_public_member_intel.hard_bans import run_three_passes


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-NEXUS-Member-Intel"] = "read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    resp.headers["X-NEXUS-Exchange-API"] = "false"
    resp.headers["X-NEXUS-Demo-Data"] = "DEMO_DATA"
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


def register_public_member_intel_routes(app: Flask) -> None:
    """Mount read-only Member Intelligence Experience routes."""

    prefix = "/api/public/member-intel"

    @app.before_request
    def _member_intel_reject_mutations():
        if not request.path.startswith(prefix):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return _method_not_allowed()

    @app.route(f"{prefix}/meta")
    def member_intel_meta():
        return _no_store(jsonify(service.service_meta()))

    @app.route(f"{prefix}/experiences")
    def member_intel_experiences():
        return _no_store(jsonify(service.list_experiences()))

    @app.route(f"{prefix}/experiences/<case_id>")
    def member_intel_experience_detail(case_id: str):
        body = service.get_experience(case_id)
        code = 200 if body.get("ok") else 404
        return _no_store(jsonify(body)), code

    @app.route(f"{prefix}/states")
    def member_intel_states():
        return _no_store(jsonify(service.state_matrix()))

    @app.route(f"{prefix}/passes")
    def member_intel_passes():
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return _no_store(jsonify(run_three_passes(root)))
