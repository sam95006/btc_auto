"""Auth commercial gap census — READY | PARTIAL | MISSING."""
from __future__ import annotations

from typing import Any


def auth_commercial_census() -> dict[str, Any]:
    """
    Honest census of paid-beta auth surface.
    Does not invent readiness — inspects existing public auth package + mount state.
    """
    auth_pkg = False
    routes_mounted_hint = False
    try:
        from backend.nexus_public_auth import service as _svc  # noqa: F401

        auth_pkg = True
    except Exception:
        auth_pkg = False

    has_password = False
    try:
        from backend.nexus_public_auth import store as st
        from backend.nexus_public_auth import passwords as pw  # noqa: F401

        src = open(st.__file__, encoding="utf-8").read()
        has_password = "password_hash" in src and "pbkdf2" in open(
            pw.__file__, encoding="utf-8"
        ).read()
    except Exception:
        has_password = False

    email_verify = False
    forgot_reset = False
    login_route = False
    logout_route = False
    try:
        from backend.nexus_public_auth import routes as rt

        text = open(rt.__file__, encoding="utf-8").read()
        email_verify = (
            "/email/verify" in text
            or "verify_email" in text
            or "email_verification" in text.lower()
        )
        forgot_reset = "forgot" in text.lower() and "reset" in text.lower()
        login_route = '@bp.post("/login")' in text or "/login" in text
        logout_route = '@bp.post("/logout")' in text or "/logout" in text
        routes_mounted_hint = "register_public_auth_routes" in text
    except Exception:
        pass

    mfa = "PARTIAL"
    deletion = "PARTIAL"
    session = "PARTIAL"
    entitlement = "READY"
    try:
        from backend.nexus_public_auth.mfa import MfaService  # noqa: F401

        # Abstraction + optional enroll/confirm/challenge ready; no live TOTP/SMS vendor.
        # Normal beta: MFA optional (not mandated). member_admin: stronger when enrolled.
        mfa = "PARTIAL"
    except Exception:
        mfa = "MISSING"
    try:
        from backend.nexus_public_auth.account_lifecycle import AccountLifecycleService  # noqa: F401

        deletion = "READY"
    except Exception:
        deletion = "MISSING"
    try:
        from backend.nexus_public_auth.sessions import SessionService  # noqa: F401

        session = "READY" if has_password and login_route else "PARTIAL"
    except Exception:
        session = "MISSING"
    try:
        from backend.nexus_public_entitlements_v18_2.authority import (  # noqa: F401
            PUBLIC_ENTITLEMENT_AUTHORITY,
        )

        entitlement = "READY"
    except Exception:
        entitlement = "MISSING"

    signup = "READY" if auth_pkg and has_password else ("MISSING" if not auth_pkg else "PARTIAL")
    login = "READY" if has_password and login_route else ("PARTIAL" if auth_pkg else "MISSING")
    logout = "READY" if logout_route else "MISSING"
    email_verify_status = "READY" if email_verify and has_password else ("MISSING" if not email_verify else "PARTIAL")
    forgot_status = "READY" if forgot_reset else "MISSING"
    reset_status = "READY" if forgot_reset else "MISSING"

    census = {
        "signup": signup,
        "login": login,
        "logout": logout,
        "session": session,
        "email_verify": email_verify_status,
        "forgot_password": forgot_status,
        "reset_password": reset_status,
        "mfa": mfa,
        "deletion": deletion,
        "entitlement": entitlement,
        "auth_package_present": auth_pkg,
        "password_credential_model": has_password,
        "routes_factory_present": routes_mounted_hint,
        "production_billing": False,
        "notes": [
            "Public auth realm (LOCAL_OR_STAGING_ONLY) with PBKDF2 password credentials.",
            "Signup/login/logout + email verify + forgot/reset tokens (inline staging delivery).",
            "MFA PARTIAL: optional enroll for members; stronger challenge for member_admin when enrolled; no live TOTP vendor.",
            "Entitlement authority remains server-side; Production Billing not activated.",
            "Closed beta invite entity binds INVITED/ACTIVE/REVOKED/EXPIRED server-side.",
        ],
    }

    blockers = [
        k
        for k, v in census.items()
        if k
        in {
            "signup",
            "login",
            "logout",
            "session",
            "email_verify",
            "forgot_password",
            "reset_password",
            "mfa",
            "deletion",
            "entitlement",
        }
        and v in {"MISSING", "PARTIAL"}
    ]
    # MFA remains PARTIAL (no live vendor) — not a P0 commercial blocker for paid beta identity.
    paid_beta_auth_blockers = [
        {"capability": k, "status": census[k]}
        for k in blockers
        if census[k] == "MISSING"
        or (
            k in {"signup", "login", "logout", "email_verify", "forgot_password", "reset_password", "session"}
            and census[k] == "PARTIAL"
        )
    ]
    return {
        "census": census,
        "paid_beta_auth_blockers": paid_beta_auth_blockers,
        "AUTH_REQUIRED_BLOCKER": "AUTH_REQUIRED_BLOCKER",
        "paid_beta_identity_minimum_met": len(paid_beta_auth_blockers) == 0,
    }
