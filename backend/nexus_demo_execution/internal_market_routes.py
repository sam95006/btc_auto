"""Internal market intelligence routes — single-service, no Stage3 HTTP dependency."""
from __future__ import annotations

import os
import threading
import time
from typing import Any

from flask import Flask, jsonify

from backend.nexus_demo_execution.bounded_universe import scan_dynamic_candidates
from backend.nexus_demo_execution.component_health import set_component, snapshot as health_snapshot
from backend.nexus_demo_execution.fee_rate import fee_policy_public_status

_LOCK = threading.Lock()
_LATEST: dict[str, Any] = {
    "updated_at": None,
    "candidates": [],
    "scan_meta": {},
    "geometry_complete_count": 0,
    "geometry_missing_count": 0,
}


def latest_market_snapshot() -> dict[str, Any]:
    with _LOCK:
        return dict(_LATEST)


def run_readonly_market_scan(*, limit: int = 8) -> dict[str, Any]:
    set_component("market_worker_health", "HEALTHY")
    try:
        candidates, meta = scan_dynamic_candidates(limit=limit)
        rows = [c.to_dict() for c in candidates]
        complete = sum(1 for r in rows if r.get("geometry_status") == "GEOMETRY_INPUTS_COMPLETE")
        missing = sum(1 for r in rows if r.get("geometry_status") != "GEOMETRY_INPUTS_COMPLETE")
        payload = {
            "updated_at": time.time(),
            "candidates": rows,
            "scan_meta": meta,
            "geometry_complete_count": complete,
            "geometry_missing_count": missing,
            "market_owner": "INTERNAL_MARKET_INTELLIGENCE",
            "stage3_dependency_required": False,
        }
        with _LOCK:
            _LATEST.clear()
            _LATEST.update(payload)
        set_component("market_worker_health", "HEALTHY")
        return payload
    except Exception as exc:  # noqa: BLE001
        set_component("market_worker_health", "ERROR")
        return {"ok": False, "error": type(exc).__name__, "stage3_dependency_required": False}


def build_market_status() -> dict[str, Any]:
    snap = latest_market_snapshot()
    single = (os.environ.get("NEXUS_SINGLE_SERVICE") or "").strip().lower() in {"1", "true", "yes", "on"}
    fee = fee_policy_public_status()
    return {
        "ok": True,
        "status": "OK",
        "service": "nexus-bybit-demo-learning-validation",
        "market_owner": "INTERNAL_MARKET_INTELLIGENCE",
        "stage3_dependency_required": False,
        "external_control_plane_dependency_required": False,
        "single_service": single,
        "updated_at": snap.get("updated_at"),
        "candidate_count": len(snap.get("candidates") or []),
        "geometry_complete_count": snap.get("geometry_complete_count") or 0,
        "geometry_missing_count": snap.get("geometry_missing_count") or 0,
        "fee_policy": fee,
        "component_health": health_snapshot(),
        # Compatibility fields consumed by Control Plane aggregator funnel
        "universe_count": len(snap.get("candidates") or []) or (snap.get("scan_meta") or {}).get("tier1_count"),
        "tradable_count": len(snap.get("candidates") or []),
    }


def register_internal_market_routes(app: Flask) -> None:
    @app.route("/api/nexus/market/status", methods=["GET"])
    def market_status():
        return jsonify(build_market_status())

    # Compatibility alias so Control Plane aggregator can stop calling Stage3 hosts.
    @app.route("/api/nexus/stage3/status", methods=["GET"])
    def stage3_status_alias_internal():
        body = build_market_status()
        body["alias_of"] = "/api/nexus/market/status"
        body["legacy_stage3_execution"] = False
        return jsonify(body)

    @app.route("/api/nexus/market/scan-readonly", methods=["GET", "POST"])
    def market_scan_readonly():
        # Read-only scan — never places orders.
        out = run_readonly_market_scan(limit=8)
        out["ok"] = "error" not in out
        out["exchange_write"] = False
        return jsonify(out)

    @app.route("/api/nexus/market/latest-candidates", methods=["GET"])
    def market_latest_candidates():
        snap = latest_market_snapshot()
        return jsonify({"ok": True, "exchange_write": False, **snap})

    @app.route("/api/nexus/fee-policy", methods=["GET"])
    def fee_policy():
        return jsonify({"ok": True, **fee_policy_public_status()})
