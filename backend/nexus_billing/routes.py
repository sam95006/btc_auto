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

import json
import os
from typing import Any, Optional

from flask import Flask, Response, jsonify, request

from backend.nexus_billing.entitlements import (
    EntitlementResolution,
    resolve_entitlements,
)
from backend.nexus_billing.event_repository import BillingEventRepository
from backend.nexus_billing.factory import build_stripe_config
from backend.nexus_billing.mock_provider import MockPaymentProvider
from backend.nexus_billing.plans import DEFAULT_PLAN_CODE, list_plans
from backend.nexus_billing.provider import KNOWN_EVENT_TYPES
from backend.nexus_billing.repository import SubscriptionRepository
from backend.nexus_billing.service import BillingError, BillingService
from backend.nexus_billing.stripe_provider import (
    StripeConfigError,
    StripePaymentProvider,
    normalize_stripe_event,
    verify_stripe_signature,
)
from backend.nexus_billing.subscription import Subscription, default_subscription

from backend.nexus_billing.usage_repository import UsageRepository
from backend.nexus_billing.usage_service import UsageDecision, UsageService

MOCK_ENABLED_CONFIG_KEY = "NEXUS_BILLING_MOCK_ENABLED"
BILLING_SERVICE_CONFIG_KEY = "NEXUS_BILLING_SERVICE"
STRIPE_CONFIG_CONFIG_KEY = "NEXUS_BILLING_STRIPE_CONFIG"
STRIPE_SERVICE_CONFIG_KEY = "NEXUS_BILLING_STRIPE_SERVICE"
USAGE_SERVICE_CONFIG_KEY = "NEXUS_BILLING_USAGE_SERVICE"
USAGE_DEMO_ENABLED_CONFIG_KEY = "NEXUS_BILLING_USAGE_DEMO_ENABLED"

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


def _mock_enabled(app: Flask) -> bool:
    return bool(app.config.get(MOCK_ENABLED_CONFIG_KEY))


def _billing_service(app: Flask) -> Optional[BillingService]:
    service = app.config.get(BILLING_SERVICE_CONFIG_KEY)
    if service is not None:
        return service
    pool = _services(app).get("pool")
    if pool is None:
        return None
    service = BillingService(
        subscription_repo=SubscriptionRepository(pool),
        event_repo=BillingEventRepository(pool),
        provider=MockPaymentProvider(),
    )
    app.config[BILLING_SERVICE_CONFIG_KEY] = service
    return service


def _stripe_config(app: Flask):
    cfg = app.config.get(STRIPE_CONFIG_CONFIG_KEY)
    if cfg is not None:
        return cfg
    return build_stripe_config(dict(os.environ))


def _stripe_service(app: Flask) -> Optional[BillingService]:
    svc = app.config.get(STRIPE_SERVICE_CONFIG_KEY)
    if svc is not None:
        return svc
    cfg = _stripe_config(app)
    pool = _services(app).get("pool")
    if cfg is None or pool is None:
        return None
    try:
        provider = StripePaymentProvider(cfg)
    except StripeConfigError:
        return None
    svc = BillingService(
        subscription_repo=SubscriptionRepository(pool),
        event_repo=BillingEventRepository(pool),
        provider=provider,
    )
    app.config[STRIPE_SERVICE_CONFIG_KEY] = svc
    return svc


def _usage_service(app: Flask) -> Optional[UsageService]:
    svc = app.config.get(USAGE_SERVICE_CONFIG_KEY)
    if svc is not None:
        return svc
    pool = _services(app).get("pool")
    if pool is None:
        return None
    svc = UsageService(usage_repo=UsageRepository(pool), subscription_repo=SubscriptionRepository(pool))
    app.config[USAGE_SERVICE_CONFIG_KEY] = svc
    return svc


def enforce_quota(
    app: Flask, account_id: str, quota_code: str, *, amount: int = 1, idempotency_key: str
) -> tuple[Optional[Response], Optional[UsageDecision]]:
    """Central quota gate. Returns (error_response, None) on deny/unavailable, or
    (None, decision) on success. 429 with a consistent USAGE_LIMIT_EXCEEDED
    classification when the quota is exhausted; fail closed otherwise."""
    svc = _usage_service(app)
    if svc is None:
        return _json_no_store({"error": "usage_unavailable", "classification": "UNAVAILABLE"}, 503), None
    decision = svc.consume(account_id=account_id, quota_code=quota_code, amount=amount, idempotency_key=idempotency_key)
    if decision.allowed:
        return None, decision
    # Consistent, distinct error semantics by reason (fail closed; never dress an
    # internal error up as "quota exhausted").
    reason = decision.reason or "quota_exceeded"
    if reason == "quota_exceeded":
        payload = {"error": "usage_limit_exceeded", "classification": "USAGE_LIMIT_EXCEEDED"}
        payload.update(decision.to_public_dict())
        return _json_no_store(payload, 429), None
    if reason == "usage_unavailable":
        return _json_no_store({"error": "usage_unavailable", "classification": "UNAVAILABLE"}, 503), None
    if reason in ("invalid_amount", "missing_idempotency_key"):
        return _json_no_store({"error": reason, "classification": "BAD_REQUEST"}, 400), None
    if reason in ("entitlement_required", "no_quota"):
        return _json_no_store(
            {"error": "entitlement_required", "classification": "ENTITLEMENT_REQUIRED", "required_quota": quota_code},
            403,
        ), None
    # unknown_quota / not_consumable / anything else -> fail closed as bad request.
    return _json_no_store({"error": "invalid_quota", "classification": "BAD_REQUEST"}, 400), None


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

    # ----- development/staging-only mock billing endpoints (disabled default) --
    @app.post("/api/v1/billing/mock/checkout")
    def billing_mock_checkout():
        if not _mock_enabled(app):
            return _json_no_store({"error": "not_found", "classification": "DISABLED"}, 404)
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        service = _billing_service(app)
        if service is None:
            return _json_no_store({"error": "billing_unavailable", "classification": "UNAVAILABLE"}, 503)
        body = request.get_json(silent=True) or {}
        plan_code = str(body.get("plan_code") or "").strip().lower()
        try:
            session = service.start_checkout(account_id=account_id, plan_code=plan_code)
        except BillingError:
            return _json_no_store({"error": "invalid_checkout_plan", "classification": "INVALID_PLAN"}, 400)
        return _json_no_store({"checkout": session.to_public_dict()})

    @app.post("/api/v1/billing/mock/event")
    def billing_mock_event():
        if not _mock_enabled(app):
            return _json_no_store({"error": "not_found", "classification": "DISABLED"}, 404)
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        service = _billing_service(app)
        if service is None:
            return _json_no_store({"error": "billing_unavailable", "classification": "UNAVAILABLE"}, 503)
        body = request.get_json(silent=True) or {}
        event_type = str(body.get("event_type") or "").strip()
        if event_type not in KNOWN_EVENT_TYPES:
            return _json_no_store({"error": "unsupported_event_type", "classification": "INVALID_EVENT"}, 400)
        plan_code = body.get("plan_code")
        # The account is ALWAYS derived from the session; a body/query account is
        # never honored. The mock provider fabricates the normalized event.
        event = MockPaymentProvider().make_event(
            account_id=account_id,
            event_type=event_type,
            target_plan_code=str(plan_code).strip().lower() if isinstance(plan_code, str) else None,
            provider_event_id=(str(body.get("provider_event_id")).strip() if body.get("provider_event_id") else None),
        )
        result = service.process_provider_event(event)
        return _json_no_store({"result": result})

    @app.post("/api/v1/billing/mock/cancel")
    def billing_mock_cancel():
        if not _mock_enabled(app):
            return _json_no_store({"error": "not_found", "classification": "DISABLED"}, 404)
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        service = _billing_service(app)
        if service is None:
            return _json_no_store({"error": "billing_unavailable", "classification": "UNAVAILABLE"}, 503)
        return _json_no_store({"result": service.request_cancellation(account_id=account_id)})

    # ----- member usage (read-only; own account only) -----
    @app.get("/api/v1/billing/usage")
    def billing_usage():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        svc = _usage_service(app)
        if svc is None:
            return _json_no_store({"error": "usage_unavailable", "classification": "UNAVAILABLE"}, 503)
        try:
            data = svc.resolve_usage(account_id)
        except Exception:  # noqa: BLE001 - never expose internals; UI shows unavailable
            return _json_no_store({"error": "usage_unavailable", "classification": "UNAVAILABLE"}, 503)
        return _json_no_store(data)

    # ----- representative non-trading quota-enforced endpoint (disabled default) -----
    @app.post("/api/v1/billing/usage/consume-demo")
    def billing_usage_consume_demo():
        if not app.config.get(USAGE_DEMO_ENABLED_CONFIG_KEY):
            return _json_no_store({"error": "not_found", "classification": "DISABLED"}, 404)
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        # Access = Authentication AND Entitlement AND Quota. Entitlement first.
        denied_entitlement = enforce_entitlement(app, "advanced_analysis")
        if denied_entitlement is not None:
            return denied_entitlement
        body = request.get_json(silent=True) or {}
        idempotency_key = str(body.get("idempotency_key") or "").strip()
        if not idempotency_key:
            return _json_no_store({"error": "missing_idempotency_key", "classification": "BAD_REQUEST"}, 400)
        err, decision = enforce_quota(
            app, account_id, "advanced_analysis_requests_daily", amount=1, idempotency_key=idempotency_key
        )
        if err is not None:
            return err
        assert decision is not None
        return _json_no_store(
            {"ok": True, "data_class": "USAGE_DEMO_READ_ONLY", "remaining": decision.remaining}
        )

    # ----- provider-neutral real checkout (Stripe when configured) -----
    @app.post("/api/v1/billing/checkout")
    def billing_checkout():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        service = _stripe_service(app)
        if service is None:
            # Provider not configured (e.g. sandbox creds absent). Deferred, not
            # an error the member can fix — never falls back to granting access.
            return _json_no_store({"error": "billing_provider_unavailable", "classification": "UNAVAILABLE"}, 503)
        body = request.get_json(silent=True) or {}
        plan_code = str(body.get("plan_code") or "").strip().lower()
        try:
            session = service.start_checkout(account_id=account_id, plan_code=plan_code)
        except BillingError:
            return _json_no_store({"error": "invalid_checkout_plan", "classification": "INVALID_PLAN"}, 400)
        except StripeConfigError:
            return _json_no_store({"error": "billing_provider_unavailable", "classification": "UNAVAILABLE"}, 503)
        return _json_no_store({"checkout": session.to_public_dict()})

    def _active_service(app: Flask) -> Optional[BillingService]:
        # Prefer the configured real provider (Stripe); fall back to the mock
        # service only when mock is explicitly enabled.
        svc = _stripe_service(app)
        if svc is not None:
            return svc
        if _mock_enabled(app):
            return _billing_service(app)
        return None

    @app.post("/api/v1/billing/cancel")
    def billing_cancel():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        service = _active_service(app)
        if service is None:
            return _json_no_store({"error": "billing_provider_unavailable", "classification": "UNAVAILABLE"}, 503)
        try:
            # Account/subscription reference come from the server's own repo,
            # never from the client.
            result = service.request_cancellation(account_id=account_id)
        except StripeConfigError:
            return _json_no_store({"error": "billing_provider_unavailable", "classification": "UNAVAILABLE"}, 503)
        return _json_no_store({"result": result})

    @app.post("/api/v1/billing/portal")
    def billing_portal():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        service = _active_service(app)
        if service is None:
            return _json_no_store({"error": "billing_provider_unavailable", "classification": "UNAVAILABLE"}, 503)
        try:
            portal = service.create_billing_portal(account_id=account_id)
        except StripeConfigError:
            return _json_no_store({"error": "portal_unavailable", "classification": "UNAVAILABLE"}, 503)
        return _json_no_store({"portal": portal.to_public_dict()})

    # ----- Stripe webhook (no member session; signature-verified) -----
    @app.post("/api/v1/billing/webhook/stripe")
    def billing_webhook_stripe():
        cfg = _stripe_config(app)
        if cfg is None:
            return _json_no_store({"error": "webhook_unavailable", "classification": "UNAVAILABLE"}, 503)
        # Use the RAW body for signature verification BEFORE any parsing.
        raw = request.get_data()
        signature = request.headers.get("Stripe-Signature", "")
        if not verify_stripe_signature(raw, signature, cfg.webhook_secret, tolerance=cfg.signature_tolerance_seconds):
            return _json_no_store({"error": "invalid_signature", "classification": "SIGNATURE_INVALID"}, 400)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _json_no_store({"error": "malformed_payload", "classification": "MALFORMED"}, 400)
        event = normalize_stripe_event(payload)
        if event is None:
            # Unknown/ignored event type or unmapped status: acknowledge, no-op.
            return _json_no_store({"received": True, "handled": False}, 200)
        service = _stripe_service(app)
        if service is None:
            return _json_no_store({"error": "webhook_unavailable", "classification": "UNAVAILABLE"}, 503)
        result = service.process_provider_event(event)
        if result.get("status") == "error" and result.get("retryable"):
            # Transient failure: signal Stripe to retry (do not ack as done).
            return _json_no_store({"received": True, "retry": True}, 500)
        return _json_no_store({"received": True, "result_status": result.get("status")}, 200)
