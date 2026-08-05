"""NEXUS Phase 6.5 Gate K — Founder Private Core (fail-closed on Live).

Production / Zeabur: routes remain disabled until verified Founder auth exists.
Client headers / query params cannot grant Founder access.
Execution always disabled this phase.

PUB-E / PUB2-D: Founder Private Operator UI snapshot is Founder-authorized
only, live/sim bound to private operational surfaces, and must never be
readable from a member session.

UX-C: Founder Operator Diagnostics — V16 research observe panels.
Observe / authorize research only. Member sessions fail-closed (403).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.founder_operator.diagnostics.panels import (
    DIAGNOSTIC_PANEL_IDS,
    assert_no_forbidden_keys as assert_diagnostics_no_forbidden_keys,
    build_founder_diagnostics_snapshot,
)
from backend.founder_operator.diagnostics.research_auth import authorize_research_observe
from backend.founder_operator.snapshot import (
    OPERATOR_PANEL_IDS,
    assert_no_forbidden_keys,
    build_founder_operator_snapshot,
)
from backend.governance.entitlements import (
    PlanTier,
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
        "memberAccessible": False,
        "realExecutionEnabled": False,
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp, code


def _reject_client_identity_spoof() -> str | None:
    """Reject any attempt to forge Founder via header/query."""
    for h in ("X-Nexus-Role", "X-Nexus-Tier", "X-Founder", "X-Operator-Role", "X-Member-As-Founder"):
        if request.headers.get(h):
            return f"fake_header_rejected:{h}"
    for q in ("tier", "role", "founder", "asFounder", "memberTier"):
        if request.args.get(q) is not None:
            return f"fake_query_rejected:{q}"
    return None


def _authorize_founder(action: str) -> tuple[object | None, object | None]:
    """Shared Founder gate. Returns (actor, deny_response) — deny_response set on failure."""
    spoof = _reject_client_identity_spoof()
    if spoof:
        audit_event(
            action,
            "founder_core",
            permission="founder.production_control",
            result="DENIED",
            reason=spoof,
        )
        return None, _deny(spoof)

    if not founder_routes_enabled():
        audit_event(
            action,
            "founder_core",
            permission="founder.production_control",
            result="DENIED",
            reason="founder_routes_disabled",
        )
        return None, _deny("founder_routes_disabled")

    actor = resolve_actor_context()
    # Explicit member-session rejection — even if routes somehow enabled.
    if actor.tier != PlanTier.FOUNDER and "FOUNDER" not in actor.roles:
        reason = f"member_session_denied:tier={actor.tier.value}"
        audit_event(
            action,
            "founder_core",
            permission="founder.production_control",
            result="DENIED",
            reason=reason,
        )
        return None, _deny(reason)

    allowed, reason = require_entitlement("founder.production_control")
    audit_event(
        action,
        "founder_core",
        permission="founder.production_control",
        result="OK" if allowed else "DENIED",
        reason=reason or "",
    )
    if not allowed:
        return None, _deny(reason or "founder_only")

    return actor, None


@founder_private_bp.route("/api/nexus/founder/status")
def founder_status():
    actor, denied = _authorize_founder("founder.status.read")
    if denied is not None:
        return denied

    # Never expose execution controls even to Founder this phase
    return jsonify({
        "ok": True,
        "researchOnly": True,
        "founderOnly": True,
        "memberAccessible": False,
        "tier": actor.tier.value,
        "identitySource": actor.identity_source,
        "realExecutionEnabled": False,
        "armEnabled": False,
        "productionPromotionEnabled": False,
        "operatorUiEnabled": True,
        "capabilities": [
            "strategy_config_view",
            "patch_approval_view",
            "model_promotion_view",
            "operator_ui_view",
        ],
        "note": "Founder core boundary — execution remains disabled; live routes fail-closed by default",
    }), 200


@founder_private_bp.route("/api/nexus/founder/operator")
@founder_private_bp.route("/api/nexus/founder/operator/overview")
def founder_operator_overview():
    """PUB-E Founder Private Operator UI snapshot — Founder auth required."""
    actor, denied = _authorize_founder("founder.operator.read")
    if denied is not None:
        return denied

    payload = build_founder_operator_snapshot(
        actor_tier=actor.tier.value,
        identity_source=actor.identity_source,
    )
    leaks = assert_no_forbidden_keys(payload)
    if leaks:
        audit_event(
            "founder.operator.read",
            "founder_operator_ui",
            permission="founder.production_control",
            result="DENIED",
            reason=f"forbidden_payload_keys:{','.join(leaks[:8])}",
        )
        return _deny("operator_payload_sanitizer_blocked", 500)

    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Nexus-Founder-Only"] = "1"
    resp.headers["X-Nexus-Member-Accessible"] = "0"
    return resp, 200


@founder_private_bp.route("/api/nexus/founder/operator/panels")
def founder_operator_panels():
    """List operator panel ids (Founder auth). No private metric bodies."""
    actor, denied = _authorize_founder("founder.operator.panels.read")
    if denied is not None:
        return denied
    return jsonify({
        "ok": True,
        "founderOnly": True,
        "memberAccessible": False,
        "panelIds": list(OPERATOR_PANEL_IDS),
        "tier": actor.tier.value,
    }), 200


@founder_private_bp.route("/api/nexus/founder/diagnostics")
@founder_private_bp.route("/api/nexus/founder/diagnostics/overview")
def founder_diagnostics_overview():
    """UX-C Founder Operator Diagnostics — Founder auth required, research observe only."""
    actor, denied = _authorize_founder("founder.diagnostics.read")
    if denied is not None:
        return denied

    payload = build_founder_diagnostics_snapshot(
        actor_tier=actor.tier.value,
        identity_source=actor.identity_source,
    )
    leaks = assert_diagnostics_no_forbidden_keys(payload)
    if leaks:
        audit_event(
            "founder.diagnostics.read",
            "founder_operator_diagnostics",
            permission="founder.production_control",
            result="DENIED",
            reason=f"forbidden_payload_keys:{','.join(leaks[:8])}",
        )
        return _deny("diagnostics_payload_sanitizer_blocked", 500)

    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Nexus-Founder-Only"] = "1"
    resp.headers["X-Nexus-Member-Accessible"] = "0"
    resp.headers["X-Nexus-Research-Only"] = "1"
    return resp, 200


@founder_private_bp.route("/api/nexus/founder/diagnostics/panels")
def founder_diagnostics_panels():
    """List diagnostics panel ids (Founder auth). No private metric bodies."""
    actor, denied = _authorize_founder("founder.diagnostics.panels.read")
    if denied is not None:
        return denied
    return jsonify({
        "ok": True,
        "founderOnly": True,
        "memberAccessible": False,
        "researchOnly": True,
        "panelIds": list(DIAGNOSTIC_PANEL_IDS),
        "tier": actor.tier.value,
    }), 200


@founder_private_bp.route("/api/nexus/founder/diagnostics/research-authorize", methods=["POST"])
def founder_diagnostics_research_authorize():
    """Authorize research observation only — never mainnet / real-trade."""
    actor, denied = _authorize_founder("founder.diagnostics.research_authorize")
    if denied is not None:
        return denied

    body = request.get_json(silent=True) or {}
    if body.get("researchOnly") is not True:
        return _deny("researchOnly required", 400)

    scope = str(body.get("scope") or "observe_diagnostics")
    result = authorize_research_observe(
        scope=scope,
        actor_tier=actor.tier.value,
        identity_source=actor.identity_source,
    )
    audit_event(
        "founder.diagnostics.research_authorize",
        "founder_operator_diagnostics",
        permission="founder.production_control",
        result="OK" if result.get("authorized") else "DENIED",
        reason=str(result.get("error") or result.get("scope") or ""),
    )
    code = 200 if result.get("ok") else 403
    resp = jsonify(result)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Nexus-Founder-Only"] = "1"
    resp.headers["X-Nexus-Member-Accessible"] = "0"
    return resp, code


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
