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

    # Password credential model is absent in PublicAccount — signup/login are stub-grade.
    has_password = False
    try:
        from backend.nexus_public_auth import store as st

        src = open(st.__file__, encoding="utf-8").read()
        has_password = "password" in src.lower()
    except Exception:
        has_password = False

    email_verify = False
    forgot_reset = False
    try:
        from backend.nexus_public_auth import routes as rt

        text = open(rt.__file__, encoding="utf-8").read()
        email_verify = (
            "/email/verify" in text
            or "verify_email" in text
            or "email_verification" in text.lower()
        )
        forgot_reset = "forgot" in text.lower() or "reset_password" in text.lower()
        routes_mounted_hint = "register_public_auth_routes" in text
    except Exception:
        pass

    mfa = "PARTIAL"
    deletion = "PARTIAL"
    session = "PARTIAL"
    entitlement = "READY"
    try:
        from backend.nexus_public_auth.mfa import MfaService  # noqa: F401

        mfa = "PARTIAL"  # abstraction ready, no live TOTP/SMS vendor
    except Exception:
        mfa = "MISSING"
    try:
        from backend.nexus_public_auth.account_lifecycle import AccountLifecycleService  # noqa: F401

        deletion = "READY"
    except Exception:
        deletion = "MISSING"
    try:
        from backend.nexus_public_auth.sessions import SessionService  # noqa: F401

        session = "PARTIAL"  # JWT sessions exist; password login missing
    except Exception:
        session = "MISSING"
    try:
        from backend.nexus_public_entitlements_v18_2.authority import (  # noqa: F401
            PUBLIC_ENTITLEMENT_AUTHORITY,
        )

        entitlement = "READY"
    except Exception:
        entitlement = "MISSING"

    census = {
        "signup": "PARTIAL" if auth_pkg and not has_password else ("MISSING" if not auth_pkg else "PARTIAL"),
        "login": "PARTIAL" if auth_pkg and not has_password else "MISSING",
        "session": session,
        "email_verify": "MISSING" if not email_verify else "PARTIAL",
        "forgot_password": "MISSING" if not forgot_reset else "PARTIAL",
        "reset_password": "MISSING" if not forgot_reset else "PARTIAL",
        "mfa": mfa,
        "deletion": deletion,
        "entitlement": entitlement,
        "auth_package_present": auth_pkg,
        "password_credential_model": has_password,
        "routes_factory_present": routes_mounted_hint,
        "production_billing": False,
        "notes": [
            "Public auth realm exists (LOCAL_OR_STAGING_ONLY) without password credentials.",
            "Register + session-by-account_id exist; commercial email/password login is not READY.",
            "Entitlement authority is server-side and can later bind billing→subscription→capability.",
        ],
    }

    blockers = [
        k
        for k, v in census.items()
        if k
        in {
            "signup",
            "login",
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
    # PARTIAL session/mfa/signup/login are commercial blockers for paid beta identity.
    paid_beta_auth_blockers = [
        {"capability": k, "status": census[k]}
        for k in blockers
        if census[k] == "MISSING"
        or k in {"signup", "login", "email_verify", "forgot_password", "reset_password"}
    ]
    return {
        "census": census,
        "paid_beta_auth_blockers": paid_beta_auth_blockers,
        "AUTH_REQUIRED_BLOCKER": "AUTH_REQUIRED_BLOCKER",
    }
