"""Personal Market Intelligence product routes (PERSONAL-1 + PERSONAL-2).

Every paid action is gated by Authentication AND Entitlement AND (when metered)
Quota, all enforced on the backend. PERSONAL-2 binds analysis / report /
history / risk to the REAL member-safe public market services (no second
market backend, no fabricated data) and makes watchlist capacity atomic.

Member-safe only: no trading execution, order routing, ARM, position sizing,
provider secrets, or Founder controls are present or reachable here.
"""

from __future__ import annotations

from typing import Any, Optional

from flask import Flask, request

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
    assess_risk,
    build_report,
)
from backend.nexus_personal.market_adapter import (
    PersonalMarketUnavailable,
    _CallableSeriesAdapter,
    build_personal_market_adapter,
)
from backend.nexus_personal.product_access import PRODUCT_FEATURES
from backend.nexus_personal.watchlist_repository import (
    ADD_CAPACITY,
    ADD_DUPLICATE,
    PersonalWatchlistRepository,
)

MARKET_SOURCE_CONFIG_KEY = "NEXUS_PERSONAL_MARKET_SOURCE"
MARKET_ADAPTER_CONFIG_KEY = "NEXUS_PERSONAL_MARKET_ADAPTER"
WATCHLIST_REPO_CONFIG_KEY = "NEXUS_PERSONAL_WATCHLIST_REPO"

# Provider public OHLCV window ceiling (PublicMarketHistoryService HISTORY_LIMIT_MAX).
PROVIDER_HISTORY_WINDOW_MAX = 120


def _services(app: Flask) -> dict[str, Any]:
    return dict(app.config.get("NEXUS_PRODUCT_ALPHA_SERVICES") or {})


def _effective_plan(app: Flask, account_id: str) -> str:
    return effective_plan_code(_account_subscription(app, account_id))


def _market_adapter(app: Flask):
    """Resolve the Personal market data binding.

    Priority: an explicitly injected adapter (production / tests) →
    a legacy callable market source wrapped as a fixture adapter
    (PERSONAL-1 test contract) → None (→ honest 503, no network, no fabrication).
    """
    adapter = app.config.get(MARKET_ADAPTER_CONFIG_KEY)
    if adapter is not None:
        return adapter
    source = app.config.get(MARKET_SOURCE_CONFIG_KEY)
    if callable(source):
        return _CallableSeriesAdapter(source)
    return None


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

    # ----- member-safe market STATE (regime/risk/symbols) for the Simple Home -----
    @app.get("/api/v1/personal/market-state")
    def personal_market_state():
        # Backend-authoritative regime/risk/volatility from the REAL member-safe
        # public market snapshot (same primitive as Corporate). No fabrication.
        from backend.nexus_corporate.market import build_showcase
        from backend.nexus_product_backend.market_snapshot import build_public_market_snapshot_service

        svc = app.config.get("NEXUS_PERSONAL_MARKET_SNAPSHOT")
        if svc is None:
            try:
                svc = build_public_market_snapshot_service()
            except Exception:  # noqa: BLE001
                svc = None
            app.config["NEXUS_PERSONAL_MARKET_SNAPSHOT"] = svc
        symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        showcase = build_showcase(svc, symbols)
        # Present a canonical source identity only. Strip the engineering provider
        # slug (e.g. "binance_usdm_public") from the Personal contract at every
        # level so no engineering provider name is ever exposed to the member app.
        showcase.pop("source", None)
        showcase["source_label"] = "Exchange market"
        for _sym in showcase.get("symbols") or []:
            if isinstance(_sym, dict):
                _sym.pop("source", None)
        return _json_no_store(showcase)

    # ----- canonical plan + capability catalog (nexus_platform contracts) -----
    @app.get("/api/v1/personal/catalog")
    def personal_catalog():
        from backend.nexus_platform import entitlements as _ent
        from backend.nexus_platform import plans as _plans

        matrices = {p.code: _ent.capability_matrix(p.code) for p in _plans.list_plans()}
        dims = {cid: _ent.capability_dimensions(cid) for cid in _ent.CAPABILITIES}
        return _json_no_store({
            "commercial": _plans.public_catalog(),
            "capabilities": matrices,               # {plan: {capability: STATE}}
            "capability_dimensions": dims,          # 4-dimension audit (admin/inspection)
            "states": ["AVAILABLE", "LIMITED", "BETA", "PARTIAL", "COMING_SOON", "UNAVAILABLE"],
        })

    # ----- metered: advanced analysis (bound to REAL market data) -----
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
        series = _fetch_series(app, symbol)
        if series is None:
            # No real market data -> unavailable; never fabricate, never consume.
            return _json_no_store({"error": "market_data_unavailable", "classification": "UNAVAILABLE"}, 503)
        analysis = analyze_series(symbol, series.closes)
        err, decision = enforce_quota(app, account_id, "advanced_analysis_requests_daily", idempotency_key=idem)
        if err is not None:
            return err
        assert decision is not None
        return _json_no_store(
            {"ok": True, "analysis": analysis, "provenance": series.metadata(), "remaining": decision.remaining}
        )

    # ----- metered: report generation (REAL market evidence) -----
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
        series = _fetch_series(app, symbol)
        if series is None:
            return _json_no_store({"error": "market_data_unavailable", "classification": "UNAVAILABLE"}, 503)
        analysis = analyze_series(symbol, series.closes)
        err, decision = enforce_quota(app, account_id, "report_generation_monthly", idempotency_key=idem)
        if err is not None:
            return err
        assert decision is not None
        report = build_report(symbol, analysis, series.metadata())
        return _json_no_store({"ok": True, "report": report, "remaining": decision.remaining})

    # ----- watchlist (atomic capacity; own account only) -----
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
        # Atomic check-then-insert: concurrent adds cannot exceed capacity.
        outcome = repo.try_add_symbol(account_id, symbol, limit)
        if outcome == ADD_CAPACITY:
            return _json_no_store(
                {"error": "watchlist_capacity_reached", "classification": "CAPACITY_LIMIT_EXCEEDED", "capacity": limit},
                409,
            )
        # ADD_OK and ADD_DUPLICATE are both idempotent successes.
        symbols = repo.list_symbols(account_id)
        return _json_no_store(
            {"ok": True, "symbols": symbols, "used": len(symbols), "capacity": limit,
             "duplicate": outcome == ADD_DUPLICATE}
        )

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

    # ----- history: plan-clamped, REAL bounded market data -----
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
        symbol = str(request.args.get("symbol") or "BTCUSDT").upper()
        try:
            requested = int(request.args.get("days", str(max_days)))
        except ValueError:
            return _json_no_store({"error": "invalid_days", "classification": "BAD_REQUEST"}, 400)
        requested = max(1, requested)
        # Backend clamps to plan policy; the client cannot exceed it.
        effective = min(requested, max_days)
        if effective <= 0:
            return _json_no_store(
                {"error": "history_not_available_for_plan", "classification": "BAD_REQUEST", "max_days": max_days}, 400
            )
        adapter = _market_adapter(app)
        if adapter is None:
            return _json_no_store({"error": "market_data_unavailable", "classification": "UNAVAILABLE"}, 503)
        window = min(effective, PROVIDER_HISTORY_WINDOW_MAX)
        payload, status = adapter.fetch_history(symbol, interval="1d", limit=max(1, window))
        if status != 200:
            return _json_no_store({"error": "market_data_unavailable", "classification": "UNAVAILABLE"}, 503)
        candles = payload.get("candles") if isinstance(payload, dict) else None
        # Trim to the effective window so returned data never exceeds the plan.
        data = (candles or [])[-window:]
        return _json_no_store(
            {
                "symbol": symbol,
                "requested_days": requested,
                "effective_days": effective,
                "clamped": requested > max_days,
                "max_days": max_days,
                "provider_window_max": PROVIDER_HISTORY_WINDOW_MAX,
                "data_points": len(data),
                "data": data,
                "freshness": payload.get("freshness"),
                "provider": payload.get("provider"),
                "source_class": payload.get("data_class"),
            }
        )

    # ----- signals: member-safe; no safe signal source exists -> unavailable -----
    @app.get("/api/v1/personal/signals")
    def personal_signals():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "advanced_signals")
        if denied is not None:
            return denied
        # Audit result: every existing signal/decision output is private trading
        # (entry/route/size/ARM). None is member-safe, so we return an explicit
        # unavailable state rather than fabricate or leak private internals.
        return _json_no_store(
            {"data_class": "MEMBER_SAFE_SIGNALS", "available": False, "reason": "no_member_safe_signal_source", "signals": []}
        )

    # ----- risk: member-safe market-risk from REAL public volatility -----
    @app.get("/api/v1/personal/risk")
    def personal_risk():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = enforce_entitlement(app, "risk_intelligence")
        if denied is not None:
            return denied
        symbol = str(request.args.get("symbol") or "BTCUSDT").upper()
        series = _fetch_series(app, symbol)
        if series is None:
            return _json_no_store({"error": "market_data_unavailable", "classification": "UNAVAILABLE"}, 503)
        analysis = analyze_series(symbol, series.closes)
        risk = assess_risk(analysis)
        # Read-only market risk only. Explicitly NOT Risk Guard / position sizing
        # / routing / ARM / leverage authority / private trade state.
        return _json_no_store({"data_class": "MEMBER_SAFE_RISK", "available": True, "risk": risk,
                               "provenance": series.metadata()})

    # ----- closed-beta health contract -----
    @app.get("/api/v1/personal/closed-beta-health")
    def personal_closed_beta_health():
        from backend.nexus_personal.health import closed_beta_health

        payload, status = closed_beta_health(app)
        return _json_no_store(payload, status)


def _fetch_series(app: Flask, symbol: str):
    """Return a real member-safe PersonalMarketSeries or None (unavailable)."""
    adapter = _market_adapter(app)
    if adapter is None:
        return None
    try:
        return adapter.fetch_series(symbol)
    except (PersonalMarketUnavailable, AnalysisDataUnavailable):
        return None
