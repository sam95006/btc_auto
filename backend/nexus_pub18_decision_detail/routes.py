"""Flask routes for PUB18-B Decision Detail transparency (read-only GET)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_pub18_decision_detail import service
from backend.nexus_pub18_decision_detail.hard_bans import run_three_passes


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-NEXUS-Decision-Detail"] = "read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    resp.headers["X-NEXUS-Exchange-API"] = "false"
    resp.headers["X-NEXUS-Learning-Transparency"] = "aggregates-only"
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


def register_pub18_decision_detail_routes(app: Flask) -> None:
    """Mount read-only Decision Detail / Learning Transparency routes."""

    prefix = "/api/public/decision-detail"

    @app.before_request
    def _decision_detail_reject_mutations():
        if not request.path.startswith(prefix):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return _method_not_allowed()

    @app.route(f"{prefix}/meta")
    def decision_detail_meta():
        return _no_store(jsonify(service.service_meta()))

    @app.route(f"{prefix}/default")
    def decision_detail_default():
        return _no_store(jsonify(service.default_member_decision_detail()))

    @app.route(f"{prefix}/cases")
    def decision_detail_cases():
        return _no_store(jsonify(service.list_decision_details()))

    @app.route(f"{prefix}/cases/<case_id>")
    def decision_detail_case(case_id: str):
        body = service.get_decision_detail(case_id)
        code = 200 if body.get("ok") else 404
        return _no_store(jsonify(body)), code

    @app.route(f"{prefix}/passes")
    def decision_detail_passes():
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return _no_store(jsonify(run_three_passes(root)))
