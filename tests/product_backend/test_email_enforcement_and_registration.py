from __future__ import annotations

from typing import Any, Optional

import pytest
from flask import Flask

from api_staging_app import email_enforcement_enabled
from backend.nexus_product_backend.auth_alpha import AuthAlphaService
from backend.nexus_product_backend.member_foundation import account_can_use_member_api
from backend.nexus_product_backend.routes import register_product_alpha_routes


def test_pending_and_disabled_accounts_cannot_use_member_api() -> None:
    # Regression: only ACTIVE accounts may use the member API. Pending and
    # disabled accounts are denied (this gates login / session usability).
    assert account_can_use_member_api("active") is True
    assert account_can_use_member_api("ACTIVE") is True
    assert account_can_use_member_api("pending_verification") is False
    assert account_can_use_member_api("PENDING_VERIFICATION") is False
    assert account_can_use_member_api("disabled") is False
    assert account_can_use_member_api(None) is False


# --------------------------------------------------------------------------
# FIX 1 — enforcement env wiring (staging-gated, fail closed)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "env,expected",
    [
        ({"NEXUS_EMAIL_VERIFICATION_ENFORCED": "true", "NEXUS_ENV": "staging"}, True),
        ({"NEXUS_EMAIL_VERIFICATION_ENFORCED": "true", "NEXUS_DEPLOYMENT_ENV": "staging"}, True),
        ({"NEXUS_EMAIL_VERIFICATION_ENFORCED": "false", "NEXUS_ENV": "staging"}, False),
        ({"NEXUS_ENV": "staging"}, False),  # missing flag
        ({"NEXUS_EMAIL_VERIFICATION_ENFORCED": "true"}, False),  # missing env
        ({"NEXUS_EMAIL_VERIFICATION_ENFORCED": "true", "NEXUS_ENV": "production"}, False),
        ({}, False),
    ],
)
def test_email_enforcement_env_wiring(env, expected) -> None:
    assert email_enforcement_enabled(env) is expected


# --------------------------------------------------------------------------
# FIX 4 — pending registration must not leave a usable session
# --------------------------------------------------------------------------

class _RegistrationRepo:
    """In-memory repo double covering the registration + token contract."""

    def __init__(self) -> None:
        self.accounts: dict[str, dict[str, Any]] = {}
        self.email_index: dict[str, str] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.tokens: list[dict[str, Any]] = []
        self._n = 0

    def _next(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_{self._n}"

    def register_staging_account(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        founder: bool,
        csrf_token_hash: str | None = None,
        csrf_token: str | None = None,
    ) -> tuple[str, str]:
        if email in self.email_index:
            raise ValueError("email_already_registered")
        account_id = self._next("acct")
        session_id = self._next("sess")
        self.accounts[account_id] = {"account_id": account_id, "email": email, "status": "active"}
        self.email_index[email] = account_id
        self.sessions[session_id] = {"account_id": account_id, "revoked": False}
        return account_id, session_id

    def set_account_pending(self, account_id: str) -> None:
        self.accounts[account_id]["status"] = "pending_verification"

    def revoke_session(self, session_id: str) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["revoked"] = True

    def get_active_session(self, session_id: str) -> Optional[dict[str, Any]]:
        s = self.sessions.get(session_id)
        if not s or s["revoked"]:
            return None
        if self.accounts[s["account_id"]]["status"] != "active":
            return None
        return {"session_id": session_id, "account_id": s["account_id"]}

    # token contract used by MemberEmailService via build_member_email_service
    def issue_one_time_token(self, account_id: str, purpose: str, *, ttl_minutes: int) -> str:
        raw = self._next("raw")
        self.tokens.append({"account_id": account_id, "purpose": purpose, "raw": raw})
        return raw

    def supersede_unconsumed_tokens(self, account_id: str, purpose: str) -> int:
        return 0

    def seconds_since_last_token(self, account_id: str, purpose: str) -> Optional[float]:
        return None


def _enforced_app(repo: _RegistrationRepo) -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["NEXUS_STAGING_REGISTRATION_ENABLED"] = True
    app.config["NEXUS_STAGING_MEMBER_AUTH_ENABLED"] = True
    app.config["NEXUS_EMAIL_VERIFICATION_ENFORCED"] = True
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"repo": repo, "auth": AuthAlphaService(repo)}
    register_product_alpha_routes(app)
    return app


def test_enforced_registration_is_pending_with_no_usable_session_and_issues_token() -> None:
    repo = _RegistrationRepo()
    app = _enforced_app(repo)
    client = app.test_client()
    resp = client.post(
        "/api/v1/member/registration",
        json={
            "email": "newuser@example.com",
            "display_name": "New User",
            "password": "supersecret12",
            "confirm_password": "supersecret12",
        },
    )
    body = resp.get_json()
    assert resp.status_code == 201
    assert body["account_status"] == "PENDING_VERIFICATION"
    assert body["verification_required"] is True
    # The registration-created session must have been revoked (not usable).
    account_id = repo.email_index["newuser@example.com"]
    assert repo.accounts[account_id]["status"] == "pending_verification"
    assert all(s["revoked"] for s in repo.sessions.values())
    for sid in repo.sessions:
        assert repo.get_active_session(sid) is None
    # A verification token was issued.
    assert any(t["purpose"] == "email_verify" for t in repo.tokens)
    # No raw session token / csrf is leaked in the pending response.
    assert "csrf_token" not in body
    assert "session_id" not in body
