"""Optional Flask blueprint for non-production public auth endpoints."""
from __future__ import annotations

from typing import Any, Optional

from backend.nexus_public_auth.hard_bans import HardBanViolation, assert_env_hard_bans
from backend.nexus_public_auth.rate_limit import RateLimitExceeded
from backend.nexus_public_auth.service import PublicAuthMembershipService


def create_public_auth_blueprint(service: Optional[PublicAuthMembershipService] = None):
    """
    Lazy Flask blueprint factory.

    Mount only in LOCAL_OR_STAGING_ONLY contexts. Never enables live billing.
    Never grants private execution via entitlements.
    """
    assert_env_hard_bans()
    try:
        from flask import Blueprint, jsonify, request
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Flask is required to mount public auth routes") from exc

    svc = service or PublicAuthMembershipService()
    bp = Blueprint("nexus_public_auth", __name__, url_prefix="/api/public/auth")

    def _err(exc: Exception, code: int = 400):
        status = 429 if isinstance(exc, RateLimitExceeded) else code
        return (
            jsonify(
                {
                    "ok": False,
                    "error": str(exc),
                    "hard_ban": isinstance(exc, HardBanViolation),
                    "rate_limited": isinstance(exc, RateLimitExceeded),
                }
            ),
            status,
        )

    @bp.get("/foundation")
    def foundation():
        return jsonify({"ok": True, "foundation": svc.foundation_status()})

    @bp.post("/register")
    def register():
        body = request.get_json(silent=True) or {}
        try:
            result = svc.register_member(
                email=str(body.get("email", "")),
                display_name=str(body.get("display_name", "")),
                tier=str(body.get("tier", "Free")),
            )
            return jsonify({"ok": True, "account": result})
        except HardBanViolation as exc:
            return _err(exc, 403)
        except Exception as exc:
            return _err(exc)

    @bp.post("/session")
    def create_session():
        body = request.get_json(silent=True) or {}
        try:
            account_id = str(body.get("account_id", ""))
            account = svc.store.get_account(account_id)
            if account is None:
                raise HardBanViolation("account not found")
            session = svc.create_session_rate_limited(
                account_id,
                tier=account.tier,
                member_roles=list(account.member_roles),
                mfa_challenge_id=str(body["mfa_challenge_id"])
                if body.get("mfa_challenge_id")
                else None,
            )
            return jsonify({"ok": True, "session": session})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/session/revoke")
    def revoke_session():
        body = request.get_json(silent=True) or {}
        try:
            result = svc.sessions.revoke_session(
                str(body.get("session_id", "")),
                reason=str(body.get("reason", "user_revoke")),
            )
            return jsonify({"ok": True, "result": result})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/me")
    def me():
        body = request.get_json(silent=True) or {}
        token = str(
            body.get("token")
            or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        )
        try:
            auth = svc.authenticate_rate_limited(token)
            return jsonify(
                {
                    "ok": True,
                    "auth": auth,
                    "entitlements": svc.entitlements(auth["account_id"]),
                    "mfa": svc.mfa.mfa_status(auth["account_id"]),
                }
            )
        except HardBanViolation as exc:
            return _err(exc, 401)

    @bp.post("/consent")
    def consent():
        body = request.get_json(silent=True) or {}
        try:
            account_id = str(body.get("account_id", ""))
            svc.rate_limiter.check("consent", account_id or "anonymous")
            result = svc.consent.set_consent(
                account_id,
                str(body.get("purpose", "")),
                granted=bool(body.get("granted")),
                version=str(body.get("version", "v1")),
            )
            return jsonify({"ok": True, "consent": result})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/export")
    def export_data():
        body = request.get_json(silent=True) or {}
        try:
            account_id = str(body.get("account_id", ""))
            svc.rate_limiter.check("export", account_id or "anonymous")
            payload = svc.lifecycle.export_account_data(account_id)
            return jsonify({"ok": True, "export": payload})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/delete")
    def delete_account():
        body = request.get_json(silent=True) or {}
        try:
            account_id = str(body.get("account_id", ""))
            svc.rate_limiter.check("delete", account_id or "anonymous")
            pending = svc.lifecycle.request_deletion(account_id)
            if bool(body.get("finalize")):
                final = svc.lifecycle.finalize_deletion(account_id)
                return jsonify({"ok": True, "pending": pending, "final": final})
            return jsonify({"ok": True, "pending": pending})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.get("/audit/<account_id>")
    def audit(account_id: str):
        return jsonify({"ok": True, "events": svc.store.list_audit(account_id=account_id)})

    @bp.get("/mfa/<account_id>")
    def mfa_status(account_id: str):
        try:
            return jsonify({"ok": True, "mfa": svc.mfa.mfa_status(account_id)})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/mfa/enroll")
    def mfa_enroll():
        body = request.get_json(silent=True) or {}
        try:
            account_id = str(body.get("account_id", ""))
            svc.rate_limiter.check("mfa_challenge", account_id or "anonymous")
            result = svc.mfa.enroll_factor(
                account_id,
                str(body.get("factor_type", "totp")),
                label=str(body.get("label", "")),
            )
            return jsonify({"ok": True, "enrollment": result})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/mfa/confirm")
    def mfa_confirm():
        body = request.get_json(silent=True) or {}
        try:
            result = svc.mfa.confirm_enrollment(
                str(body.get("account_id", "")),
                str(body.get("factor_id", "")),
                enrollment_secret=str(body.get("enrollment_secret", "")),
            )
            return jsonify({"ok": True, "factor": result})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/mfa/challenge")
    def mfa_challenge():
        body = request.get_json(silent=True) or {}
        try:
            account_id = str(body.get("account_id", ""))
            svc.rate_limiter.check("mfa_challenge", account_id or "anonymous")
            result = svc.mfa.create_challenge(account_id, str(body.get("factor_id", "")))
            return jsonify({"ok": True, "challenge": result})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/mfa/verify")
    def mfa_verify():
        body = request.get_json(silent=True) or {}
        try:
            account_id = str(body.get("account_id", ""))
            svc.rate_limiter.check("mfa_challenge", account_id or "anonymous")
            result = svc.mfa.verify_challenge(
                account_id,
                str(body.get("challenge_id", "")),
                response_code=str(body.get("response_code", "")),
            )
            return jsonify({"ok": True, "result": result})
        except HardBanViolation as exc:
            return _err(exc, 403)

    return bp


def register_public_auth_routes(app: Any, service: Optional[PublicAuthMembershipService] = None) -> None:
    assert_env_hard_bans()
    app.register_blueprint(create_public_auth_blueprint(service))
