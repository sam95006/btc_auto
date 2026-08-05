"""Flask routes for Public Decision Cloud (local/staging, read-only GET)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_public_decision_cloud import service


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-NEXUS-Decision-Cloud"] = "read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    resp.headers["X-NEXUS-Exchange-API"] = "false"
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


def _caller_org_ids() -> set[str]:
    raw = request.headers.get("X-NEXUS-Caller-Orgs", "")
    return {p.strip() for p in raw.split(",") if p.strip()}


def _decision_response(body: dict):
    # Opaque deny uses identical 404 shape for missing and unauthorized.
    code = 200 if body.get("ok") else 404
    return _no_store(jsonify(body)), code


def register_public_decision_cloud_routes(app: Flask) -> None:
    """Mount read-only Decision Cloud routes. Safe for local/staging."""

    prefix = "/api/public/decision-cloud"

    @app.before_request
    def _decision_cloud_reject_mutations():
        if not request.path.startswith(prefix):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return _method_not_allowed()

    @app.route(f"{prefix}/meta")
    def decision_cloud_meta():
        return _no_store(jsonify(service.service_meta()))

    @app.route(f"{prefix}/market-overview")
    def decision_cloud_market_overview():
        return _no_store(jsonify(service.market_overview()))

    @app.route(f"{prefix}/decisions")
    def decision_cloud_feed():
        status = request.args.get("status")
        return _no_store(
            jsonify(service.decision_feed(status=status, caller_org_ids=_caller_org_ids()))
        )

    @app.route(f"{prefix}/decisions/<decision_id>")
    def decision_cloud_detail(decision_id: str):
        body = service.decision_detail(decision_id, caller_org_ids=_caller_org_ids())
        return _decision_response(body)

    @app.route(f"{prefix}/decisions/<decision_id>/evidence")
    def decision_cloud_evidence(decision_id: str):
        body = service.evidence_for(decision_id, caller_org_ids=_caller_org_ids())
        return _decision_response(body)

    @app.route(f"{prefix}/decisions/<decision_id>/counter-evidence")
    def decision_cloud_counter_evidence(decision_id: str):
        body = service.counter_evidence_for(
            decision_id, caller_org_ids=_caller_org_ids()
        )
        return _decision_response(body)

    @app.route(f"{prefix}/decisions/<decision_id>/risk")
    def decision_cloud_risk(decision_id: str):
        body = service.risk_for(decision_id, caller_org_ids=_caller_org_ids())
        return _decision_response(body)

    @app.route(f"{prefix}/thesis-monitor")
    def decision_cloud_thesis_monitor():
        return _no_store(jsonify(service.thesis_monitor()))

    @app.route(f"{prefix}/decision-memory")
    def decision_cloud_memory():
        return _no_store(jsonify(service.decision_memory()))

    @app.route(f"{prefix}/outcome-review")
    def decision_cloud_outcome_review():
        decision_id = request.args.get("decision_id")
        return _no_store(
            jsonify(
                service.outcome_review(
                    decision_id=decision_id, caller_org_ids=_caller_org_ids()
                )
            )
        )

    @app.route(f"{prefix}/alerts")
    def decision_cloud_alerts():
        return _no_store(jsonify(service.alerts()))

    @app.route(f"{prefix}/freshness")
    def decision_cloud_freshness():
        return _no_store(
            jsonify(service.freshness_report(caller_org_ids=_caller_org_ids()))
        )
