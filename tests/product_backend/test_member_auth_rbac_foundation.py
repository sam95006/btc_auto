from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from flask import Flask

from backend.nexus_product_backend.auth_alpha import AuthAlphaService
from backend.nexus_product_backend.entitlement_alpha import EntitlementAlphaService
from backend.nexus_product_backend.member_foundation import (
    CANONICAL_MEMBER_ROLES,
    CANONICAL_PLANS,
    ENTITLEMENT_SOURCES,
    FORBIDDEN_MEMBER_CAPABILITIES,
    account_can_use_member_api,
    build_entitlement_snapshot,
    feature_allowed,
    normalize_account_status,
    normalize_member_role,
    normalize_plan,
)
from backend.nexus_product_backend.rbac_alpha import RbacAlphaService
from backend.nexus_product_backend.routes import register_product_alpha_routes


class InMemoryProductRepo:
    """Test double for the existing ProductRepository contract."""

    def __init__(self) -> None:
        self.accounts: dict[str, dict[str, Any]] = {}
        self.email_index: dict[str, str] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.entitlements: dict[str, list[str]] = {}
        self.roles: dict[str, set[str]] = {}
        self.password_hashes: dict[str, str] = {}
        self.counter = 0

    def _next(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}_{self.counter}"

    def create_account(self, email: str, password_hash: str) -> str:
        account_id = self._next("acct")
        self.accounts[account_id] = {
            "account_id": account_id,
            "email": email,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        }
        self.email_index[email] = account_id
        self.password_hashes[account_id] = password_hash
        self.roles[account_id] = {"role_member"}
        return account_id

    def register_staging_account(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        founder: bool,
        csrf_token_hash: str | None = None,
    ) -> tuple[str, str]:
        del display_name
        account_id = self.create_account(email, password_hash)
        if founder:
            self.roles[account_id] = {"role_founder"}
            self.entitlements[account_id] = ["ENTERPRISE"]
        return account_id, self.create_session(account_id, csrf_token_hash=csrf_token_hash)

    def get_account_by_email(self, email: str) -> dict[str, Any] | None:
        account_id = self.email_index.get(email)
        if not account_id:
            return None
        account = self.accounts[account_id]
        return {
            "account_id": account_id,
            "email": account["email"],
            "status": account["status"],
            "password_hash": self.password_hashes[account_id],
        }

    def create_session(
        self,
        account_id: str,
        *,
        ttl_hours: int = 24,
        csrf_token_hash: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        del ip_address, user_agent
        session_id = self._next("sess")
        self.sessions[session_id] = {
            "session_id": session_id,
            "account_id": account_id,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
            "revoked_at": None,
            "csrf_token_hash": csrf_token_hash,
        }
        return session_id

    def get_active_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.sessions.get(session_id)
        if not session or session["revoked_at"] is not None:
            return None
        if session["expires_at"] < datetime.now(timezone.utc):
            return None
        account = self.accounts.get(session["account_id"])
        if not account or not account_can_use_member_api(account["status"]):
            return None
        return {
            "session_id": session_id,
            "account_id": session["account_id"],
            "email": account["email"],
            "status": account["status"],
            "created_at": account["created_at"].isoformat(),
            "_csrf_token_hash": session["csrf_token_hash"],
        }

    def revoke_session(self, session_id: str) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["revoked_at"] = datetime.now(timezone.utc)

    def grant_entitlement(self, account_id: str, product_code: str) -> None:
        self.entitlements.setdefault(account_id, []).append(product_code)

    def active_entitlements(self, account_id: str) -> list[str]:
        return list(self.entitlements.get(account_id, []))

    def bind_role(self, account_id: str, role_id: str, org_id: str | None = None) -> None:
        del org_id
        self.roles.setdefault(account_id, set()).add(role_id)

    def role_ids(self, account_id: str, org_id: str | None = None) -> list[str]:
        del org_id
        return sorted(self.roles.get(account_id, set()))

    def role_permissions(self, account_id: str, org_id: str | None = None) -> set[str]:
        del org_id
        role_ids = self.roles.get(account_id, set())
        permissions = {"product.view"} if "role_member" in role_ids else set()
        if "role_founder" in role_ids:
            permissions |= {
                "product.view",
                "founder.operator.read",
                "founder.diagnostics.read",
                "founder.live_ops.read",
            }
        if "role_admin" in role_ids:
            permissions |= {"org.view_audit", "org.manage_members"}
        return permissions

    def profile(self, account_id: str) -> dict[str, Any]:
        account = self.accounts[account_id]
        return {
            "account_id": account_id,
            "email": account["email"],
            "display_name": account["email"].split("@")[0],
            "locale": "zh-Hant-TW",
            "timezone": "Asia/Taipei",
            "privacy_preferences": {},
            "version": 1,
        }


@pytest.fixture()
def repo() -> InMemoryProductRepo:
    return InMemoryProductRepo()


@pytest.fixture()
def auth(repo: InMemoryProductRepo) -> AuthAlphaService:
    return AuthAlphaService(repo)  # type: ignore[arg-type]


@pytest.fixture()
def app(repo: InMemoryProductRepo, auth: AuthAlphaService) -> Flask:
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["NEXUS_STAGING_MEMBER_AUTH_ENABLED"] = True
    flask_app.config["NEXUS_STAGING_REGISTRATION_ENABLED"] = True
    flask_app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {
        "repo": repo,
        "auth": auth,
        "entitlement": EntitlementAlphaService(repo, auth),  # type: ignore[arg-type]
        "rbac": RbacAlphaService(repo, auth),  # type: ignore[arg-type]
    }
    register_product_alpha_routes(flask_app)
    return flask_app


def register_user(auth: AuthAlphaService, email: str = "member@example.invalid") -> dict[str, Any]:
    return auth.register(email, "safe-password-12345")


def test_register_creates_stable_user_identity(repo: InMemoryProductRepo, auth: AuthAlphaService) -> None:
    registration = register_user(auth)
    assert registration["account_id"].startswith("acct_")
    assert registration["account_id"] != "member@example.invalid"
    assert repo.accounts[registration["account_id"]]["email"] == "member@example.invalid"


def test_password_plaintext_is_never_persisted(repo: InMemoryProductRepo, auth: AuthAlphaService) -> None:
    registration = register_user(auth)
    stored = repo.password_hashes[registration["account_id"]]
    assert stored != "safe-password-12345"
    assert stored.startswith("$argon2")


def test_valid_login_creates_valid_session(auth: AuthAlphaService) -> None:
    register_user(auth)
    login = auth.login("member@example.invalid", "safe-password-12345")
    assert auth.resolve_session(login["session_id"]) is not None
    assert login["csrf_token"]


def test_wrong_password_rejected(auth: AuthAlphaService) -> None:
    register_user(auth)
    with pytest.raises(ValueError, match="invalid_credentials"):
        auth.login("member@example.invalid", "wrong-password")


def test_expired_session_rejected(repo: InMemoryProductRepo, auth: AuthAlphaService) -> None:
    registration = register_user(auth)
    repo.sessions[registration["session_id"]]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert auth.resolve_session(registration["session_id"]) is None


def test_revoked_session_rejected(repo: InMemoryProductRepo, auth: AuthAlphaService) -> None:
    registration = register_user(auth)
    repo.revoke_session(registration["session_id"])
    assert auth.resolve_session(registration["session_id"]) is None


def test_logout_invalidates_session(auth: AuthAlphaService) -> None:
    registration = register_user(auth)
    auth.logout(registration["session_id"])
    assert auth.resolve_session(registration["session_id"]) is None


def test_disabled_account_cannot_access_protected_api(
    repo: InMemoryProductRepo, auth: AuthAlphaService, app: Flask
) -> None:
    registration = register_user(auth)
    repo.accounts[registration["account_id"]]["status"] = "disabled"
    response = app.test_client().get(
        "/api/v1/member/session", headers={"X-Nexus-Session": registration["session_id"]}
    )
    assert response.status_code == 401


def test_unknown_user_session_rejected(app: Flask) -> None:
    response = app.test_client().get("/api/v1/member/session", headers={"X-Nexus-Session": "sess_missing"})
    assert response.status_code == 401


def test_new_user_without_billing_entitlement_does_not_receive_pro(
    auth: AuthAlphaService,
) -> None:
    registration = register_user(auth)
    entitlement = EntitlementAlphaService(auth.repo, auth)  # type: ignore[arg-type]
    decision = entitlement.decision_from_session(registration["session_id"], "AI_MARKET_ANALYST")
    assert decision["plan"] == "BEGINNER"
    assert decision["entitlement_source"] == "SYSTEM_DEFAULT"
    assert decision["allowed"] is False


@pytest.mark.parametrize(
    ("plan", "capability", "allowed"),
    [
        ("BEGINNER", "DECISION_REASON_SUMMARY", False),
        ("BEGINNER", "AI_MARKET_ANALYST", False),
        ("INTERMEDIATE", "DECISION_REASON_SUMMARY", True),
        ("INTERMEDIATE", "AI_MARKET_ANALYST", False),
        ("PRO", "AI_MARKET_ANALYST", True),
        ("BOGUS", "MARKET_OVERVIEW", False),
        ("PRO", "UNKNOWN_FEATURE", False),
    ],
)
def test_plan_entitlements_fail_closed(plan: str, capability: str, allowed: bool) -> None:
    assert feature_allowed(plan, capability) is allowed


def test_canonical_plan_and_role_models() -> None:
    assert CANONICAL_PLANS == ("BEGINNER", "INTERMEDIATE", "PRO", "ENTERPRISE")
    assert CANONICAL_MEMBER_ROLES == ("MEMBER", "FOUNDER_ADMIN")
    assert normalize_plan("FREE") == "BEGINNER"
    assert normalize_plan("ADVANCED") == "INTERMEDIATE"
    assert normalize_plan("PRO") == "PRO"
    assert normalize_plan("ENTERPRISE") == "ENTERPRISE"
    assert normalize_member_role(["role_founder"]) == "FOUNDER_ADMIN"
    assert normalize_member_role(["role_member"]) == "MEMBER"


def test_enterprise_member_cannot_access_founder_operation(
    repo: InMemoryProductRepo, auth: AuthAlphaService, app: Flask
) -> None:
    registration = register_user(auth)
    repo.grant_entitlement(registration["account_id"], "ENTERPRISE")
    response = app.test_client().get(
        "/api/v1/founder/operator", headers={"X-Nexus-Session": registration["session_id"]}
    )
    assert response.status_code == 403


def test_pro_member_cannot_access_founder_operation(
    repo: InMemoryProductRepo, auth: AuthAlphaService, app: Flask
) -> None:
    registration = register_user(auth)
    repo.grant_entitlement(registration["account_id"], "PRO")
    response = app.test_client().get(
        "/api/v1/founder/operator", headers={"X-Nexus-Session": registration["session_id"]}
    )
    assert response.status_code == 403


def test_founder_operation_requires_founder_admin_role(
    repo: InMemoryProductRepo, auth: AuthAlphaService, app: Flask
) -> None:
    registration = register_user(auth)
    repo.bind_role(registration["account_id"], "role_founder")
    response = app.test_client().get(
        "/api/v1/founder/operator", headers={"X-Nexus-Session": registration["session_id"]}
    )
    assert response.status_code == 200


def test_frontend_hiding_is_not_sufficient_direct_api_denied(
    auth: AuthAlphaService, app: Flask
) -> None:
    registration = register_user(auth)
    response = app.test_client().post(
        "/api/v1/product/entitlement/check",
        headers={"X-Nexus-Session": registration["session_id"]},
        json={"capability_id": "AI_MARKET_ANALYST"},
    )
    assert response.status_code == 403
    assert response.get_json()["allowed"] is False


def test_intermediate_and_pro_server_side_entitlement_paths(
    repo: InMemoryProductRepo, auth: AuthAlphaService, app: Flask
) -> None:
    intermediate = register_user(auth, "intermediate@example.invalid")
    repo.grant_entitlement(intermediate["account_id"], "INTERMEDIATE")
    pro = register_user(auth, "pro@example.invalid")
    repo.grant_entitlement(pro["account_id"], "PRO")

    client = app.test_client()
    assert client.post(
        "/api/v1/product/entitlement/check",
        headers={"X-Nexus-Session": intermediate["session_id"]},
        json={"capability_id": "DECISION_REASON_SUMMARY"},
    ).status_code == 200
    assert client.post(
        "/api/v1/product/entitlement/check",
        headers={"X-Nexus-Session": intermediate["session_id"]},
        json={"capability_id": "AI_MARKET_ANALYST"},
    ).status_code == 403
    assert client.post(
        "/api/v1/product/entitlement/check",
        headers={"X-Nexus-Session": pro["session_id"]},
        json={"capability_id": "AI_MARKET_ANALYST"},
    ).status_code == 200


@pytest.mark.parametrize(
    "capability",
    [
        "EXCHANGE_WRITE",
        "CERTIFIED_RUNTIME_START",
        "CERTIFIED_SHORT_START",
        "SIX_HOUR_RUNTIME_START",
        "TWELVE_HOUR_RUNTIME_START",
    ],
)
def test_member_identity_cannot_reach_private_execution(capability: str) -> None:
    assert capability in FORBIDDEN_MEMBER_CAPABILITIES
    assert feature_allowed("ENTERPRISE", capability) is False


def test_no_query_string_auth_secret_accepted(auth: AuthAlphaService, app: Flask) -> None:
    registration = register_user(auth)
    response = app.test_client().get(f"/api/v1/member/session?session={registration['session_id']}")
    assert response.status_code == 401


def test_cookie_auth_requires_csrf_for_state_change(
    auth: AuthAlphaService, app: Flask
) -> None:
    registration = register_user(auth)
    client = app.test_client()
    client.set_cookie("nexus_session", registration["session_id"])
    denied = client.post("/api/v1/member/session/logout")
    assert denied.status_code == 403
    allowed = client.post("/api/v1/member/session/logout", headers={"X-Nexus-CSRF": registration["csrf_token"]})
    assert allowed.status_code == 200


def test_production_capable_mode_never_returns_inline_email_tokens(app: Flask) -> None:
    payload = app.test_client().get("/api/v1/product/auth/foundation").get_json()
    assert payload["inline_verification_token_allowed_in_production"] is False


def test_entitlement_snapshot_contract() -> None:
    snapshot = build_entitlement_snapshot("acct_1", ["UNKNOWN", "PRO"])
    assert snapshot.user_id == "acct_1"
    assert snapshot.plan == "PRO"
    assert snapshot.source in ENTITLEMENT_SOURCES
    assert "AI_MARKET_ANALYST" in snapshot.features


def test_account_status_contract() -> None:
    assert normalize_account_status("active") == "ACTIVE"
    assert normalize_account_status("disabled") == "DISABLED"
    assert normalize_account_status("pending_verification") == "PENDING_VERIFICATION"
    assert account_can_use_member_api("active") is True
    assert account_can_use_member_api("disabled") is False
    assert account_can_use_member_api("pending_verification") is False
