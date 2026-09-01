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
    assert set(m.values()) <= {"AVAILABLE", "LIMITED", "COMING_SOON", "UNAVAILABLE"}
    assert m["market_overview"] == "AVAILABLE"


# ---- data licensing gate ----

def test_only_licensed_datasets_expose_commercially():
    assert data_licenses.can_expose_commercially("usdm_public_ticker_ohlcv") is True
    for ds in ("oi_funding_liquidation", "onchain_flows_metrics", "creator_social_sentiment", "market_news_feed"):
        assert data_licenses.can_expose_commercially(ds) is False
    assert data_licenses.licensed_domains() == {"market"}


# ---- domains / Founder isolation ----

def test_founder_isolation_and_social_domains():
    assert domains.FOUNDER_PRIVATE_ISOLATED is True
    assert domains.founder_may_read("market") is False
    assert domains.founder_may_read("news_social") is False
    # SaaS surfaces read news_social/reputation; founder_private never does
    assert "founder_private" not in domains.readers_for("news_social")
    assert "founder_private" not in domains.readers_for("reputation")


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
