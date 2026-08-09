"""Auth gate — never invent identity; return AUTH_REQUIRED_BLOCKER."""
from __future__ import annotations

from typing import Any, Optional

from backend.nexus_paid_beta_retention.constants import AUTH_REQUIRED_BLOCKER


def auth_required_body(*, reason: str = "identity_or_session_required") -> dict[str, Any]:
    return {
        "ok": False,
        "error": AUTH_REQUIRED_BLOCKER,
        "blocker": AUTH_REQUIRED_BLOCKER,
        "reason": reason,
        "fake_identity": False,
        "production_billing": False,
        "member_execution": 0,
    }


def extract_bearer_token(headers: dict[str, str], body: Optional[dict[str, Any]] = None) -> str:
    auth = str(headers.get("Authorization") or headers.get("authorization") or "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if body and body.get("token"):
        return str(body.get("token") or "").strip()
    return ""


def resolve_account_id(token: str) -> Optional[str]:
    """Authenticate against public auth realm when available. No guest fabrication."""
    if not token:
        return None
    try:
        from backend.nexus_public_auth.service import PublicAuthMembershipService

        svc = PublicAuthMembershipService()
        auth = svc.authenticate_rate_limited(token)
        account_id = str(auth.get("account_id") or "").strip()
        return account_id or None
    except Exception:
        return None
