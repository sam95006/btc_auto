"""Optional Flask blueprint for non-production public auth endpoints."""
from __future__ import annotations

from typing import Any, Optional

from backend.nexus_public_auth.hard_bans import HardBanViolation, assert_env_hard_bans
from backend.nexus_public_auth.rate_limit import RateLimitExceeded
from backend.nexus_public_auth.service import (
    PublicAuthMembershipService,
    get_default_public_auth_service,
)


def create_public_auth_blueprint(service: Optional[PublicAuthMembershipService] = None):
    """
    Lazy Flask blueprint factory.

    Mount only in LOCAL_OR_STAGING_ONLY contexts. Never enables live billing.
    Never grants private execution via entitlements.
    PUB2-H: bearer ACL on consent/export/delete/audit/revoke.
    """
    assert_env_hard_bans()
    try:
        from flask import Blueprint, jsonify, request
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Flask is required to mount public auth routes") from exc

    svc = service or get_default_public_auth_service()
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

    def _bearer_account() -> dict[str, Any]:
        token = str(
            request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            or (request.get_json(silent=True) or {}).get("token", "")
        )
        if not token:
            raise HardBanViolation("HARD BAN: bearer token required")
        return svc.authenticate_rate_limited(token)

    @bp.get("/foundation")
    def foundation():
        return jsonify({"ok": True, "foundation": svc.foundation_status()})

    @bp.post("/register")
    def register():
        body = request.get_json(silent=True) or {}
        try:
            password = str(body.get("password", "") or "")
            if not password:
                raise HardBanViolation("password required for paid-beta signup")
            # Ignore client-supplied tier/roles — self-register is Free/member only.
            result = svc.register_member(
                email=str(body.get("email", "")),
                display_name=str(body.get("display_name", "")),
                tier="Free",
                member_roles=["member"],
                password=password,
            )
            return jsonify({"ok": True, "account": result})
        except HardBanViolation as exc:
            return _err(exc, 403)
        except Exception as exc:
            return _err(exc)

    @bp.post("/signup")
    def signup():
        """Paid-beta signup alias — requires password."""
        return register()

    @bp.post("/login")
    def login():
        body = request.get_json(silent=True) or {}
        try:
            result = svc.login_with_password(
                email=str(body.get("email", "")),
                password=str(body.get("password", "")),
                mfa_challenge_id=str(body["mfa_challenge_id"])
                if body.get("mfa_challenge_id")
                else None,
                mfa_response_code=str(body["mfa_response_code"])
                if body.get("mfa_response_code")
                else None,
            )
            if result.get("mfa_required") and not result.get("session"):
                return jsonify({"ok": False, **result}), 401
            return jsonify({"ok": True, **result})
        except HardBanViolation as exc:
            return _err(exc, 401)
        except RateLimitExceeded as exc:
            return _err(exc, 429)

    @bp.post("/logout")
    def logout():
        try:
            token = str(
                request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                or (request.get_json(silent=True) or {}).get("token", "")
            )
            result = svc.logout(token)
            return jsonify(result)
        except HardBanViolation as exc:
            return _err(exc, 401)

    @bp.post("/email/verify")
    def email_verify():
        body = request.get_json(silent=True) or {}
        try:
            result = svc.verify_email(str(body.get("token") or body.get("verification_token") or ""))
            return jsonify({"ok": True, **result})
        except HardBanViolation as exc:
            return _err(exc, 400)

    @bp.post("/email/resend")
    def email_resend():
        try:
            auth = _bearer_account()
            result = svc.request_email_verification(auth["account_id"])
            return jsonify({"ok": True, **result})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/password/forgot")
    def password_forgot():
        body = request.get_json(silent=True) or {}
        try:
            result = svc.forgot_password(str(body.get("email", "")))
            return jsonify(result)
        except HardBanViolation as exc:
            return _err(exc, 429 if isinstance(exc, RateLimitExceeded) else 400)

    @bp.post("/password/reset")
    def password_reset():
        body = request.get_json(silent=True) or {}
        try:
            result = svc.reset_password(
                str(body.get("token") or body.get("reset_token") or ""),
                str(body.get("password") or body.get("new_password") or ""),
            )
            return jsonify({"ok": True, **result})
        except HardBanViolation as exc:
            return _err(exc, 400)

    @bp.post("/session")
    def create_session():
        body = request.get_json(silent=True) or {}
        try:
            # Prefer password login; legacy account_id session remains for admin/test tooling.
            if body.get("email") and body.get("password"):
                result = svc.login_with_password(
                    email=str(body.get("email", "")),
                    password=str(body.get("password", "")),
                )
                return jsonify({"ok": True, "session": result["session"], "account": result["account"]})
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
            auth = _bearer_account()
            session = svc.store.get_session(str(body.get("session_id", "")))
            if session is None:
                raise HardBanViolation("session not found")
            if session.account_id != auth["account_id"] and "member_admin" not in set(
                auth.get("member_roles") or []
            ):
                raise HardBanViolation("HARD BAN: cross-account session revoke denied")
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
            account = svc.store.get_account(auth["account_id"])
            beta_access = None
            try:
                from backend.nexus_closed_beta.service import get_closed_beta_service

                beta_access = get_closed_beta_service().member_access_snapshot(auth["account_id"])
            except Exception:
                beta_access = None
            return jsonify(
                {
                    "ok": True,
                    "auth": auth,
                    "account": {
                        "account_id": account.account_id if account else auth["account_id"],
                        "email": account.email if account else None,
                        "email_verified": bool(account.email_verified) if account else False,
                        "display_name": account.display_name if account else None,
                        "tier": account.tier if account else None,
                        "member_roles": list(account.member_roles) if account else [],
                        "status": account.status if account else None,
                    },
                    "entitlements": svc.entitlements(auth["account_id"]),
                    "mfa": svc.mfa.mfa_status(auth["account_id"]),
                    "beta_access": beta_access,
                    "production_billing": False,
                    "session": {
                        "session_id": auth.get("session_id"),
                        "expires_at": auth.get("expires_at"),
                    },
                }
            )
        except HardBanViolation as exc:
            return _err(exc, 401)

    @bp.post("/consent")
    def consent():
        body = request.get_json(silent=True) or {}
        try:
            auth = _bearer_account()
            target = str(body.get("account_id", "") or auth["account_id"])
            if target != auth["account_id"]:
                raise HardBanViolation("HARD BAN: cross-account consent mutation denied")
            svc.rate_limiter.check("consent", target)
            result = svc.consent.set_consent(
                target,
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
            auth = _bearer_account()
            target = str(body.get("account_id", "") or auth["account_id"])
            svc.rate_limiter.check("export", target)
            payload = svc.lifecycle.export_account_data(
                target, actor_account_id=auth["account_id"]
            )
            return jsonify({"ok": True, "export": payload})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/delete")
    def delete_account():
        body = request.get_json(silent=True) or {}
        try:
            auth = _bearer_account()
            target = str(body.get("account_id", "") or auth["account_id"])
            svc.rate_limiter.check("delete", target)
            pending = svc.lifecycle.request_deletion(
                target, actor_account_id=auth["account_id"]
            )
            if bool(body.get("finalize")):
                final = svc.lifecycle.finalize_deletion(
                    target, actor_account_id=auth["account_id"]
                )
                return jsonify({"ok": True, "pending": pending, "final": final})
            return jsonify({"ok": True, "pending": pending})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.get("/audit/<account_id>")
    def audit(account_id: str):
        try:
            auth = _bearer_account()
            if account_id != auth["account_id"] and "member_admin" not in set(
                auth.get("member_roles") or []
            ):
                raise HardBanViolation("HARD BAN: cross-account audit enumeration denied")
            return jsonify({"ok": True, "events": svc.store.list_audit(account_id=account_id)})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.get("/mfa/<account_id>")
    def mfa_status(account_id: str):
        try:
            auth = _bearer_account()
            if account_id != auth["account_id"] and "member_admin" not in set(
                auth.get("member_roles") or []
            ):
                raise HardBanViolation("HARD BAN: cross-account MFA status denied")
            return jsonify({"ok": True, "mfa": svc.mfa.mfa_status(account_id)})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/mfa/enroll")
    def mfa_enroll():
        body = request.get_json(silent=True) or {}
        try:
            auth = _bearer_account()
            account_id = str(body.get("account_id", "") or auth["account_id"])
            if account_id != auth["account_id"]:
                raise HardBanViolation("HARD BAN: cross-account MFA enroll denied")
            svc.rate_limiter.check("mfa_challenge", account_id)
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
            auth = _bearer_account()
            account_id = str(body.get("account_id", "") or auth["account_id"])
            if account_id != auth["account_id"]:
                raise HardBanViolation("HARD BAN: cross-account MFA confirm denied")
            result = svc.mfa.confirm_enrollment(
                account_id,
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
            auth = _bearer_account()
            account_id = str(body.get("account_id", "") or auth["account_id"])
            if account_id != auth["account_id"]:
                raise HardBanViolation("HARD BAN: cross-account MFA challenge denied")
            svc.rate_limiter.check("mfa_challenge", account_id)
            result = svc.mfa.create_challenge(account_id, str(body.get("factor_id", "")))
            return jsonify({"ok": True, "challenge": result})
        except HardBanViolation as exc:
            return _err(exc, 403)

    @bp.post("/mfa/verify")
    def mfa_verify():
        body = request.get_json(silent=True) or {}
        try:
            auth = _bearer_account()
            account_id = str(body.get("account_id", "") or auth["account_id"])
            if account_id != auth["account_id"]:
                raise HardBanViolation("HARD BAN: cross-account MFA verify denied")
            svc.rate_limiter.check("mfa_challenge", account_id)
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
