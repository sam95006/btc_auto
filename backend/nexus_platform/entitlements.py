"""Entitlement capability registry (NEXUS-EXPERIENCE-1A / hardened in 1A.1).

FOUR independent dimensions are modelled so a capability is never called READY
just because some frontend code exists:

  * plan grant   — does the plan entitle it?           full | limited | none
  * backend_state — is a real backend service present?  ready | partial | absent
  * product_state — is the end-to-end feature built?    available | beta | partial | coming_soon
  * data_state    — is the underlying data legally usable? (derived from the
                    data-licensing registry: licensed | unlicensed)

Effective UI state (backend-authoritative), most-restrictive wins:
  UNAVAILABLE  — plan does not grant it (locked; upsell)
  COMING_SOON  — data unlicensed, or product not built, or no backend service
  PARTIAL      — real backend exists but the product is only partially built
  BETA         — built but explicitly beta
  LIMITED      — full path works but the plan grants a limited tier
  AVAILABLE    — entitled, backend ready, product built, data licensed

Plan AUTHORIZATION and product READINESS are separate dimensions. Enterprise is a
SEPARATE PRODUCT — it does NOT inherit Personal capabilities; grants are explicit.
"""
from __future__ import annotations

from backend.nexus_platform.data_licenses import can_use_for_derived_intelligence
from backend.nexus_platform.plans import (
    PLAN_ADVANCED, PLAN_ENTERPRISE, PLAN_FREE, PLAN_PRO, PLAN_STARTER,
)

STATE_AVAILABLE = "AVAILABLE"
STATE_LIMITED = "LIMITED"
STATE_BETA = "BETA"
STATE_PARTIAL = "PARTIAL"
STATE_COMING_SOON = "COMING_SOON"
STATE_UNAVAILABLE = "UNAVAILABLE"

_F, _L, _N = "full", "limited", None  # plan-grant shorthands

# Datasets (from data_licenses) that back each capability's data_state.
DS_MARKET = "usdm_public_ticker_ohlcv"
DS_DERIVATIVES = "oi_funding_liquidation"
DS_ONCHAIN = "onchain_flows_metrics"
DS_SMART = "entity_wallet_intelligence"
DS_SOCIAL = "creator_social_sentiment"
DS_NEWS = "market_news_feed"


def _cap(domain, grants, backend, product, dataset, evidence=""):
    return {"domain": domain, "plans": grants, "backend_state": backend,
            "product_state": product, "dataset": dataset, "evidence": evidence}


# Audited against real routes/services (see 1A.1). product_state reflects what is
# genuinely built end-to-end today — NOT merely that frontend code exists.
CAPABILITIES: dict[str, dict] = {
    # ---- market-derived, licensed data, genuinely built today ----
    "market_overview": _cap("market", {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                            "ready", "available", DS_MARKET,
                            "GET /api/v1/personal/{analysis,risk,signals} on real market adapter"),
    "watchlist": _cap("personal", {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                      "ready", "available", DS_MARKET,
                      "GET/POST /api/v1/personal/watchlist + watchlist_repository + migration 0014"),
    "history": _cap("market", {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                    "ready", "available", DS_MARKET,
                    "GET /api/v1/personal/history (bounded public market history)"),
    # ---- market-derived but only partially built ----
    "alerts": _cap("personal", {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                   "partial", "partial", DS_MARKET,
                   "alert engine contract + retention alert_events exist; no member alert-delivery route yet"),
    "nex_ai_digest": _cap("personal", {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                          "partial", "partial", DS_MARKET,
                          "deterministic brief primitive exists (corporate intelligence); Personal wiring pending"),
    # ---- pro view/tools not built yet ----
    "multi_chart": _cap("personal", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F},
                        "absent", "coming_soon", None, "multi-chart workspace not built"),
    "custom_workspace": _cap("personal", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F},
                             "absent", "coming_soon", None, "saved-layout workspace not built"),
    "advanced_alerts": _cap("personal", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                            "absent", "coming_soon", None, "multi-condition rule builder not built"),
    "ai_screener": _cap("personal", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                        "absent", "coming_soon", None, "screener not built"),
    "export": _cap("personal", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F},
                   "absent", "coming_soon", None, "export not built"),
    "api_access": _cap("personal", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F},
                       "absent", "coming_soon", None, "public API not implemented"),
    "cross_exchange": _cap("market", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F},
                           "absent", "coming_soon", DS_MARKET, "cross-exchange compare not built"),

    # ---- news / social (UNLICENSED data -> COMING_SOON regardless) ----
    "news": _cap("news_social", {PLAN_FREE: _L, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                 "absent", "coming_soon", DS_NEWS, "no licensed news feed"),
    "news_reliability": _cap("reputation", {PLAN_FREE: _N, PLAN_STARTER: _L, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                             "absent", "coming_soon", DS_NEWS, "no licensed reputation data"),
    "social_summary": _cap("news_social", {PLAN_FREE: _N, PLAN_STARTER: _F, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                           "absent", "coming_soon", DS_SOCIAL, "no licensed social data"),
    "news_social_intel": _cap("news_social", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                              "absent", "coming_soon", DS_SOCIAL, "no licensed social data"),
    "kol_track_record": _cap("reputation", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                             "absent", "coming_soon", DS_SOCIAL, "no licensed creator data"),
    "historical_reaction": _cap("historical_reaction", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                                "absent", "coming_soon", DS_NEWS, "no licensed event data"),

    # ---- derivatives / on-chain (UNLICENSED data -> COMING_SOON) ----
    "oi_funding": _cap("derivatives", {PLAN_FREE: _N, PLAN_STARTER: _L, PLAN_PRO: _F, PLAN_ADVANCED: _F},
                       "absent", "coming_soon", DS_DERIVATIVES, "no licensed derivatives data"),
    "liquidation": _cap("derivatives", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F},
                        "absent", "coming_soon", DS_DERIVATIVES, "no licensed derivatives data"),
    "derivatives_full": _cap("derivatives", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F},
                             "absent", "coming_soon", DS_DERIVATIVES, "no licensed derivatives data"),
    "onchain_basic": _cap("onchain", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F},
                          "absent", "coming_soon", DS_ONCHAIN, "no licensed on-chain data"),
    "onchain_full": _cap("onchain", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _N, PLAN_ADVANCED: _F},
                         "absent", "coming_soon", DS_ONCHAIN, "no licensed on-chain data"),
    "smart_money": _cap("onchain", {PLAN_FREE: _N, PLAN_STARTER: _N, PLAN_PRO: _L, PLAN_ADVANCED: _F},
                        "absent", "coming_soon", DS_SMART, "no licensed smart-money data"),

    # ---- ENTERPRISE product — EXPLICIT grants only (NOT Personal Advanced+) ----
    "org_seats": _cap("enterprise", {PLAN_ENTERPRISE: _F}, "absent", "coming_soon", None, "org/seats not built"),
    "shared_watchlists": _cap("enterprise", {PLAN_ENTERPRISE: _F}, "absent", "coming_soon", None, "shared watchlists not built"),
    "shared_intelligence": _cap("enterprise", {PLAN_ENTERPRISE: _F}, "absent", "coming_soon", None, "shared intelligence not built"),
    "shared_research": _cap("enterprise", {PLAN_ENTERPRISE: _F}, "absent", "coming_soon", None, "shared research not built"),
    "shared_alerts": _cap("enterprise", {PLAN_ENTERPRISE: _F}, "absent", "coming_soon", None, "shared alerts not built"),
    "org_audit": _cap("enterprise", {PLAN_ENTERPRISE: _F}, "absent", "coming_soon", None, "org audit not built"),
    "integrations": _cap("enterprise", {PLAN_ENTERPRISE: _F}, "absent", "coming_soon", None, "integrations not built"),
    "sso": _cap("enterprise", {PLAN_ENTERPRISE: _F}, "absent", "coming_soon", None, "SSO not built"),
}

# Capabilities that make up the Enterprise product (explicit — no inheritance).
ENTERPRISE_CAPABILITIES = tuple(cid for cid, s in CAPABILITIES.items() if s["domain"] == "enterprise")


DATA_LICENSED = "licensed"
DATA_UNLICENSED = "unlicensed"
DATA_NOT_APPLICABLE = "not_applicable"


def data_state_of(dataset: str | None) -> str:
    """A capability with no external dataset (product/account mechanics) is
    NOT_APPLICABLE and is NOT blocked by licensing. External datasets are
    licensed only when the licensing registry permits derived use; unknown/
    unregistered datasets fail closed as unlicensed."""
    if dataset is None:
        return DATA_NOT_APPLICABLE
    return DATA_LICENSED if can_use_for_derived_intelligence(dataset) else DATA_UNLICENSED


def resolve_state(capability_id: str, plan: str) -> str:
    spec = CAPABILITIES.get(capability_id)
    if spec is None:
        return STATE_UNAVAILABLE
    grant = spec["plans"].get(plan)
    if grant is None:
        return STATE_UNAVAILABLE                        # plan does not grant it
    # Only EXTERNAL-data capabilities are gated by licensing. NOT_APPLICABLE
    # (workspace/seats/sso/audit/integrations) depends on grant/backend/product only.
    if data_state_of(spec.get("dataset")) == DATA_UNLICENSED:
        return STATE_COMING_SOON                        # underlying data not licensed
    if spec["product_state"] == "coming_soon" or spec["backend_state"] == "absent":
        return STATE_COMING_SOON
    if spec["product_state"] == "beta":
        return STATE_BETA
    if spec["product_state"] == "partial" or spec["backend_state"] == "partial":
        return STATE_PARTIAL
    return STATE_LIMITED if grant == "limited" else STATE_AVAILABLE


def capability_matrix(plan: str) -> dict[str, str]:
    """Backend-authoritative capability→state map for a plan (admin-inspectable)."""
    return {cid: resolve_state(cid, plan) for cid in CAPABILITIES}


def capability_dimensions(capability_id: str) -> dict:
    """Full four-dimension view (for admin/inspection)."""
    spec = CAPABILITIES.get(capability_id)
    if spec is None:
        return {}
    return {"domain": spec["domain"], "backend_state": spec["backend_state"],
            "product_state": spec["product_state"],
            "data_state": data_state_of(spec.get("dataset")),
            "evidence": spec.get("evidence", "")}


def is_allowed(capability_id: str, plan: str) -> bool:
    """True only when the capability is actually usable today (AVAILABLE/LIMITED/BETA)."""
    return resolve_state(capability_id, plan) in (STATE_AVAILABLE, STATE_LIMITED, STATE_BETA)
