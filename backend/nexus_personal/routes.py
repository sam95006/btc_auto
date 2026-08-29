"""Personal Market Intelligence product routes (PERSONAL-1).

Every paid action is gated by Authentication AND Entitlement AND (when metered)
Quota, all enforced on the backend. Reuses the BILLING enforcement helpers and
the existing market/watchlist capabilities. Member-safe only.
"""

from __future__ import annotations

from typing import Any, Optional

from flask import Flask, Response, request

from backend.nexus_billing.entitlements import effective_plan_code, plan_has_entitlement
from backend.nexus_billing.routes import (
    _account_subscription,
    _authenticated_account_id,
    _json_no_store,
    enforce_entitlement,
    enforce_quota,
)
from backend.nexus_billing.usage_policy import quota_limit
from backend.nexus_personal.analysis import (
    AnalysisDataUnavailable,
    analyze_series,
    build_report,
)
from backend.nexus_personal.product_access import (
    PRODUCT_FEATURES,
    QUOTA_KIND_CAPACITY,
    QUOTA_KIND_CONSUMABLE,
)
from backend.nexus_personal.watchlist_repository import PersonalWatchlistRepository

MARKET_SOURCE_CONFIG_KEY = "NEXUS_PERSONAL_MARKET_SOURCE"
WATCHLIST_REPO_CONFIG_KEY = "NEXUS_PERSONAL_WATCHLIST_REPO"


def _services(app: Flask) -> dict[str, Any]:
    return dict(app.config.get("NEXUS_PRODUCT_ALPHA_SERVICES") or {})


def _effective_plan(app: Flask, account_id: str) -> str:
    return effective_plan_code(_account_subscription(app, account_id))


def _market_series(app: Flask, symbol: str) -> Optional[list[float]]:
    source = app.config.get(MARKET_SOURCE_CONFIG_KEY)
    if not callable(source):
        return None
    try:
        series = source(symbol)
    except Exception:  # noqa: BLE001 - treat any source error as unavailable
        return None
    return list(series) if series else None


def _watchlist_repo(app: Flask) -> Optional[PersonalWatchlistRepository]:
    repo = app.config.get(WATCHLIST_REPO_CONFIG_KEY)
    if repo is not None:
        return repo
    pool = _services(app).get("pool")
    if pool is None:
        return None
    repo = PersonalWatchlistRepository(pool)
    app.config[WATCHLIST_REPO_CONFIG_KEY] = repo
    return repo


def register_personal_routes(app: Flask) -> None:
    # ----- product access matrix (member-safe) -----
    @app.get("/api/v1/personal/features")
    def personal_features():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        plan = _effective_plan(app, account_id)
        features = []
        for feature in PRODUCT_FEATURES.values():
            entitled = plan_has_entitlement(plan, feature.entitlement)
            features.append(
                {
                    "key": feature.key,
                    "label": feature.label,
                    "entitlement": feature.entitlement,
                    "entitled": entitled,
                    "available": feature.available,
                    "locked": (not entitled) and feature.available,
                    "quota_kind": feature.quota_kind,
                    "quota_code": feature.quota_code,
                }
            )
        return _json_no_store({"effective_plan_code": plan, "features": features})

    # ----- metered: advanced analysis -----
    @app.post("/api/v1/personal/analysis")
    def personal_analysis():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "advanced_analysis")
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        symbol = str(body.get("symbol") or "").strip().upper()
        idem = str(body.get("idempotency_key") or "").strip()
        if not symbol:
            return _json_no_store({"error": "symbol_required", "classification": "BAD_REQUEST"}, 400)
        if not idem:
            return _json_no_store({"error": "missing_idempotency_key", "classification": "BAD_REQUEST"}, 400)
        try:
            analysis = analyze_series(symbol, _market_series(app, symbol))
        except AnalysisDataUnavailable:
            # No market data -> unavailable; never fabricate, never consume quota.
            return _json_no_store({"error": "market_data_unavailable", "classification": "UNAVAILABLE"}, 503)
        err, decision = enforce_quota(app, account_id, "advanced_analysis_requests_daily", idempotency_key=idem)
        if err is not None:
            return err
        assert decision is not None
        return _json_no_store({"ok": True, "analysis": analysis, "remaining": decision.remaining})

    # ----- metered: report generation -----
    @app.post("/api/v1/personal/report")
    def personal_report():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "report_generation")
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        symbol = str(body.get("symbol") or "").strip().upper()
        idem = str(body.get("idempotency_key") or "").strip()
        if not symbol:
            return _json_no_store({"error": "symbol_required", "classification": "BAD_REQUEST"}, 400)
        if not idem:
            return _json_no_store({"error": "missing_idempotency_key", "classification": "BAD_REQUEST"}, 400)
        try:
            analysis = analyze_series(symbol, _market_series(app, symbol))
        except AnalysisDataUnavailable:
            return _json_no_store({"error": "market_data_unavailable", "classification": "UNAVAILABLE"}, 503)
        err, decision = enforce_quota(app, account_id, "report_generation_monthly", idempotency_key=idem)
        if err is not None:
            return err
        assert decision is not None
        report = build_report(symbol, analysis)
        return _json_no_store({"ok": True, "report": report, "remaining": decision.remaining})

    # ----- watchlist (capacity quota; own account only) -----
    @app.get("/api/v1/personal/watchlist")
    def personal_watchlist_get():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "watchlists")
        if denied is not None:
            return denied
        repo = _watchlist_repo(app)
        if repo is None:
            return _json_no_store({"error": "watchlist_unavailable", "classification": "UNAVAILABLE"}, 503)
        plan = _effective_plan(app, account_id)
        limit = quota_limit(plan, "watchlist_items") or 0
        symbols = repo.list_symbols(account_id)
        return _json_no_store({"symbols": symbols, "used": len(symbols), "capacity": limit})

    @app.post("/api/v1/personal/watchlist")
    def personal_watchlist_add():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "watchlists")
        if denied is not None:
            return denied
        repo = _watchlist_repo(app)
        if repo is None:
            return _json_no_store({"error": "watchlist_unavailable", "classification": "UNAVAILABLE"}, 503)
        body = request.get_json(silent=True) or {}
        symbol = str(body.get("symbol") or "").strip().upper()
        if not symbol:
            return _json_no_store({"error": "symbol_required", "classification": "BAD_REQUEST"}, 400)
        plan = _effective_plan(app, account_id)
        limit = quota_limit(plan, "watchlist_items") or 0
        if repo.contains(account_id, symbol):
            return _json_no_store({"ok": True, "symbols": repo.list_symbols(account_id), "capacity": limit})
        if repo.count(account_id) + 1 > limit:
            # Capacity limit is NOT a consumable 429; use a distinct product limit.
            return _json_no_store(
                {"error": "watchlist_capacity_reached", "classification": "CAPACITY_LIMIT_EXCEEDED", "capacity": limit},
                409,
            )
        repo.add_symbol(account_id, symbol)
        symbols = repo.list_symbols(account_id)
        return _json_no_store({"ok": True, "symbols": symbols, "used": len(symbols), "capacity": limit})

    @app.delete("/api/v1/personal/watchlist/<symbol>")
    def personal_watchlist_remove(symbol: str):
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "watchlists")
        if denied is not None:
            return denied
        repo = _watchlist_repo(app)
        if repo is None:
            return _json_no_store({"error": "watchlist_unavailable", "classification": "UNAVAILABLE"}, 503)
        repo.remove_symbol(account_id, str(symbol))
        return _json_no_store({"ok": True, "symbols": repo.list_symbols(account_id)})

    # ----- history range clamp by plan (capacity policy) -----
    @app.get("/api/v1/personal/history")
    def personal_history():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "extended_market_history")
        if denied is not None:
            return denied
        plan = _effective_plan(app, account_id)
        max_days = quota_limit(plan, "history_days") or 0
        try:
            requested = int(request.args.get("days", str(max_days)))
        except ValueError:
            return _json_no_store({"error": "invalid_days", "classification": "BAD_REQUEST"}, 400)
        requested = max(0, requested)
        # Backend clamps; the client cannot exceed the plan policy.
        effective = min(requested, max_days)
        return _json_no_store(
            {"symbol": str(request.args.get("symbol") or "").upper(), "requested_days": requested,
             "effective_days": effective, "clamped": requested > max_days, "max_days": max_days}
        )

    # ----- signals / risk (entitlement-gated, member-safe, sanitized) -----
    @app.get("/api/v1/personal/signals")
    def personal_signals():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "advanced_signals")
        if denied is not None:
            return denied
        # Member-safe: no live member signal backend yet -> explicit unavailable,
        # never fabricated. The DTO carries no trading execution fields.
        return _json_no_store(
            {"data_class": "MEMBER_SAFE_SIGNALS", "available": False, "reason": "signal_backend_unavailable", "signals": []}
        )

    @app.get("/api/v1/personal/risk")
    def personal_risk():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "risk_intelligence")
        if denied is not None:
            return denied
        # Read-only market risk information only. Explicitly NOT Risk Guard /
        # position sizing / routing / ARM. Unavailable until a real backend lands.
        return _json_no_store(
            {"data_class": "MEMBER_SAFE_RISK", "available": False, "reason": "risk_backend_unavailable", "risk": []}
        )
