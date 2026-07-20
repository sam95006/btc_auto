"""NEXUS Phase 6.5 Gate K — Founder Private Core (fail-closed on Live).

Production / Zeabur: routes remain disabled until verified Founder auth exists.
Client headers / query params cannot grant Founder access.
Execution always disabled this phase.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.governance.entitlements import (
    audit_event,
    founder_routes_enabled,
    require_entitlement,
    resolve_actor_context,
)

founder_private_bp = Blueprint("founder_private", __name__)


def _deny(msg: str, code: int = 403):
    resp = jsonify({
        "ok": False,
        "error": msg,
        "researchOnly": True,
        "founderOnly": True,
        "realExecutionEnabled": False,
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp, code


def _reject_client_identity_spoof() -> str | None:
    """Reject any attempt to forge Founder via header/query."""
    # Headers that must never grant access
    for h in ("X-Nexus-Role", "X-Nexus-Tier", "X-Founder", "X-Operator-Role"):
        if request.headers.get(h):
            return f"fake_header_rejected:{h}"
    for q in ("tier", "role", "founder", "asFounder"):
        if request.args.get(q) is not None:
            return f"fake_query_rejected:{q}"
    return None


@founder_private_bp.route("/api/nexus/founder/status")
def founder_status():
    spoof = _reject_client_identity_spoof()
    if spoof:
        audit_event(
            "founder.status.read",
            "founder_core",
            permission="founder.production_control",
            result="DENIED",
            reason=spoof,
        )
        return _deny(spoof)

    if not founder_routes_enabled():
        audit_event(
            "founder.status.read",
            "founder_core",
            permission="founder.production_control",
            result="DENIED",
            reason="founder_routes_disabled",
        )
        return _deny("founder_routes_disabled")

    actor = resolve_actor_context()
    allowed, reason = require_entitlement("founder.production_control")
    audit_event(
        "founder.status.read",
        "founder_core",
        permission="founder.production_control",
        result="OK" if allowed else "DENIED",
        reason=reason or "",
    )
    if not allowed:
        return _deny(reason or "founder_only")

    # Never expose execution controls even to Founder this phase
    return jsonify({
        "ok": True,
        "researchOnly": True,
        "founderOnly": True,
        "tier": actor.tier.value,
        "identitySource": actor.identity_source,
        "realExecutionEnabled": False,
        "armEnabled": False,
        "productionPromotionEnabled": False,
        "capabilities": [
            "strategy_config_view",
            "patch_approval_view",
            "model_promotion_view",
        ],
        "note": "Founder core boundary — execution remains disabled; live routes fail-closed by default",
    }), 200


@founder_private_bp.route("/api/nexus/founder/autonomous-execution", methods=["POST"])
def founder_autonomous_execution():
    spoof = _reject_client_identity_spoof()
    if spoof:
        audit_event(
            "founder.autonomous_execution.attempt",
            "founder_core",
            permission="founder.autonomous_execution",
            result="DENIED",
            reason=spoof,
        )
        return _deny(spoof)

    body = request.get_json(silent=True) or {}
    if not body.get("researchOnly"):
        return _deny("researchOnly required", 400)

    audit_event(
        "founder.autonomous_execution.attempt",
        "founder_core",
        permission="founder.autonomous_execution",
        result="DENIED",
        reason="execution_disabled_phase65",
    )
    # Always deny — even authenticated Founder cannot execute this phase
    return _deny("autonomous execution disabled — founder boundary enforced")


def register_founder_private_routes(app) -> None:
    app.register_blueprint(founder_private_bp)
