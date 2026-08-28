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

from backend.nexus_billing.plans import DEFAULT_PLAN_CODE, list_plans
from backend.nexus_billing.repository import SubscriptionRepository
from backend.nexus_billing.subscription import default_subscription

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
