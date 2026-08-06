"""Flask routes — public Runtime Snapshot live binding (read-only)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_runtime_snapshot_v18_1.alerts import fixture_as_live_count
from backend.nexus_runtime_snapshot_v18_1.binder import build_bound_home
from backend.nexus_runtime_snapshot_v18_1.constants import HARD_BANS, PACKAGE, SCHEMA
from backend.nexus_runtime_snapshot_v18_1.hard_bans import run_phase_b_scans
from backend.nexus_runtime_snapshot_v18_1.loader import load_runtime_snapshot


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-NEXUS-Runtime-Snapshot"] = "read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    resp.headers["X-NEXUS-Trade-Buttons"] = "false"
    resp.headers["X-NEXUS-Actual-Ordered"] = "false"
    resp.headers["X-NEXUS-Actual-Filled"] = "false"
    return resp


def _method_not_allowed():
    return _no_store(
        jsonify(
            {
                "ok": False,
                "error": "method_not_allowed",
                "read_only": True,
                "allowed": ["GET", "HEAD", "OPTIONS"],
                "trade_buttons": False,
                "member_execution_control_count": 0,
            }
        )
    ), 405


def register_runtime_snapshot_routes(app: Flask) -> None:
    """Mount Phase B runtime snapshot routes (public + mobile consume)."""

    prefix = "/api/public/runtime-snapshot"
    # Also expose under /v1/public for mobile endpoint allowlist.
    v1_prefix = "/v1/public/intelligence/runtime-snapshot"

    @app.before_request
    def _runtime_snapshot_reject_mutations():
        path = request.path or ""
        if not (path.startswith(prefix) or path.startswith(v1_prefix)):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return _method_not_allowed()

    def _snapshot_body():
        return load_runtime_snapshot()

    def _bound_body():
        body = build_bound_home()
        body["fixture_as_live_count"] = fixture_as_live_count(body.get("alerts") or [])
        return body

    def _meta_body():
        return {
            "ok": True,
            "schema": SCHEMA,
            "package": PACKAGE,
            "hard_bans": list(HARD_BANS),
            "read_only": True,
            "trade_buttons": False,
            "endpoints": [
                f"{prefix}",
                f"{prefix}/bound",
                f"{prefix}/alerts",
                f"{prefix}/passes",
                f"{v1_prefix}",
                f"{v1_prefix}/bound",
            ],
        }

    @app.route(f"{prefix}")
    @app.route(f"{v1_prefix}")
    def runtime_snapshot_get():
        return _no_store(jsonify(_snapshot_body()))

    @app.route(f"{prefix}/bound")
    @app.route(f"{v1_prefix}/bound")
    def runtime_snapshot_bound():
        return _no_store(jsonify(_bound_body()))

    @app.route(f"{prefix}/alerts")
    @app.route(f"{v1_prefix}/alerts")
    def runtime_snapshot_alerts():
        body = _bound_body()
        return _no_store(
            jsonify(
                {
                    "ok": True,
                    "alerts": body.get("alerts") or [],
                    "fixture_as_live_count": body.get("fixture_as_live_count", 0),
                    "read_only": True,
                }
            )
        )

    @app.route(f"{prefix}/meta")
    @app.route(f"{v1_prefix}/meta")
    def runtime_snapshot_meta():
        return _no_store(jsonify(_meta_body()))

    @app.route(f"{prefix}/passes")
    def runtime_snapshot_passes():
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return _no_store(jsonify(run_phase_b_scans(root)))
