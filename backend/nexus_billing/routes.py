"""Read-only Billing HTTP routes for BILLING-1.

Endpoints:
  * GET /api/v1/billing/plans        -> the logical plan catalog (public).
  * GET /api/v1/billing/subscription -> the AUTHENTICATED caller's subscription.

The backend is the sole source of truth. The subscription endpoint derives the
account strictly from the authenticated session — it never accepts an
account/plan id from the client. Any missing/ambiguous case resolves to the
safe default (free / inactive); a paid plan is never granted by accident.

No checkout endpoint, no webhook endpoint, and no payment provider are part of
BILLING-1.
"""

from __future__ import annotations

from typing import Any, Optional

from flask import Flask, Response, jsonify, request

from backend.nexus_billing.entitlements import (
    EntitlementResolution,
    resolve_entitlements,
)
from backend.nexus_billing.plans import DEFAULT_PLAN_CODE, list_plans
from backend.nexus_billing.repository import SubscriptionRepository
from backend.nexus_billing.subscription import Subscription, default_subscription

SUBSCRIPTION_REPO_CONFIG_KEY = "NEXUS_BILLING_SUBSCRIPTION_REPO"


def _services(app: Flask) -> dict[str, Any]:
    return dict(app.config.get("NEXUS_PRODUCT_ALPHA_SERVICES") or {})


def _session_id() -> Optional[str]:
    return request.headers.get("X-Nexus-Session") or request.cookies.get("nexus_session")


def _authenticated_account_id(app: Flask) -> Optional[str]:
    auth = _services(app).get("auth")
    session_id = _session_id()
    if not auth or not session_id:
        return None
    identity = auth.resolve_session(session_id)
    if not identity:
        return None
    return identity.get("account_id")


def _subscription_repo(app: Flask) -> Optional[SubscriptionRepository]:
    repo = app.config.get(SUBSCRIPTION_REPO_CONFIG_KEY)
    if repo is not None:
        return repo
    pool = _services(app).get("pool")
    if pool is None:
        return None
    repo = SubscriptionRepository(pool)
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = repo
    return repo


def _json_no_store(payload: dict[str, Any], status: int = 200) -> Response:
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def _account_subscription(app: Flask, account_id: str) -> Optional[Subscription]:
    repo = _subscription_repo(app)
    subscription = repo.get_by_account(account_id) if repo is not None else None
    # Missing row or no repository/pool both resolve to the safe non-paid
    # default rather than failing open to a paid plan.
    return subscription if subscription is not None else default_subscription(account_id)


def resolve_request_entitlements(
    app: Flask,
) -> tuple[Optional[EntitlementResolution], Optional[Response]]:
    """Resolve the AUTHENTICATED caller's entitlements from the backend only.

    Returns (resolution, None) when authenticated, or (None, 401_response) when
    not. The account is derived strictly from the session — never from client
    input — so a caller can only ever resolve their own entitlements.
    """
    account_id = _authenticated_account_id(app)
    if not account_id:
        return None, _json_no_store(
            {"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401
        )
    resolution = resolve_entitlements(_account_subscription(app, account_id))
    return resolution, None


def enforce_entitlement(app: Flask, feature_code: str) -> Optional[Response]:
    """Central entitlement gate. Returns an error Response when access must be
    denied (unauthenticated -> 401; lacking the entitlement -> 403 with a
    consistent ENTITLEMENT_REQUIRED classification), or None when allowed.

    This is the entitlement dimension only; a route may additionally require an
    RBAC check (e.g. services['rbac'].require_permission(...)). The two layers
    compose — RBAC PASS AND ENTITLEMENT PASS — without being merged here.
    """
    resolution, error = resolve_request_entitlements(app)
    if error is not None:
        return error
    assert resolution is not None
    if not resolution.has(feature_code):
        return _json_no_store(
            {
                "error": "entitlement_required",
                "classification": "ENTITLEMENT_REQUIRED",
                "required_feature": feature_code,
            },
            403,
        )
    return None


def register_billing_routes(app: Flask) -> None:
    @app.get("/api/v1/billing/plans")
    def billing_plans():
        return _json_no_store(
            {
                "plans": [plan.to_public_dict() for plan in list_plans()],
                "default_plan_code": DEFAULT_PLAN_CODE,
            }
        )

    @app.get("/api/v1/billing/subscription")
    def billing_subscription():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store(
                {"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401
            )
        repo = _subscription_repo(app)
        subscription = None
        if repo is not None:
            subscription = repo.get_by_account(account_id)
        # Missing row, or no repository/pool available, both resolve to the safe
        # non-paid default rather than failing open to a paid plan.
        if subscription is None:
            subscription = default_subscription(account_id)
        return _json_no_store({"subscription": subscription.to_public_dict()})

    @app.get("/api/v1/billing/entitlements")
    def billing_entitlements():
        resolution, error = resolve_request_entitlements(app)
        if error is not None:
            return error
        assert resolution is not None
        return _json_no_store(resolution.to_public_dict())

    @app.get("/api/v1/billing/protected/advanced-signals")
    def billing_protected_advanced_signals():
        # Representative read-only, non-trading capability gated by the central
        # entitlement engine. Free is denied; Pro/Advanced/Enterprise allowed.
        denied = enforce_entitlement(app, "advanced_signals")
        if denied is not None:
            return denied
        return _json_no_store(
            {
                "feature": "advanced_signals",
                "allowed": True,
                "data_class": "ENTITLEMENT_DEMO_READ_ONLY",
            }
        )
