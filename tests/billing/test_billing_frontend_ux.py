from __future__ import annotations

from pathlib import Path

FE = Path("frontend/src/member_platform_v1")
API = FE / "services" / "stagingApi.ts"
BILLING_PAGES = FE / "pages" / "BillingPages.tsx"
PRESENTATION = FE / "billing" / "presentation.ts"
INDEX = FE / "index.tsx"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_billing_api_client_only_sends_plan_code() -> None:
    src = _read(API)
    assert "getBillingPlans" in src
    assert "getBillingSubscription" in src
    assert "getBillingEntitlements" in src
    assert 'postBilling("/billing/checkout", { plan_code: planCode })' in src
    # The client must not send authoritative price/url/customer identity.
    for banned in ("price_id", "success_url", "cancel_url", "customer_id"):
        assert banned not in src


def test_checkout_redirect_uses_backend_checkout_url() -> None:
    src = _read(BILLING_PAGES)
    # The redirect target comes from the server response, never composed client-side.
    assert "res.body?.checkout?.checkout_url" in src
    assert "window.location.href = url" in src
    assert "stripe.com" not in src  # frontend never builds a Stripe URL itself


def test_success_page_does_not_assume_from_redirect() -> None:
    src = _read(BILLING_PAGES)
    # No trusting of ?success= / session_id in the URL to unlock.
    assert "success=true" not in src
    assert "getBillingSubscription()" in src  # it polls verified backend state
    assert '"confirming"' in src and 'useState<"confirming"' in src
    assert 'ACTIVE_STATUSES.has(subscription.status)' in src


def test_cancel_return_page_does_no_mutation() -> None:
    src = _read(BILLING_PAGES)
    # BillingCancelPage must not call any mutating billing API.
    start = src.index("export function BillingCancelPage")
    block = src[start:]
    for mutation in ("startBillingCheckout", "cancelBillingSubscription", "openBillingPortal", "fetch("):
        assert mutation not in block


def test_enterprise_is_contact_not_self_checkout() -> None:
    src = _read(BILLING_PAGES)
    assert 'plan.code === "enterprise"' in src
    assert "企業方案即將開放" in src
    # No hardcoded email / unregistered domain / branding placeholder anywhere.
    for banned in ("nexus.local", "mailto:", "ELVUMO", "KELYVORA", "TELYVOR", "NAVELYR"):
        assert banned not in src
    pres = _read(PRESENTATION)
    assert '"starter", "pro", "advanced"' in pres  # enterprise absent from self-service
    assert "enterprise" not in pres.split("SELF_SERVICE_PLANS")[1].split("]")[0]


def test_status_and_entitlements_are_presented_friendly() -> None:
    pres = _read(PRESENTATION)
    assert "STATUS_LABELS" in pres and "past_due" in pres
    assert "ENTITLEMENT_LABELS" in pres and "advanced_signals" in pres
    src = _read(BILLING_PAGES)
    assert "statusLabel(status)" in src
    assert "entitlements.map(entitlementLabel)" in src


def test_billing_routes_registered() -> None:
    src = _read(INDEX)
    assert 'path="/billing/success"' in src
    assert 'path="/billing/cancel"' in src
    assert "BillingCenterPage" in src  # membership -> billing center


def test_billing_ui_handles_loading_error_unavailable() -> None:
    src = _read(BILLING_PAGES)
    assert "載入帳務資訊中" in src  # loading
    assert "無法載入帳務資訊" in src  # error
    assert "res.status === 503" in src  # provider unavailable handled
    assert "付款出現問題" in src  # past_due UI


def test_usage_summary_ui_present() -> None:
    api = _read(API)
    assert "getBillingUsage" in api
    src = _read(BILLING_PAGES)
    assert '"usage-summary"' in src
    assert "使用額度" in src
    assert "剩餘" in src  # remaining shown
    assert "本期額度已用完" in src  # exhausted state
    assert "使用額度目前無法取得" in src  # unavailable state (fail-safe, not unlimited)
    # UI is not security: no localStorage authority anywhere in billing pages.
    assert "localStorage" not in src
    assert "sessionStorage" not in src


def test_no_hardcoded_enterprise_email_anywhere() -> None:
    for p in (BILLING_PAGES, PRESENTATION):
        text = _read(p)
        assert "nexus.local" not in text
        assert "mailto:" not in text
