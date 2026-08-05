"""Flask routes for PUB2-A Decision Product E2E (read-only GET)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_public_decision_product import service
from backend.nexus_public_decision_product.journey import JourneyError


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-NEXUS-Decision-Product"] = "e2e-read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    resp.headers["X-NEXUS-Exchange-API"] = "false"
    resp.headers["X-NEXUS-Execution-Controls"] = "false"
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
                "execution_controls": False,
            }
        )
    ), 405


def register_public_decision_product_routes(app: Flask) -> None:
    """Mount read-only Decision Product E2E routes."""

    prefix = "/api/public/decision-product"

    @app.before_request
    def _decision_product_reject_mutations():
        if not request.path.startswith(prefix):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return _method_not_allowed()

    @app.route(f"{prefix}/meta")
    def decision_product_meta():
        return _no_store(jsonify(service.service_meta()))

    @app.route(f"{prefix}/e2e")
    def decision_product_e2e():
        decision_id = request.args.get("decision_id")
        try:
            body = service.run_e2e(decision_id=decision_id)
            return _no_store(jsonify(body))
        except JourneyError as exc:
            return _no_store(
                jsonify(
                    {
                        "ok": False,
                        "error": str(exc),
                        "read_only": True,
                        "customer_trading": False,
                        "execution_controls": False,
                    }
                )
            ), 404

    @app.route(f"{prefix}/passes")
    def decision_product_passes():
        return _no_store(jsonify(service.three_pass_report()))
