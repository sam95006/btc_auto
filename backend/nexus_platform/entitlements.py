"""Entitlement capability registry (NEXUS-EXPERIENCE-1A).

Backend-authoritative mapping of capability × plan → honest availability STATE.
Two independent axes are combined:

  * plan grant  — does the plan entitle this capability?  full | limited | None
  * backend readiness — does real, legally-usable backend data exist TODAY?
                        ready | coming_soon   (per "DO NOT IMPLEMENT YET",
                        news/social/derivatives/on-chain/smart-money/reputation
                        have NO licensed data yet → coming_soon)

Effective state (what the UI may show):
  UNAVAILABLE  — plan does not grant it (locked; upsell)
  COMING_SOON  — plan grants it but backend data is not yet available
  LIMITED      — plan grants a limited tier and backend is ready
  AVAILABLE    — plan grants full access and backend is ready

Authorization is ALWAYS this registry (backend), never frontend view density.
"""
from __future__ import annotations

from backend.nexus_platform.plans import (
    PLAN_ADVANCED, PLAN_ENTERPRISE, PLAN_FREE, PLAN_PRO, PLAN_STARTER,
)

STATE_AVAILABLE = "AVAILABLE"
STATE_LIMITED = "LIMITED"
STATE_COMING_SOON = "COMING_SOON"
STATE_UNAVAILABLE = "UNAVAILABLE"

_F, _L, _N = "full", "limited", None  # plan-grant shorthands

# capability_id -> {"backend": "ready"|"coming_soon", "plans": {plan: grant}}
# "domain" groups capabilities for the data-domain map.
CAPABILITIES: dict[str, dict] = {
    # ---- market (real backend data exists today) ----
    "market_overview":   {"backend": "ready", "domain": "market",
                          "plans": {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "watchlist":         {"backend": "ready", "domain": "personal",
                          "plans": {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "alerts":            {"backend": "ready", "domain": "personal",
                          "plans": {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "history":           {"backend": "ready", "domain": "market",
                          "plans": {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "nex_ai_digest":     {"backend": "ready", "domain": "personal",
                          "plans": {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "multi_chart":       {"backend": "ready", "domain": "personal",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F}},
    "custom_workspace":  {"backend": "ready", "domain": "personal",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F}},
    "advanced_alerts":   {"backend": "ready", "domain": "personal",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F}},

    # ---- news / social intelligence (NO licensed data yet → coming_soon) ----
    "news":              {"backend": "coming_soon", "domain": "news_social",
                          "plans": {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "news_reliability":  {"backend": "coming_soon", "domain": "reputation",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _L, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "social_summary":    {"backend": "coming_soon", "domain": "news_social",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "news_social_intel": {"backend": "coming_soon", "domain": "news_social",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "kol_track_record":  {"backend": "coming_soon", "domain": "reputation",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "historical_reaction": {"backend": "coming_soon", "domain": "historical_reaction",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F}},

    # ---- derivatives (NO licensed data yet → coming_soon) ----
    "oi_funding":        {"backend": "coming_soon", "domain": "derivatives",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _L, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "liquidation":       {"backend": "coming_soon", "domain": "derivatives",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F}},
    "derivatives_full":  {"backend": "coming_soon", "domain": "derivatives",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F}},

    # ---- on-chain / smart money (NO licensed data yet → coming_soon) ----
    "onchain_basic":     {"backend": "coming_soon", "domain": "onchain",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F}},
    "onchain_full":      {"backend": "coming_soon", "domain": "onchain",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F}},
    "smart_money":       {"backend": "coming_soon", "domain": "onchain",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F}},

    # ---- pro tools ----
    "ai_screener":       {"backend": "coming_soon", "domain": "personal",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F}},
    "cross_exchange":    {"backend": "coming_soon", "domain": "market",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F}},
    "export":            {"backend": "coming_soon", "domain": "personal",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F}},
    "api_access":        {"backend": "coming_soon", "domain": "personal",
                          "plans": {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F}},

    # ---- enterprise-only (separate product; org domain) ----
    "org_seats":         {"backend": "coming_soon", "domain": "enterprise",
                          "plans": {PLAN_ENTERPRISE: _F}},
    "shared_intelligence": {"backend": "coming_soon", "domain": "enterprise",
                          "plans": {PLAN_ENTERPRISE: _F}},
    "org_audit":         {"backend": "coming_soon", "domain": "enterprise",
                          "plans": {PLAN_ENTERPRISE: _F}},
    "sso":               {"backend": "coming_soon", "domain": "enterprise",
                          "plans": {PLAN_ENTERPRISE: _F}},
}

# Enterprise inherits all Personal capabilities at full grant (superset product).
for _cid, _spec in CAPABILITIES.items():
    _spec["plans"].setdefault(PLAN_ENTERPRISE, _F if _spec["plans"].get(PLAN_ADVANCED) else _spec["plans"].get(PLAN_ENTERPRISE, _N))


def resolve_state(capability_id: str, plan: str) -> str:
    spec = CAPABILITIES.get(capability_id)
    if spec is None:
        return STATE_UNAVAILABLE
    grant = spec["plans"].get(plan)
    if grant is None:
        return STATE_UNAVAILABLE  # locked for this plan
    if spec["backend"] != "ready":
        return STATE_COMING_SOON  # entitled, but no real backend data yet
    return STATE_LIMITED if grant == "limited" else STATE_AVAILABLE


def capability_matrix(plan: str) -> dict[str, str]:
    """Backend-authoritative capability→state map for a plan (admin-inspectable)."""
    return {cid: resolve_state(cid, plan) for cid in CAPABILITIES}


def is_allowed(capability_id: str, plan: str) -> bool:
    """True only when entitled AND backed by real data (AVAILABLE or LIMITED)."""
    return resolve_state(capability_id, plan) in (STATE_AVAILABLE, STATE_LIMITED)
