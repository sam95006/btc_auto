"""Read-only Control Plane HTTP routes — never proxy trading writes."""
from __future__ import annotations

from typing import Any

from flask import Flask, jsonify

from backend.nexus_control_plane.aggregator import ControlPlaneAggregator
from backend.nexus_control_plane.federation_client import FederationClient
from backend.nexus_control_plane.service_registry import ServiceRegistry

_FORBIDDEN_WRITE_HINT = {
    "ok": False,
    "error": "CONTROL_PLANE_READ_ONLY",
    "detail": "Control Plane rejects POST/PUT/PATCH/DELETE and never proxies order/session writes",
    "exchange_write": False,
}


def register_control_plane_routes(app: Flask) -> None:
    registry = ServiceRegistry.from_env()
    client = FederationClient(registry=registry)
    agg = ControlPlaneAggregator(registry=registry, client=client)

    def _ok(payload: dict[str, Any], code: int = 200):
        body = dict(payload)
        body.setdefault("ok", True)
        body.setdefault("control_plane", True)
        body.setdefault("exchange_write", False)
        body.setdefault("mainnet", False)
        body.setdefault("real_money", False)
        return jsonify(body), code

    @app.route("/api/nexus/control-plane/overview", methods=["GET"])
    def control_plane_overview():
        try:
            return _ok({"overview": agg.overview()})
        except Exception as exc:  # noqa: BLE001 — never 500 whole site on child failure
            return _ok(
                {
                    "ok": True,
                    "overview": {"error": type(exc).__name__, "note": "partial_failure_isolated"},
                }
            )

    @app.route("/api/nexus/control-plane/services", methods=["GET"])
    def control_plane_services():
        return _ok({"services": agg.services()})

    @app.route("/api/nexus/control-plane/market", methods=["GET"])
    def control_plane_market():
        return _ok(agg.market())

    @app.route("/api/nexus/control-plane/demo-session", methods=["GET"])
    def control_plane_demo_session():
        return _ok({"demo_session": agg.demo_session()})

    @app.route("/api/nexus/control-plane/positions", methods=["GET"])
    def control_plane_positions():
        return _ok({"positions": agg.positions()})

    @app.route("/api/nexus/control-plane/performance", methods=["GET"])
    def control_plane_performance():
        return _ok({"performance": agg.performance()})

    @app.route("/api/nexus/control-plane/learning", methods=["GET"])
    def control_plane_learning():
        return _ok({"learning": agg.learning()})

    @app.route("/api/nexus/control-plane/runtime-identity", methods=["GET"])
    def control_plane_runtime_identity():
        return _ok({"runtime_identity": agg.runtime_identity()})

    @app.route("/api/nexus/control-plane/orders", methods=["POST", "PUT", "PATCH", "DELETE"])
    def control_plane_orders_blocked():
        return jsonify(_FORBIDDEN_WRITE_HINT), 405

    @app.route("/api/nexus/control-plane/session/start", methods=["POST", "PUT", "PATCH", "DELETE"])
    def control_plane_session_start_blocked():
        return jsonify(_FORBIDDEN_WRITE_HINT), 405

    @app.route("/api/nexus/control-plane/session/stop", methods=["POST", "PUT", "PATCH", "DELETE"])
    def control_plane_session_stop_blocked():
        return jsonify(_FORBIDDEN_WRITE_HINT), 405

    @app.route("/api/nexus/control-plane/position/close", methods=["POST", "PUT", "PATCH", "DELETE"])
    def control_plane_position_close_blocked():
        return jsonify(_FORBIDDEN_WRITE_HINT), 405
