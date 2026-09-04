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

from backend.nexus_billing.entitlements import (
    effective_plan_code,
    plan_has_entitlement,
    resolve_entitlements_for_plan,
)
from backend.nexus_billing.routes import (
    _account_subscription,
    _authenticated_account_id,
    _json_no_store,
    _services as _billing_services,
    _session_id,
    _usage_service,
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
    """The canonical trial-aware effective Personal plan (paid wins, then active
    Starter trial, else free), used for features + quota/capacity policy. Kept
    identical to the plan reported by /personal/subscription and enforced by the
    entitlement/quota gates so the member is never shown one plan and gated at
    another."""
    from backend.nexus_platform.personal_access import effective_personal_plan

    identity = _authenticated_identity(app)
    registered_at = identity.get("created_at") if identity else None
    return effective_personal_plan(
        registered_at=registered_at, subscription=_account_subscription(app, account_id)
    )


def _personal_entitlements(app: Flask, account_id: str):
    """Entitlements resolved from the canonical Personal effective plan (trial-
    aware). This is the PERSONAL access path — distinct from the generic billing
    entitlement resolver, which stays billing-subscription authoritative."""
    return resolve_entitlements_for_plan(_effective_plan(app, account_id))


def _enforce_personal_entitlement(app: Flask, account_id: str, feature_code: str):
    """Personal entitlement gate: deny (403) unless the canonical Personal
    effective plan holds the feature. Callers have already resolved account_id."""
    if not _personal_entitlements(app, account_id).has(feature_code):
        return _json_no_store(
            {"error": "entitlement_required", "classification": "ENTITLEMENT_REQUIRED",
             "required_feature": feature_code},
            403,
        )
    return None


def _authenticated_identity(app: Flask) -> Optional[dict[str, Any]]:
    """Full authenticated session identity (includes the account registration
    timestamp `created_at` from nexus.accounts). The account is ALWAYS resolved
    from the server session — account_id / registration time are never accepted
    from browser input."""
    auth = _billing_services(app).get("auth")
    session_id = _session_id()
    if not auth or not session_id:
        return None
    return auth.resolve_session(session_id) or None


def _parse_iso_utc(value: Any) -> Optional[Any]:
    """Parse an ISO-8601 timestamp to a tz-aware UTC datetime; None if unparseable."""
    from datetime import datetime, timezone

    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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

    # ----- member subscription + honest Starter-trial status (no fabrication) -----
    @app.get("/api/v1/personal/subscription")
    def personal_subscription():
        from backend.nexus_platform import plans as _plans
        from backend.nexus_platform import personal_access as _pa

        identity = _authenticated_identity(app)
        account_id = identity.get("account_id") if identity else None
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)

        sub = _account_subscription(app, account_id)
        # Single source of truth: the canonical Personal access module resolves the
        # paid Personal plan (live, allowlisted, NEVER Enterprise) and the trial
        # status from the ACCOUNT registration timestamp (accounts.created_at via
        # the authenticated identity) — not subscription.created_at / now / any
        # browser value. When registration cannot be resolved AND there is no paid
        # plan the public contract reports UNAVAILABLE rather than a fabricated
        # trial/free.
        paid_plan = _pa.personal_paid_plan(sub)
        registered_at = _parse_iso_utc(identity.get("created_at"))
        if registered_at is not None:
            status = _pa.personal_trial_status(registered_at=registered_at, subscription=sub)
            effective = _pa.effective_personal_plan(registered_at=registered_at, subscription=sub)
        elif paid_plan:
            status = {"state": "PAID", "plan": paid_plan, "trial_active": False}
            effective = paid_plan
        else:
            status = {"state": "UNAVAILABLE", "trial_active": False}
            effective = effective_plan_code(sub)

        catalog = _plans.public_catalog()
        return _json_no_store({
            "effective_plan": effective,
            "trial": status,
            "trial_contract": catalog["trial"],   # generic contract (always safe to show)
            "currency": catalog["currency"],
        })

    # ----- Personal product ACCESS truth (trial-aware) for the member UI -----
    @app.get("/api/v1/personal/access")
    def personal_access_view():
        """Member-safe Personal ACCESS contract: the trial-aware effective plan,
        its entitlements, and quota/capacity limits — the source the membership
        page uses for entitlement/quota display. Raw payment status is exposed as
        a SEPARATE `billing_status` field; this endpoint never mints a paid row.
        Distinct from the generic /billing endpoints, which stay billing-only."""
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        plan = _effective_plan(app, account_id)
        resolution = resolve_entitlements_for_plan(plan)
        sub = _account_subscription(app, account_id)
        billing_status = getattr(sub, "status", "inactive") if sub is not None else "inactive"
        # Plan / entitlement / billing truth NEVER depends on usage-ledger health.
        payload = {
            "effective_plan_code": plan,
            "entitlements": resolution.feature_codes,
            "billing_status": billing_status,   # raw payment truth, kept separate
            "usage_available": False,
            "quotas": None,                     # explicit: not "no quotas", but "unknown"
        }
        # Usage/quota is best-effort and reported with explicit availability. A
        # missing usage service or a ledger read error must NOT 500 the endpoint,
        # fabricate empty quotas, or downgrade the plan.
        svc = _usage_service(app)
        if svc is not None:
            try:
                payload["quotas"] = svc.resolve_usage(account_id, effective_plan=plan)["quotas"]
                payload["usage_available"] = True
            except Exception:  # noqa: BLE001 - usage outage -> explicitly unavailable
                payload["quotas"] = None
                payload["usage_available"] = False
        return _json_no_store(payload)

    # ----- metered: advanced analysis (bound to REAL market data) -----
    @app.post("/api/v1/personal/analysis")
    def personal_analysis():
        account_id = _authenticated_account_id(app)
        if not account_id:
            return _json_no_store({"error": "session_unavailable", "classification": "AUTH_REQUIRED"}, 401)
        denied = _enforce_personal_entitlement(app, account_id, "advanced_analysis")
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
        err, decision = enforce_quota(
            app, account_id, "advanced_analysis_requests_daily", idempotency_key=idem,
            effective_plan=_effective_plan(app, account_id),
        )
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
        denied = _enforce_personal_entitlement(app, account_id, "report_generation")
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
        err, decision = enforce_quota(
            app, account_id, "report_generation_monthly", idempotency_key=idem,
            effective_plan=_effective_plan(app, account_id),
        )
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
        denied = _enforce_personal_entitlement(app, account_id, "watchlists")
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
        denied = _enforce_personal_entitlement(app, account_id, "watchlists")
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
        denied = _enforce_personal_entitlement(app, account_id, "watchlists")
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
        denied = _enforce_personal_entitlement(app, account_id, "extended_market_history")
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
        denied = _enforce_personal_entitlement(app, account_id, "advanced_signals")
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
        denied = _enforce_personal_entitlement(app, account_id, "risk_intelligence")
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
