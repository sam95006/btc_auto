"""Flask routes for PUB17-D subscription product boundary."""
from __future__ import annotations

from typing import Any, Optional

from backend.nexus_public_subscription_boundary.hard_bans import HardBanViolation
from backend.nexus_public_subscription_boundary.service import SubscriptionBoundaryService


def create_subscription_boundary_blueprint(
    service: Optional[SubscriptionBoundaryService] = None,
):
    """Lazy Flask blueprint factory — LOCAL_OR_STAGING_ONLY."""
    try:
        from flask import Blueprint, jsonify, request
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Flask is required to mount subscription boundary routes") from exc

    svc = service or SubscriptionBoundaryService()
    bp = Blueprint(
        "nexus_public_subscription_boundary",
        __name__,
        url_prefix="/api/public/subscription",
    )

    def _err(exc: Exception, code: int = 400):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": str(exc),
                    "hard_ban": isinstance(exc, HardBanViolation),
                    "execution_controls": False,
                    "member_execution_control_count": 0,
                }
            ),
            code,
        )

    def _no_store(resp):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-NEXUS-Subscription-Boundary"] = "pub17-d"
        resp.headers["X-NEXUS-Execution-Controls"] = "false"
        resp.headers["X-NEXUS-Live-Billing"] = "false"
        return resp

    @bp.get("/foundation")
    def foundation():
        return _no_store(jsonify({"ok": True, "foundation": svc.foundation_status()}))

    @bp.get("/catalog")
    def catalog():
        return _no_store(jsonify({"ok": True, "catalog": svc.catalog()}))

    @bp.get("/entitlements/<tier>")
    def entitlements(tier: str):
        try:
            return _no_store(
                jsonify({"ok": True, "entitlements": svc.entitlement_snapshot(tier)})
            )
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/access")
    def access():
        body = request.get_json(silent=True) or {}
        try:
            return _no_store(
                jsonify(
                    {
                        "ok": True,
                        "access": svc.access_for(
                            account_id=str(body.get("account_id", "")),
                            tier=str(body.get("tier", "Free")),
                        ),
                    }
                )
            )
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/authorize")
    def authorize():
        body = request.get_json(silent=True) or {}
        try:
            result = svc.authorize(
                account_id=str(body.get("account_id", "")),
                product_id=str(body.get("product_id", "")),
                action=str(body.get("action", "read")),
            )
            return _no_store(jsonify(result))
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/grant")
    def grant():
        """Manual non-production grant — refuses forbidden / execution products."""
        body = request.get_json(silent=True) or {}
        try:
            result = svc.grant_manual(
                account_id=str(body.get("account_id", "")),
                tier=str(body.get("tier", "Free")),
                product_id=str(body.get("product_id", "")),
                actor=str(body.get("actor", "manual_operator")),
            )
            return _no_store(jsonify({"ok": True, "grant": result}))
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.get("/audit")
    def audit():
        account_id = request.args.get("account_id")
        return _no_store(
            jsonify({"ok": True, "events": svc.audit_events(account_id=account_id)})
        )

    @bp.post("/nav/web-check")
    def web_nav_check():
        body = request.get_json(silent=True) or {}
        paths = list(body.get("paths") or [])
        try:
            return _no_store(jsonify({"ok": True, "nav": svc.web_nav_check(paths)}))
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/nav/mobile-check")
    def mobile_nav_check():
        body = request.get_json(silent=True) or {}
        routes = list(body.get("routes") or [])
        try:
            return _no_store(
                jsonify({"ok": True, "nav": svc.mobile_nav_check(routes)})
            )
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.get("/execution-control-count")
    def execution_control_count():
        scan = svc.execution_control_count()
        return _no_store(
            jsonify(
                {
                    "ok": scan["member_execution_control_count"] == 0,
                    **scan,
                }
            )
        )

    # Explicitly refuse execution-product purchase endpoints.
    @bp.post("/buy/<product_id>")
    def buy(product_id: str):
        body = request.get_json(silent=True) or {}
        try:
            result = svc.authorize(
                account_id=str(body.get("account_id", "anonymous")),
                product_id=product_id,
                action="buy",
            )
            return _no_store(jsonify(result))
        except HardBanViolation as exc:
            return _err(exc, 403)

    return bp


def register_subscription_boundary_routes(app: Any, service: Optional[SubscriptionBoundaryService] = None) -> None:
    app.register_blueprint(create_subscription_boundary_blueprint(service))
