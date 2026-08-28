"""Safe Flask alpha endpoints for the product backend.

Routes are read-only by default and deliberately have no execution, credential,
or provider-secret surfaces.  Database-backed actions require services injected
by the hosting application, which makes local/test wiring explicit.
"""
from __future__ import annotations

import json
import hmac
import os
import re
from datetime import datetime, timezone
from typing import Any

from flask import Flask, Response, jsonify, request

from backend.nexus_api_contract import contract_snapshot, validate_contract
from backend.nexus_event_contract import event_envelope
from backend.nexus_product_backend.market_snapshot import (
    SYMBOLS,
    build_public_market_history_service,
    build_public_market_snapshot_service,
    build_public_market_telemetry_service,
)
from backend.nexus_product_health import compose_health, compose_readiness
from backend.nexus_public_realtime_transport.routes import get_hub
from backend.nexus_product_backend.member_foundation import (
    build_entitlement_snapshot,
    normalize_account_status,
    normalize_member_role,
)


def _services(app: Flask) -> dict[str, Any]:
    return dict(app.config.get("NEXUS_PRODUCT_ALPHA_SERVICES") or {})


def _session_id() -> str | None:
    return request.headers.get("X-Nexus-Session") or request.cookies.get("nexus_session")


def _cookie_session_id() -> str | None:
    return request.cookies.get("nexus_session") if not request.headers.get("X-Nexus-Session") else None


def _verified_session(app: Flask) -> dict[str, Any] | None:
    session_id = _session_id()
    auth = _services(app).get("auth")
    if not session_id or not auth:
        return None
    return auth.resolve_session(session_id)


def _member_identity(app: Flask) -> tuple[dict[str, Any] | None, tuple[Response, int] | None]:
    identity = _verified_session(app)
    if not identity:
        return None, (jsonify({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}), 401)
    return identity, None


def _public_identity(app: Flask, identity: dict[str, Any]) -> dict[str, Any]:
    repo = _services(app).get("repo")
    account_id = identity["account_id"]
    entitlements = repo.active_entitlements(account_id) if repo else []
    role_ids = repo.role_ids(account_id) if repo else []
    snapshot = build_entitlement_snapshot(account_id, entitlements)
    return {
        "user_id": account_id,
        "email": identity["email"],
        "account_status": normalize_account_status(identity.get("status")),
        "role": normalize_member_role(role_ids),
        "plan": snapshot.plan,
        "created_at": identity.get("created_at"),
        "updated_at": None,
    }


def _csrf_error_if_required(app: Flask) -> tuple[Response, int] | None:
    session_id = _cookie_session_id()
    if not session_id or request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    auth = _services(app).get("auth")
    token = request.headers.get("X-Nexus-CSRF")
    if not auth or not auth.verify_csrf(session_id, token):
        return jsonify({"error": "csrf_required", "classification": "AUTH_REQUIRED"}), 403
    return None


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _json_no_store(payload: dict[str, Any], status: int = 200) -> Response:
    response = jsonify(payload)
    response.status_code = status
    return _no_store(response)


def _publish_runtime_health() -> dict[str, Any]:
    health = compose_health()
    contract_payload = {
        "application": health["application"],
        "shadow": health["shadow_readonly"],
    }
    envelope = event_envelope(
        event_id=f"runtime-health-{health['shadow_readonly'].get('campaign_id', 'unknown')}",
        event_type="runtime.health",
        occurred_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        sequence=1,
        payload=contract_payload,
        reconnect_cursor=None,
    )
    # PublicStreamHub only admits allow-listed kinds; map runtime health to a safe kind.
    hub = get_hub()
    hub.publish(
        kind="freshness_change",
        topic="public.product.runtime_health",
        payload={
            "contract_schema": envelope["schema"],
            "event_type": envelope["event_type"],
            "reconnect_cursor": envelope["reconnect_cursor"],
            "dedupe_key": envelope["dedupe_key"],
            "shadow": contract_payload["shadow"],
            "application": contract_payload["application"],
        },
    )
    return envelope


def register_product_alpha_routes(app: Flask) -> None:
    market_snapshot_service = app.config.setdefault(
        "NEXUS_PUBLIC_MARKET_SNAPSHOT_SERVICE",
        build_public_market_snapshot_service(),
    )
    market_history_service = app.config.setdefault(
        "NEXUS_PUBLIC_MARKET_HISTORY_SERVICE",
        build_public_market_history_service(),
    )
    market_telemetry_service = app.config.setdefault(
        "NEXUS_PUBLIC_MARKET_TELEMETRY_SERVICE",
        build_public_market_telemetry_service(),
    )

    def session_response(payload: dict[str, Any], session_id: str, status: int = 200) -> Response:
        csrf_token = str(payload.pop("csrf_token", "") or "")
        if csrf_token:
            payload["csrf_token"] = csrf_token
        response = jsonify(payload)
        response.status_code = status
        response.set_cookie(
            "nexus_session", session_id, secure=True, httponly=True,
            samesite="None", max_age=24 * 60 * 60,
        )
        return _no_store(response)

    @app.get("/api/v1/market/snapshot")
    def market_snapshot():
        """Credential-free public telemetry; no trading or account surfaces."""
        payload, status = market_snapshot_service.snapshot()
        return jsonify(payload), status

    @app.get("/api/v1/market/history")
    def market_history():
        """Bounded public OHLCV; only BTC/ETH/SOL and a fixed interval allowlist."""
        try:
            limit = int(request.args.get("limit", "60"))
        except ValueError:
            limit = 60
        payload, status = market_history_service.history(
            symbol=str(request.args.get("symbol") or "BTCUSDT"),
            interval=str(request.args.get("interval") or "15m"),
            limit=limit,
        )
        return jsonify(payload), status

    @app.get("/api/v1/market/rankings")
    def market_rankings():
        try:
            limit = int(request.args.get("limit", "20"))
        except ValueError:
            limit = 20
        payload, status = market_snapshot_service.rankings(
            metric=str(request.args.get("metric") or "gainers").lower(), limit=limit
        )
        return jsonify(payload), status

    @app.get("/api/v1/market/instruments")
    def market_instruments():
        payload, status = market_telemetry_service.instruments()
        return jsonify(payload), status

    @app.get("/api/v1/market/instruments/<symbol>/derivatives")
    def market_derivatives(symbol: str):
        payload, status = market_telemetry_service.derivatives(symbol)
        return jsonify(payload), status

    @app.get("/api/v1/market/instruments/<symbol>/liquidity")
    def market_liquidity(symbol: str):
        payload, status = market_telemetry_service.liquidity(symbol)
        return jsonify(payload), status

    @app.get("/api/v1/market/instruments/<symbol>/liquidations")
    def market_liquidations(symbol: str):
        payload, status = market_telemetry_service.liquidations(symbol)
        return jsonify(payload), status

    @app.post("/api/v1/member/session/login")
    def member_login():
        if not app.config.get("NEXUS_STAGING_MEMBER_AUTH_ENABLED", False):
            return jsonify({"error": "staging_member_auth_unavailable", "classification": "NOT_IMPLEMENTED"}), 404
        auth = _services(app).get("auth")
        body = request.get_json(silent=True) or {}
        if not auth or not isinstance(body.get("email"), str) or not isinstance(body.get("password"), str):
            return jsonify({"error": "invalid_credentials"}), 401
        try:
            session = auth.login(body["email"].strip().lower(), body["password"], ip=request.remote_addr or "unknown")
            return session_response(
                {"email": session["email"], "csrf_token": session.get("csrf_token"), "staging_only": True},
                session["session_id"],
            )
        except ValueError:
            return jsonify({"error": "invalid_credentials"}), 401

    @app.post("/api/v1/member/registration")
    def member_registration():
        """Staging-only persisted registration. Client input has no authority fields."""
        if not app.config.get("NEXUS_STAGING_REGISTRATION_ENABLED", False):
            return jsonify({"error": "registration_unavailable", "classification": "NOT_IMPLEMENTED"}), 404
        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip().lower()
        display_name = str(body.get("display_name") or "").strip()
        password = body.get("password")
        confirmation = body.get("confirm_password")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or not 1 <= len(display_name) <= 120:
            return jsonify({"error": "invalid_registration"}), 400
        if not isinstance(password, str) or password != confirmation or len(password) < 12:
            return jsonify({"error": "invalid_registration"}), 400
        founder_email = os.getenv("NEXUS_FOUNDER_EMAIL", "").strip().lower()
        founder_code = os.getenv("NEXUS_FOUNDER_REGISTRATION_CODE", "")
        supplied_code = body.get("founder_claim_code")
        is_founder_email = bool(founder_email) and hmac.compare_digest(email, founder_email)
        has_valid_claim = (
            is_founder_email
            and isinstance(supplied_code, str)
            and bool(founder_code)
            and hmac.compare_digest(supplied_code, founder_code)
        )
        if is_founder_email and not has_valid_claim:
            return jsonify({"error": "reserved_identity_unavailable"}), 403
        auth = _services(app).get("auth")
        if not auth:
            return jsonify({"error": "member_store_unavailable"}), 503
        try:
            registered = auth.register_staging_member(
                email=email, password=password, display_name=display_name, founder=has_valid_claim
            )
            # Email-verification enforcement (opt-in, backward compatible). When
            # enabled, a non-founder registration is moved to PENDING_VERIFICATION
            # and a verification email is issued; the account cannot use the
            # member API until it is verified. The Founder identity is exempt so
            # it can never be locked out.
            if app.config.get("NEXUS_EMAIL_VERIFICATION_ENFORCED") and not has_valid_claim:
                repo = _services(app).get("repo")
                if repo is not None and hasattr(repo, "set_account_pending"):
                    from backend.nexus_product_backend.email_routes import (
                        build_member_email_service,
                    )

                    repo.set_account_pending(registered["account_id"])
                    build_member_email_service(app).issue_verification(
                        account_id=registered["account_id"], email=email
                    )
                    return _json_no_store(
                        {
                            "classification": "LIVE_MEMBER_DB",
                            "registered": True,
                            "account_status": "PENDING_VERIFICATION",
                            "verification_required": True,
                            "role": "MEMBER",
                            "plan": "BEGINNER",
                            "tier": "BEGINNER",
                        },
                        201,
                    )
            return session_response(
                {
                    "classification": "LIVE_MEMBER_DB",
                    "registered": True,
                    "role": "FOUNDER" if has_valid_claim else "MEMBER",
                    "plan": "ENTERPRISE" if has_valid_claim else "BEGINNER",
                    "tier": "ENTERPRISE" if has_valid_claim else "BEGINNER",
                    "csrf_token": registered.get("csrf_token"),
                },
                registered["session_id"],
                201,
            )
        except ValueError as exc:
            if str(exc) == "founder_already_initialized":
                return jsonify({"error": "Founder identity has already been initialized"}), 409
            if str(exc) == "email_already_registered":
                return jsonify({"error": "email_already_registered"}), 409
            return jsonify({"error": "invalid_registration"}), 400

    @app.post("/api/v1/member/session/logout")
    def member_logout():
        csrf_error = _csrf_error_if_required(app)
        if csrf_error:
            return csrf_error
        identity, error = _member_identity(app)
        if error:
            return error
        del identity
        auth = _services(app).get("auth")
        if auth:
            auth.logout(_session_id() or "")
        response = jsonify({"ok": True})
        response.delete_cookie("nexus_session", secure=True, httponly=True, samesite="None")
        return _no_store(response)

    @app.get("/api/v1/member/session")
    def member_session():
        identity, error = _member_identity(app)
        if error:
            return error
        repo = _services(app).get("repo")
        profile = repo.profile(identity["account_id"]) if repo else {}
        payload = {"session": _public_identity(app, identity), "profile": profile, "staging_only": True}
        if _cookie_session_id():
            csrf_token = identity.get("_csrf_token")
            if not csrf_token:
                return _json_no_store({"error": "csrf_unavailable", "classification": "AUTH_REQUIRED"}, 401)
            payload["csrf_token"] = csrf_token
        return _json_no_store(payload)

    @app.route("/api/v1/member/profile", methods=["GET", "PATCH"])
    def member_profile():
        identity, error = _member_identity(app)
        if error:
            return error
        csrf_error = _csrf_error_if_required(app)
        if csrf_error:
            return csrf_error
        repo = _services(app).get("repo")
        if not repo:
            return jsonify({"error": "member_store_unavailable"}), 503
        if request.method == "PATCH":
            version = request.headers.get("If-Match")
            try:
                profile = repo.update_profile(identity["account_id"], request.get_json(silent=True) or {}, int(version) if version else None)
            except (ValueError, TypeError) as exc:
                return jsonify({"error": str(exc)}), 409
        else:
            profile = repo.profile(identity["account_id"])
        return jsonify({"classification": "LIVE_MEMBER_DB", "profile": profile})

    @app.route("/api/v1/member/preferences", methods=["GET", "PUT"])
    def member_preferences():
        identity, error = _member_identity(app)
        if error:
            return error
        csrf_error = _csrf_error_if_required(app)
        if csrf_error:
            return csrf_error
        repo = _services(app).get("repo")
        if not repo:
            return jsonify({"error": "member_store_unavailable"}), 503
        data = repo.update_member_preferences(identity["account_id"], request.get_json(silent=True) or {}) if request.method == "PUT" else repo.member_preferences(identity["account_id"])
        return jsonify({"classification": "LIVE_MEMBER_DB", **data})

    @app.route("/api/v1/member/watchlist", methods=["GET", "POST", "DELETE"])
    def member_watchlist():
        identity, error = _member_identity(app)
        if error:
            return error
        csrf_error = _csrf_error_if_required(app)
        if csrf_error:
            return csrf_error
        repo = _services(app).get("repo")
        if not repo:
            return jsonify({"error": "member_store_unavailable"}), 503
        body = request.get_json(silent=True) or {}
        symbol = str(body.get("symbol") or "").upper()
        if request.method != "GET" and symbol not in SYMBOLS:
            return jsonify({"error": "unsupported_symbol"}), 400
        try:
            if request.method == "POST":
                symbols = repo.add_watchlist_symbol(identity["account_id"], symbol)
            elif request.method == "DELETE":
                symbols = repo.remove_watchlist_symbol(identity["account_id"], symbol)
            else:
                symbols = repo.watchlist_symbols(identity["account_id"])
            repo.touch_last_viewed(identity["account_id"])
            return jsonify({"classification": "LIVE_MEMBER_DB", "symbols": symbols})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409

    @app.route("/api/v1/member/notification-preferences", methods=["GET", "PATCH"])
    def member_notification_preferences():
        identity, error = _member_identity(app)
        if error:
            return error
        csrf_error = _csrf_error_if_required(app)
        if csrf_error:
            return csrf_error
        repo = _services(app).get("repo")
        if not repo:
            return jsonify({"error": "member_store_unavailable"}), 503
        data = repo.update_notification_preferences(identity["account_id"], request.get_json(silent=True) or {}) if request.method == "PATCH" else repo.notification_preferences(identity["account_id"])
        return jsonify({"classification": "LIVE_MEMBER_DB", "preferences": data})

    @app.get("/api/v1/member/notifications")
    def member_notifications():
        identity, error = _member_identity(app)
        if error:
            return error
        repo = _services(app).get("repo")
        return jsonify({"classification": "LIVE_MEMBER_DB", "notifications": repo.list_notifications(identity["account_id"]) if repo else []})

    @app.post("/api/v1/member/notifications/<notification_id>/read")
    def member_notification_read(notification_id: str):
        identity, error = _member_identity(app)
        if error:
            return error
        csrf_error = _csrf_error_if_required(app)
        if csrf_error:
            return csrf_error
        repo = _services(app).get("repo")
        if repo:
            repo.mark_notification_read(identity["account_id"], notification_id)
        return jsonify({"ok": True})

    @app.get("/api/v1/member/entitlements")
    def member_entitlements():
        identity, error = _member_identity(app)
        if error:
            return error
        repo = _services(app).get("repo")
        entitlements = repo.active_entitlements(identity["account_id"]) if repo else []
        snapshot = build_entitlement_snapshot(identity["account_id"], entitlements)
        return jsonify({
            "classification": "LIVE_MEMBER_DB", "entitlements": entitlements,
            "plan": snapshot.plan,
            "features": list(snapshot.features),
            "entitlement_source": snapshot.source,
            "billing": "NOT_IMPLEMENTED", "effective_limits": {"watchlist": 30},
        })

    @app.get("/api/v1/product/health")
    def product_health():
        return jsonify(compose_health())

    @app.get("/api/v1/product/readiness")
    def product_readiness():
        payload = compose_readiness()
        return jsonify(payload), 200 if payload["ready"] else 503

    @app.get("/api/v1/product/capabilities")
    def product_capabilities():
        return jsonify(
            {
                "contract": contract_snapshot(),
                "validation": validate_contract(),
            }
        )

    @app.get("/api/v1/product/runtime-status")
    def product_runtime_status():
        return jsonify(
            {
                "classification": "RUNTIME_REQUIRED",
                "runtime_state": "UNAVAILABLE_NOT_BOUND",
                "reason": "nexus_runtime_staging_not_deployed",
                "read_only": True,
            }
        )

    @app.get("/api/v1/product/shadow-watch-snapshot")
    def shadow_watch_snapshot():
        entitlement = _services(app).get("entitlement")
        session_id = _session_id()
        if entitlement:
            if not _verified_session(app):
                return jsonify({"allowed": False, "reason": "invalid_or_expired_session"}), 401
            decision = entitlement.decision_from_session(
                session_id,
                "SHADOW_OUTCOME_SUMMARY",
            )
            if not decision.get("allowed"):
                return jsonify(decision), 403
        return jsonify(
            {
                "classification": "RUNTIME_REQUIRED",
                "read_only": True,
                "runtime_state": "UNAVAILABLE_NOT_BOUND",
                "reason": "nexus_runtime_staging_not_deployed",
            }
        )

    @app.get("/api/v1/product/auth/foundation")
    def auth_foundation():
        return jsonify(
            {
                "status": "AUTH_ALPHA_READY",
                "password_hashing": "argon2",
                "session_revocation": True,
                "tokens_hashed": True,
                "mfa_model": True,
                "customer_onboarding": False,
                "inline_verification_token_allowed_in_production": False,
                "billing": False,
            }
        )

    @app.post("/api/v1/product/entitlement/check")
    def entitlement_check():
        capability_id = str((request.get_json(silent=True) or {}).get("capability_id") or "")
        entitlement = _services(app).get("entitlement")
        session_id = _session_id()
        if not entitlement or not session_id or not capability_id:
            return jsonify({"allowed": False, "reason": "service_or_session_unavailable"}), 401
        if not _verified_session(app):
            return jsonify({"allowed": False, "reason": "invalid_or_expired_session"}), 401
        csrf_error = _csrf_error_if_required(app)
        if csrf_error:
            return csrf_error
        decision = entitlement.decision_from_session(session_id, capability_id)
        return jsonify(decision), 200 if decision.get("allowed") else 403

    @app.get("/api/v1/product/organization/permissions")
    def organization_permissions():
        rbac = _services(app).get("rbac")
        session_id = _session_id()
        if not rbac or not session_id:
            return jsonify({"allowed": False, "reason": "service_or_session_unavailable"}), 401
        if not _verified_session(app):
            return jsonify({"allowed": False, "reason": "invalid_or_expired_session"}), 401
        return jsonify(rbac.permissions_for_session(session_id, org_id=request.args.get("org_id")))

    def founder_surface(permission: str, surface: str):
        rbac = _services(app).get("rbac")
        session_id = _session_id()
        if not rbac or not session_id or not _verified_session(app):
            return jsonify({"allowed": False, "reason": "invalid_or_expired_session"}), 401
        try:
            rbac.require_founder_admin(session_id)
            rbac.require_permission(session_id, permission)
        except PermissionError:
            return jsonify({"allowed": False, "reason": "founder_permission_required"}), 403
        return jsonify({
            "allowed": True, "classification": "RUNTIME_REQUIRED", "surface": surface,
            "runtime_state": "UNAVAILABLE_NOT_BOUND", "read_only": True,
        })

    @app.get("/api/v1/founder/operator")
    def founder_operator():
        return founder_surface("founder.operator.read", "operator")

    @app.get("/api/v1/founder/diagnostics")
    def founder_diagnostics():
        return founder_surface("founder.diagnostics.read", "diagnostics")

    @app.get("/api/v1/founder/live-ops")
    def founder_live_ops():
        return founder_surface("founder.live_ops.read", "live_ops")

    @app.post("/api/v1/product/audit/protected-operation")
    def protected_audit_operation():
        services = _services(app)
        rbac = services.get("rbac")
        audit = services.get("audit")
        session_id = _session_id()
        if not rbac or not audit or not session_id:
            return jsonify({"allowed": False, "reason": "service_or_session_unavailable"}), 401
        if not _verified_session(app):
            return jsonify({"allowed": False, "reason": "invalid_or_expired_session"}), 401
        csrf_error = _csrf_error_if_required(app)
        if csrf_error:
            return csrf_error
        try:
            rbac.require_permission(session_id, "org.view_audit", org_id=request.args.get("org_id"))
        except PermissionError as exc:
            return jsonify({"allowed": False, "reason": str(exc)}), 403
        auth = services.get("auth")
        identity = auth.resolve_session(session_id) if auth else None
        return jsonify(
            audit.record(
                actor_account_id=(identity or {}).get("account_id"),
                action="product.protected_operation",
                resource_type="product_alpha",
            )
        )

    @app.get("/api/v1/product/market-overview")
    def market_overview():
        return jsonify(
            {
                "schema": "v18_3_4_market_overview_read_model_v1",
                "data_class": "READ_ONLY",
                "execution_controls": False,
                "credentials_exposed": False,
            }
        )

    @app.get("/api/v1/product/events/runtime-health")
    def runtime_health_event():
        envelope = _publish_runtime_health()
        return Response(json.dumps(envelope), mimetype="application/json")
