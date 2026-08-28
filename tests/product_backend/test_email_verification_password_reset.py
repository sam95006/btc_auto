from __future__ import annotations

import hashlib
import secrets
from typing import Any, Optional

import pytest
from flask import Flask

from backend.nexus_product_backend.email_auth import (
    MemberEmailService,
    PURPOSE_EMAIL_VERIFY,
    PURPOSE_PASSWORD_RESET,
)
from backend.nexus_product_backend.email_provider import (
    NullEmailProvider,
    build_email_provider,
    mask_email,
)
from backend.nexus_product_backend.email_routes import register_member_email_routes


class FakeRepo:
    """In-memory double for the token/account contract used by email flows."""

    def __init__(self) -> None:
        self.accounts: dict[str, dict[str, Any]] = {}
        self.email_index: dict[str, str] = {}
        self.tokens: dict[str, dict[str, Any]] = {}  # raw -> record
        self.sessions: dict[str, dict[str, Any]] = {}
        self.password_hashes: dict[str, str] = {}
        self.verified: dict[str, bool] = {}
        self.now: float = 1000.0
        self._counter = 0

    # -- helpers to set up fixtures --
    def add_account(self, email: str, *, status: str = "pending_verification") -> str:
        self._counter += 1
        account_id = f"acct_{self._counter}"
        self.accounts[account_id] = {"account_id": account_id, "email": email, "status": status}
        self.email_index[email] = account_id
        self.password_hashes[account_id] = "OLD_HASH"
        self.verified[account_id] = False
        return account_id

    def add_session(self, account_id: str) -> str:
        self._counter += 1
        sid = f"sess_{self._counter}"
        self.sessions[sid] = {"account_id": account_id, "revoked": False}
        return sid

    # -- contract used by MemberEmailService --
    def get_account_by_email(self, email: str) -> Optional[dict[str, Any]]:
        aid = self.email_index.get(email)
        return dict(self.accounts[aid]) if aid else None

    def issue_one_time_token(self, account_id: str, purpose: str, *, ttl_minutes: int) -> str:
        raw = secrets.token_urlsafe(32)
        self.tokens[raw] = {
            "account_id": account_id,
            "purpose": purpose,
            "expires_at": self.now + ttl_minutes * 60,
            "consumed": False,
            "created_at": self.now,
        }
        return raw

    def consume_one_time_token(self, raw: str, purpose: str) -> Optional[str]:
        rec = self.tokens.get(raw)
        if not rec:
            return None
        if rec["purpose"] != purpose:
            return None
        if rec["consumed"] or rec["expires_at"] < self.now:
            return None
        rec["consumed"] = True
        return rec["account_id"]

    def supersede_unconsumed_tokens(self, account_id: str, purpose: str) -> int:
        n = 0
        for rec in self.tokens.values():
            if rec["account_id"] == account_id and rec["purpose"] == purpose and not rec["consumed"]:
                rec["consumed"] = True
                n += 1
        return n

    def mark_email_verified_and_activate(self, account_id: str) -> None:
        self.verified[account_id] = True
        self.accounts[account_id]["status"] = "active"

    def set_account_pending(self, account_id: str) -> None:
        self.accounts[account_id]["status"] = "pending_verification"

    def update_password_hash(self, account_id: str, password_hash: str) -> None:
        self.password_hashes[account_id] = password_hash

    def revoke_all_sessions(self, account_id: str) -> int:
        n = 0
        for s in self.sessions.values():
            if s["account_id"] == account_id and not s["revoked"]:
                s["revoked"] = True
                n += 1
        return n

    def seconds_since_last_token(self, account_id: str, purpose: str) -> Optional[float]:
        stamps = [
            r["created_at"]
            for r in self.tokens.values()
            if r["account_id"] == account_id and r["purpose"] == purpose
        ]
        if not stamps:
            return None
        return max(0.0, self.now - max(stamps))


def _fake_hash(raw: str) -> str:
    return "fakehash$" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _service(repo: FakeRepo, provider=None, cooldown: int = 60) -> MemberEmailService:
    return MemberEmailService(
        repo,
        hash_password=_fake_hash,
        provider=provider or NullEmailProvider(),
        frontend_base_url="https://frontend.example",
        resend_cooldown_seconds=cooldown,
    )


# --------------------------------------------------------------------------
# Token security matrix (service level)
# --------------------------------------------------------------------------

def test_verification_success_moves_account_to_active() -> None:
    repo = FakeRepo()
    aid = repo.add_account("a@example.com")
    svc = _service(repo)
    issued = svc.issue_verification(account_id=aid, email="a@example.com")
    raw = next(iter(repo.tokens))
    assert issued.ok
    res = svc.verify_email(raw_token=raw)
    assert res.ok and res.code == "verified"
    assert repo.accounts[aid]["status"] == "active"
    assert repo.verified[aid] is True


def test_verification_replay_denied() -> None:
    repo = FakeRepo()
    aid = repo.add_account("a@example.com")
    svc = _service(repo)
    svc.issue_verification(account_id=aid, email="a@example.com")
    raw = next(iter(repo.tokens))
    assert svc.verify_email(raw_token=raw).ok
    second = svc.verify_email(raw_token=raw)
    assert not second.ok and second.code == "invalid_token"


def test_expired_verification_denied() -> None:
    repo = FakeRepo()
    aid = repo.add_account("a@example.com")
    svc = _service(repo)
    svc.issue_verification(account_id=aid, email="a@example.com")
    raw = next(iter(repo.tokens))
    repo.now += 25 * 3600  # past 24h TTL
    res = svc.verify_email(raw_token=raw)
    assert not res.ok and res.code == "invalid_token"


def test_verify_and_reset_tokens_not_interchangeable() -> None:
    repo = FakeRepo()
    aid = repo.add_account("a@example.com")
    svc = _service(repo)
    # A verification token must not work as a reset token, and vice versa.
    svc.issue_verification(account_id=aid, email="a@example.com")
    verify_raw = next(iter(repo.tokens))
    assert svc.reset_password(raw_token=verify_raw, new_password="a" * 12).code == "invalid_token"

    svc.forgot_password(email="a@example.com")
    reset_raw = [r for r, rec in repo.tokens.items() if rec["purpose"] == PURPOSE_PASSWORD_RESET][0]
    assert not svc.verify_email(raw_token=reset_raw).ok


def test_unknown_and_empty_tokens_denied() -> None:
    repo = FakeRepo()
    svc = _service(repo)
    assert not svc.verify_email(raw_token="").ok
    assert not svc.verify_email(raw_token="nope").ok
    assert not svc.reset_password(raw_token="", new_password="a" * 12).ok
    assert not svc.reset_password(raw_token="nope", new_password="a" * 12).ok


def test_resend_cooldown_enforced() -> None:
    repo = FakeRepo()
    aid = repo.add_account("a@example.com")
    svc = _service(repo, cooldown=60)
    svc.issue_verification(account_id=aid, email="a@example.com")
    first_count = len(repo.tokens)
    # Immediately resending is within cooldown: no new token issued.
    svc.resend_verification(email="a@example.com")
    assert len(repo.tokens) == first_count
    # After cooldown passes, a new token may be issued (supersede + issue).
    repo.now += 120
    svc.resend_verification(email="a@example.com")
    assert len(repo.tokens) == first_count + 1


def test_resend_for_active_account_is_generic_and_issues_nothing() -> None:
    repo = FakeRepo()
    repo.add_account("a@example.com", status="active")
    svc = _service(repo)
    res = svc.resend_verification(email="a@example.com")
    assert res.ok
    assert len(repo.tokens) == 0


def test_forgot_password_is_enumeration_resistant() -> None:
    repo = FakeRepo()
    repo.add_account("real@example.com")
    svc = _service(repo)
    present = svc.forgot_password(email="real@example.com")
    absent = svc.forgot_password(email="ghost@example.com")
    assert present.ok and absent.ok
    assert present.code == absent.code == "forgot_generic"
    assert present.message == absent.message
    # A reset token exists only for the real account.
    assert any(r["purpose"] == PURPOSE_PASSWORD_RESET for r in repo.tokens.values())


def test_password_reset_success_revokes_all_sessions_and_rehashes() -> None:
    repo = FakeRepo()
    aid = repo.add_account("a@example.com", status="active")
    repo.add_session(aid)
    repo.add_session(aid)
    svc = _service(repo)
    svc.forgot_password(email="a@example.com")
    reset_raw = next(iter(repo.tokens))
    res = svc.reset_password(raw_token=reset_raw, new_password="newpassword12")
    assert res.ok and res.code == "password_reset"
    assert res.revoked_sessions == 2
    assert all(s["revoked"] for s in repo.sessions.values())
    assert repo.password_hashes[aid] == _fake_hash("newpassword12")


def test_password_reset_replay_denied() -> None:
    repo = FakeRepo()
    aid = repo.add_account("a@example.com", status="active")
    svc = _service(repo)
    svc.forgot_password(email="a@example.com")
    reset_raw = next(iter(repo.tokens))
    assert svc.reset_password(raw_token=reset_raw, new_password="newpassword12").ok
    assert not svc.reset_password(raw_token=reset_raw, new_password="another123456").ok


def test_expired_reset_denied() -> None:
    repo = FakeRepo()
    repo.add_account("a@example.com", status="active")
    svc = _service(repo)
    svc.forgot_password(email="a@example.com")
    reset_raw = next(iter(repo.tokens))
    repo.now += 2 * 3600  # past 1h reset TTL
    assert not svc.reset_password(raw_token=reset_raw, new_password="newpassword12").ok


def test_weak_new_password_rejected_before_token_consumed() -> None:
    repo = FakeRepo()
    repo.add_account("a@example.com", status="active")
    svc = _service(repo)
    svc.forgot_password(email="a@example.com")
    reset_raw = next(iter(repo.tokens))
    res = svc.reset_password(raw_token=reset_raw, new_password="short")
    assert not res.ok and res.code == "weak_password"
    # Token must remain usable since a weak password was rejected early.
    assert repo.tokens[reset_raw]["consumed"] is False


def test_reset_fails_closed_when_hasher_unavailable_without_consuming_token() -> None:
    repo = FakeRepo()
    aid = repo.add_account("a@example.com", status="active")
    repo.add_session(aid)
    # hash_password=None models the canonical Argon2 hasher being unavailable.
    svc = MemberEmailService(
        repo, hash_password=None, provider=NullEmailProvider(), frontend_base_url="https://x"
    )
    svc.forgot_password(email="a@example.com")
    reset_raw = next(iter(repo.tokens))
    res = svc.reset_password(raw_token=reset_raw, new_password="newpassword12")
    assert res.ok is False
    assert res.status_code == 503 and res.code == "service_unavailable"
    # Token must NOT be consumed, password must NOT change, sessions NOT revoked.
    assert repo.tokens[reset_raw]["consumed"] is False
    assert repo.password_hashes[aid] == "OLD_HASH"
    assert all(not s["revoked"] for s in repo.sessions.values())


def test_supersede_invalidates_prior_verification_token() -> None:
    repo = FakeRepo()
    aid = repo.add_account("a@example.com")
    svc = _service(repo)
    svc.issue_verification(account_id=aid, email="a@example.com")
    old_raw = next(iter(repo.tokens))
    repo.now += 120
    svc.resend_verification(email="a@example.com")  # supersede + issue new
    assert not svc.verify_email(raw_token=old_raw).ok


# --------------------------------------------------------------------------
# Provider abstraction
# --------------------------------------------------------------------------

def test_null_provider_never_fabricates_delivery() -> None:
    provider = build_email_provider({})
    assert provider.configured is False
    attempt = provider.send_verification_email(to_email="a@example.com", verify_link="https://x/verify?token=SECRET")
    assert attempt.delivered is False
    assert attempt.status == "PROVIDER_NOT_CONFIGURED"
    # The raw link/token must not appear in the audit record.
    assert "SECRET" not in str(attempt.to_audit_dict())


def test_mask_email_hides_local_part() -> None:
    assert mask_email("alice@example.com").endswith("@example.com")
    assert "alice" not in mask_email("alice@example.com")


# --------------------------------------------------------------------------
# HTTP routes
# --------------------------------------------------------------------------

class _FakeAuth:
    class _Hasher:
        def hash(self, raw: str) -> str:
            return _fake_hash(raw)

    def __init__(self) -> None:
        self._hasher = self._Hasher()


@pytest.fixture()
def client_and_repo():
    repo = FakeRepo()
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"repo": repo, "auth": _FakeAuth()}
    register_member_email_routes(app)
    return app.test_client(), repo


def test_routes_are_post_only_and_no_store(client_and_repo) -> None:
    client, repo = client_and_repo
    aid = repo.add_account("a@example.com")
    # GET must not be allowed (no state-changing GET).
    assert client.get("/api/v1/product/auth/verify-email").status_code == 405
    r = client.post("/api/v1/product/auth/forgot-password", json={"email": "a@example.com"})
    assert r.status_code == 200
    assert r.headers.get("Cache-Control") == "no-store"


def test_route_verify_then_reset_flow_no_token_leak(client_and_repo) -> None:
    client, repo = client_and_repo
    aid = repo.add_account("a@example.com")
    # issue a verification token via the service path
    _service(repo).issue_verification(account_id=aid, email="a@example.com")
    raw = next(iter(repo.tokens))
    r = client.post("/api/v1/product/auth/verify-email", json={"token": raw})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    # The raw token must never be echoed back in any response body.
    assert raw not in r.get_data(as_text=True)


def test_route_forgot_password_generic_for_missing_and_present(client_and_repo) -> None:
    client, repo = client_and_repo
    repo.add_account("real@example.com")
    a = client.post("/api/v1/product/auth/forgot-password", json={"email": "real@example.com"})
    b = client.post("/api/v1/product/auth/forgot-password", json={"email": "ghost@example.com"})
    assert a.get_json() == b.get_json()


def test_route_reset_password_reports_sessions_revoked(client_and_repo) -> None:
    client, repo = client_and_repo
    aid = repo.add_account("a@example.com", status="active")
    repo.add_session(aid)
    _service(repo).forgot_password(email="a@example.com")
    reset_raw = next(iter(repo.tokens))
    r = client.post(
        "/api/v1/product/auth/reset-password",
        json={"token": reset_raw, "new_password": "newpassword12"},
    )
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["sessions_revoked"] == 1


def test_route_rate_limit_triggers_429(client_and_repo) -> None:
    client, repo = client_and_repo
    repo.add_account("a@example.com")
    codes = [
        client.post("/api/v1/product/auth/forgot-password", json={"email": "a@example.com"}).status_code
        for _ in range(7)
    ]
    assert 429 in codes


def test_route_resend_is_enumeration_resistant_and_leaks_no_delivery_state(client_and_repo) -> None:
    client, repo = client_and_repo
    repo.add_account("pending@example.com", status="pending_verification")
    repo.add_account("active@example.com", status="active")
    r_unknown = client.post("/api/v1/product/auth/resend-verification", json={"email": "ghost@example.com"})
    r_pending = client.post("/api/v1/product/auth/resend-verification", json={"email": "pending@example.com"})
    r_active = client.post("/api/v1/product/auth/resend-verification", json={"email": "active@example.com"})
    for r in (r_unknown, r_pending, r_active):
        assert r.status_code == 200
    # Identical public response regardless of account existence/state.
    assert r_unknown.get_json() == r_pending.get_json() == r_active.get_json()
    body_text = r_pending.get_data(as_text=True)
    # No provider delivery state leaked to unauthenticated callers.
    for leaked in ("delivery_status", "delivery_provider", "email_provider_configured", "delivery_attempted", "null", "resend"):
        assert leaked not in body_text
