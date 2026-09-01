"""NEXUS-EXPERIENCE-1A foundation contracts + boundary tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.nexus_platform import data_licenses, domains, entitlements, plans, trial, view_modes
from backend.nexus_platform.checks.founder_social_boundary import scan_founder_social_violations
from backend.nexus_platform.checks.personal_demo_dependency import scan_personal_demo_dependencies

REPO = Path(__file__).resolve().parents[2]


# ---- plans / pricing / annual ----

def test_canonical_plans_and_prices():
    assert plans.CANONICAL_PLAN_CODES == ("free", "starter", "pro", "advanced", "enterprise")
    cat = {p.code: p for p in plans.list_plans()}
    assert cat["free"].monthly_usd_cents == 0
    assert cat["starter"].monthly_usd_cents == 1900 and cat["starter"].annual_usd_cents == 18240   # $182.40
    assert cat["pro"].monthly_usd_cents == 3900 and cat["pro"].annual_usd_cents == 37440           # $374.40
    assert cat["advanced"].monthly_usd_cents == 7900 and cat["advanced"].annual_usd_cents == 75840  # $758.40
    assert cat["enterprise"].contact_sales and cat["enterprise"].monthly_usd_cents is None


def test_annual_is_20pct_discount():
    pub = plans.public_catalog()
    assert pub["annual_discount_pct"] == 20
    for p in pub["plans"]:
        if p["monthly_usd_cents"]:
            assert p["annual_usd_cents"] == round(p["monthly_usd_cents"] * 12 * 0.8)
    assert pub["trial"] == {"code": "STARTER_TRIAL_30D", "grants": "starter", "days": 30,
                            "auto_charge": False, "on_expiry": "paid_else_free"}


# ---- trial ----

def test_trial_effective_plan_and_status():
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    reg = now - timedelta(days=5)
    # active trial → starter
    assert trial.effective_plan(now, registered_at=reg, paid_plan=None) == "starter"
    # expired trial → free
    old = now - timedelta(days=40)
    assert trial.effective_plan(now, registered_at=old, paid_plan=None) == "free"
    # paid always wins
    assert trial.effective_plan(now, registered_at=old, paid_plan="advanced") == "advanced"
    st = trial.trial_status(now, registered_at=reg, paid_plan=None)
    assert st["state"] == "TRIAL" and st["trial_active"] and st["days_remaining"] == 25


# ---- view mode != authorization ----

def test_view_mode_never_authorizes():
    assert view_modes.VIEW_MODES == ("simple", "standard", "pro")
    for vm in view_modes.VIEW_MODES:
        assert view_modes.authorizes(vm) is False  # density never grants access
    assert view_modes.normalize_view_mode("bogus") == "simple"


# ---- entitlements: honest states ----

def test_entitlement_states_are_honest():
    # market overview: FREE limited, STARTER+ available (backend ready)
    assert entitlements.resolve_state("market_overview", "free") == "LIMITED"
    assert entitlements.resolve_state("market_overview", "starter") == "AVAILABLE"
    # entitled but no licensed backend data yet → COMING_SOON (not fabricated)
    assert entitlements.resolve_state("oi_funding", "pro") == "COMING_SOON"
    assert entitlements.resolve_state("news_social_intel", "pro") == "COMING_SOON"
    assert entitlements.resolve_state("derivatives_full", "advanced") == "COMING_SOON"
    # not entitled for plan → UNAVAILABLE (locked)
    assert entitlements.resolve_state("derivatives_full", "free") == "UNAVAILABLE"
    assert entitlements.resolve_state("ai_screener", "starter") == "UNAVAILABLE"
    # only real-data capabilities are actually allowed today
    assert entitlements.is_allowed("market_overview", "free") is True
    assert entitlements.is_allowed("oi_funding", "advanced") is False  # coming soon, not allowed


def test_capability_matrix_admin_inspectable():
    m = entitlements.capability_matrix("pro")
    assert set(m.values()) <= {"AVAILABLE", "LIMITED", "BETA", "PARTIAL", "COMING_SOON", "UNAVAILABLE"}
    assert m["market_overview"] == "AVAILABLE"


def test_audited_capability_states_are_honest():
    # genuinely built on real market data → AVAILABLE (LIMITED on free)
    for cap in ("market_overview", "watchlist", "history"):
        assert entitlements.resolve_state(cap, "starter") == "AVAILABLE", cap
        assert entitlements.resolve_state(cap, "free") == "LIMITED", cap
    # real backend primitive but not fully productised → PARTIAL (never AVAILABLE)
    for cap in ("alerts", "nex_ai_digest"):
        assert entitlements.resolve_state(cap, "starter") == "PARTIAL", cap
        assert entitlements.capability_dimensions(cap)["backend_state"] == "partial"
    # not built → COMING_SOON even for a granting plan
    for cap in ("multi_chart", "custom_workspace", "advanced_alerts"):
        assert entitlements.resolve_state(cap, "advanced") == "COMING_SOON", cap
        assert entitlements.capability_dimensions(cap)["product_state"] == "coming_soon"


# ---- data licensing gates (raw display vs derived intelligence; fail closed) ----

MARKET_DS = "usdm_public_ticker_ohlcv"
UNLICENSED = ("oi_funding_liquidation", "onchain_flows_metrics", "creator_social_sentiment", "market_news_feed")


def test_license_derived_intelligence_gate():
    assert data_licenses.can_use_for_derived_intelligence(MARKET_DS) is True
    for ds in UNLICENSED:
        assert data_licenses.can_use_for_derived_intelligence(ds) is False


def test_license_raw_display_denied_without_redistribution():
    # market data permits DERIVED use but NOT raw redistribution/display
    assert data_licenses.can_display_raw_data(MARKET_DS) is False
    for ds in UNLICENSED:
        assert data_licenses.can_display_raw_data(ds) is False


def test_license_unknown_and_not_licensed_fail_closed():
    for fn in (data_licenses.can_use_for_derived_intelligence, data_licenses.can_display_raw_data,
               data_licenses.can_cache_dataset):
        assert fn("no_such_dataset") is False           # unknown → denied
        assert fn("market_news_feed") is False           # not_licensed → denied
    # unknown datasets conservatively require attribution
    assert data_licenses.requires_attribution("no_such_dataset") is True


def test_license_cache_and_attribution():
    assert data_licenses.can_cache_dataset(MARKET_DS) is True
    assert data_licenses.requires_attribution(MARKET_DS) is False
    assert data_licenses.requires_attribution("creator_social_sentiment") is True
    assert data_licenses.licensed_domains() == {"market"}


# ---- Enterprise is a SEPARATE product (no Personal-Advanced inheritance) ----

def test_enterprise_does_not_inherit_personal_capabilities():
    # Every non-enterprise capability must NOT grant the enterprise plan — so
    # adding a new Advanced Personal capability can never auto-appear in Enterprise.
    for cid, spec in entitlements.CAPABILITIES.items():
        if spec["domain"] != "enterprise":
            assert "enterprise" not in spec["plans"], f"{cid} leaks to enterprise plan"
            assert entitlements.resolve_state(cid, "enterprise") == "UNAVAILABLE", cid
    # A concrete Advanced Personal capability is UNAVAILABLE on the enterprise plan.
    assert entitlements.resolve_state("derivatives_full", "enterprise") == "UNAVAILABLE"
    assert entitlements.resolve_state("multi_chart", "enterprise") == "UNAVAILABLE"


def test_enterprise_capabilities_are_explicit():
    assert set(entitlements.ENTERPRISE_CAPABILITIES) >= {
        "org_seats", "shared_intelligence", "org_audit", "sso"}
    for cid in entitlements.ENTERPRISE_CAPABILITIES:
        assert entitlements.CAPABILITIES[cid]["plans"].get("enterprise") == "full"


def test_new_advanced_personal_capability_not_granted_to_enterprise():
    # Simulate adding a brand-new Advanced-only Personal capability at runtime.
    entitlements.CAPABILITIES["__probe_adv_cap__"] = entitlements._cap(
        "personal", {"advanced": "full"}, "ready", "available",
        entitlements.DS_MARKET, "probe")
    try:
        assert entitlements.resolve_state("__probe_adv_cap__", "advanced") == "AVAILABLE"
        assert entitlements.resolve_state("__probe_adv_cap__", "enterprise") == "UNAVAILABLE"
    finally:
        del entitlements.CAPABILITIES["__probe_adv_cap__"]


# ---- domains / Founder isolation ----

def test_founder_isolation_and_social_domains():
    assert domains.FOUNDER_PRIVATE_ISOLATED is True
    # Direct SaaS DB access is DENIED for every domain (physical/security boundary).
    assert domains.FOUNDER_DIRECT_SAAS_DB_ACCESS is False
    assert domains.founder_may_read_saas_db("market") is False
    assert domains.founder_may_read_saas_db("news_social") is False
    assert "founder_private" not in domains.readers_for("news_social")
    assert "founder_private" not in domains.readers_for("reputation")


def test_founder_safe_service_market_clarification():
    # Founder MAY consume separately-authorized safe market-data SERVICE outputs
    # (not DB), but NEVER social/reputation, even at the service level.
    assert domains.FOUNDER_SAFE_SERVICE_MARKET_ALLOWED is True
    assert domains.founder_may_consume_service_market("market") is True
    assert domains.founder_may_consume_service_market("news_social") is False
    assert domains.founder_may_consume_service_market("reputation") is False


# ---- Founder ↔ Social HARD BAN (critical) ----

def test_founder_runtime_has_no_social_imports():
    violations = scan_founder_social_violations(REPO)
    assert violations == [], f"Founder runtime imports banned social intelligence: {violations}"


# ---- Personal demo-dependency AUDIT (baseline for Workstream B) ----

def test_personal_demo_dependency_audit_baseline():
    # Workstream A documents the current violation; Workstream B must drive this to zero.
    hits = scan_personal_demo_dependencies(REPO)
    files = {h["file"] for h in hits}
    assert any("firstScreenAnswers" in f for f in files), files
    assert any("MemberFirstScreen" in f for f in files), files
