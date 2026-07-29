"""Read-only Wave 5 real public shadow API routes."""
from __future__ import annotations

from typing import Any, Callable

from backend.nexus_adaptive_policy import FIXED_LEVERAGE, MAX_MARGIN, MIN_MARGIN, TARGET_NET_OOS_WIN_RATE
from backend.nexus_adaptive_policy.constitution import LeverageConstitution
from backend.nexus_adaptive_policy.metrics import TargetStatus
from backend.nexus_real_shadow import MAX_OPEN, MAX_PENDING, PUBLIC_MARKET_DATA_ONLY, SHADOW_LABELS
from backend.nexus_real_shadow.orchestration import NexusRealPublicShadowRuntime
from backend.nexus_real_shadow.workers import Wave5WorkerHealthRegistry

READ_ONLY_META = {
    "read_only": True,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "mode": "SHADOW",
    "public_market_data_only": PUBLIC_MARKET_DATA_ONLY,
    "labels": list(SHADOW_LABELS),
}

EMPTY_FUNNEL = {
    "marketsScanned": 0,
    "marketsEligible": 0,
    "candidatesGenerated": 0,
    "sixRoleReviewed": 0,
    "riskCriticPassed": 0,
    "riskCriticBlocked": 0,
    "portfolioSelected": 0,
    "openShadowPositions": 0,
}


def _wrap(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    labels = list(payload.get("labels") or [])
    for label in READ_ONLY_META["labels"]:
        if label not in labels:
            labels.append(label)
    payload["labels"] = labels
    return {**READ_ONLY_META, **payload}


def _empty_meta() -> dict[str, Any]:
    return {
        "data_status": "NO_DATA",
        "data_source": "NONE",
        "dataSource": "NONE",
        "freshness": "UNAVAILABLE",
        "providerStatus": "NOT_CONNECTED",
    }


class RealShadowApiState:
    """Backing store populated by NexusRealPublicShadowRuntime."""

    def __init__(self) -> None:
        self.runtime: NexusRealPublicShadowRuntime | None = None
        self.workers = Wave5WorkerHealthRegistry()
        self.workers.ensure_all_types_registered()
        self.universe_snapshots: list[dict[str, Any]] = []
        self.markets: dict[str, dict[str, Any]] = {}
        self.candidates: dict[str, dict[str, Any]] = {}
        self.reviews: dict[str, dict[str, Any]] = {}
        self.portfolio: list[dict[str, Any]] = []
        self.positions: dict[str, dict[str, Any]] = {}
        self.outcomes: list[dict[str, Any]] = []
        self.reflections: list[dict[str, Any]] = []
        self.learning_counts: dict[str, int] = {}

    def sync_from_cycle(self, cycle: dict[str, Any]) -> None:
        uni = cycle.get("universe") or {}
        if uni:
            self.universe_snapshots.append(uni)
        self.markets = {}
        for sym in (cycle.get("tier_scan") or {}).get("tier3_symbols") or []:
            self.markets[sym] = {"symbol": sym, "status": "OK", "labels": list(SHADOW_LABELS)}
        bind_wave5_cycle_to_shadow_api(cycle)


def bind_wave5_cycle_to_shadow_api(cycle: dict[str, Any]) -> None:
    """Push Wave5 runtime cycle into Wave2 shadow API state (no fixture defaults)."""
    try:
        from backend.nexus_global_shadow.api_routes import get_shadow_api_state

        st = get_shadow_api_state()
        st.explicit_fixture_mode = False
        uni = cycle.get("universe") or {}
        if uni:
            if not st.universe_snapshots or st.universe_snapshots[-1].get("universe_snapshot_id") != uni.get(
                "universe_snapshot_id"
            ):
                st.universe_snapshots.append(uni)
        st.scoreboard.update_funnel(
            scanned=int(cycle.get("markets_scanned") or 0),
            eligible=int(cycle.get("markets_eligible") or 0),
            excluded=max(0, int(cycle.get("markets_scanned") or 0) - int(cycle.get("markets_eligible") or 0)),
            candidates=int(cycle.get("candidate_count") or 0),
            reviewed=int(cycle.get("six_role_reviewed") or 0),
            risk_pass=int(cycle.get("portfolio_selected") or 0),
            risk_block=max(0, int(cycle.get("candidate_count") or 0) - int(cycle.get("portfolio_selected") or 0)),
            selected=int(cycle.get("portfolio_selected") or 0),
        )
        st.scoreboard._data["open_shadow_positions"] = int(cycle.get("open_positions") or 0)
        st.scoreboard._data["data_freshness"] = uni.get("freshness") or "UNKNOWN"
        for sym in (cycle.get("tier_scan") or {}).get("tier3_symbols") or []:
            st.markets[sym] = {
                "symbol": sym,
                "status": "OK",
                "labels": list(SHADOW_LABELS),
                "data_source": "REAL_PUBLIC_SHADOW_RUNTIME",
            }
    except Exception:
        pass


_STATE: RealShadowApiState | None = None


def get_real_shadow_api_state() -> RealShadowApiState:
    global _STATE
    if _STATE is None:
        _STATE = RealShadowApiState()
    return _STATE


def reset_real_shadow_api_state() -> None:
    global _STATE
    _STATE = RealShadowApiState()


def get_or_create_runtime() -> NexusRealPublicShadowRuntime:
    st = get_real_shadow_api_state()
    if st.runtime is None:
        st.runtime = NexusRealPublicShadowRuntime()
    return st.runtime


def handle_runtime_status(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    runtime = st.runtime
    cycle = runtime.last_cycle if runtime else None
    if not cycle:
        return _wrap(
            {
                "funnel": dict(EMPTY_FUNNEL),
                "fixed_leverage": FIXED_LEVERAGE,
                "max_open": MAX_OPEN,
                "max_pending": MAX_PENDING,
                "block_new_entries": False,
                **_empty_meta(),
            }
        )
    funnel = {
        "marketsScanned": cycle.get("markets_scanned", 0),
        "marketsEligible": cycle.get("markets_eligible", 0),
        "candidatesGenerated": cycle.get("candidate_count", 0),
        "sixRoleReviewed": cycle.get("six_role_reviewed", 0),
        "riskCriticPassed": cycle.get("portfolio_selected", 0),
        "riskCriticBlocked": max(0, cycle.get("candidate_count", 0) - cycle.get("portfolio_selected", 0)),
        "portfolioSelected": cycle.get("portfolio_selected", 0),
        "openShadowPositions": cycle.get("open_positions", 0),
    }
    return _wrap(
        {
            "funnel": funnel,
            "correlation_id": cycle.get("correlation_id"),
            "fixed_leverage": FIXED_LEVERAGE,
            "max_open": MAX_OPEN,
            "max_pending": MAX_PENDING,
            "block_new_entries": cycle.get("blocked", False),
            "data_status": "OK",
            "data_source": "REAL_PUBLIC_SHADOW_RUNTIME",
            "dataSource": "REAL_PUBLIC_SHADOW_RUNTIME",
            "freshness": (cycle.get("universe") or {}).get("freshness", "FRESH"),
            "providerStatus": cycle.get("provider_status", "OK"),
        }
    )


def handle_runtime_workers(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    workers = st.runtime.workers if st.runtime else st.workers
    return _wrap(
        {
            "workers": workers.snapshot(),
            "block_new_entries": workers.block_new_entries(),
            "data_status": "OK",
            "data_source": "WAVE5_WORKER_REGISTRY",
        }
    )


def handle_universe_latest(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    latest = st.universe_snapshots[-1] if st.universe_snapshots else {}
    if latest:
        return _wrap(
            {
                "totalMarkets": latest.get("total_markets", 0),
                "eligibleMarkets": latest.get("eligible_markets", 0),
                "excludedMarkets": latest.get("excluded_markets", 0),
                "exclusionReasonCounts": {},
                "capturedAt": latest.get("captured_at"),
                "freshness": latest.get("freshness", "UNKNOWN"),
                "providerStatus": latest.get("provider_status", "UNKNOWN"),
                "snapshotId": latest.get("universe_snapshot_id"),
                "data_status": "OK",
                "data_source": "REAL_PUBLIC_SHADOW_RUNTIME",
            }
        )
    return _wrap(
        {
            "totalMarkets": 0,
            "eligibleMarkets": 0,
            "excludedMarkets": 0,
            "exclusionReasonCounts": {},
            "capturedAt": None,
            "freshness": "UNAVAILABLE",
            "providerStatus": "NOT_CONNECTED",
            "snapshotId": None,
            **_empty_meta(),
        }
    )


def handle_markets(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    markets = list(st.markets.values())
    meta = {"data_status": "OK", "data_source": "REAL_PUBLIC_SHADOW_RUNTIME"} if markets else _empty_meta()
    return _wrap({"markets": markets, "count": len(markets), **meta})


def handle_candidates(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    candidates = list(st.candidates.values())
    meta = {"data_status": "OK", "data_source": "REAL_PUBLIC_SHADOW_RUNTIME"} if candidates else _empty_meta()
    return _wrap({"candidates": candidates, "count": len(candidates), **meta})


def handle_reviews(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    reviews = list(st.reviews.values())
    meta = {"data_status": "OK", "data_source": "REAL_PUBLIC_SHADOW_RUNTIME"} if reviews else _empty_meta()
    return _wrap({"reviews": reviews, "count": len(reviews), **meta})


def handle_portfolio(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    portfolio = list(st.portfolio)
    meta = {"data_status": "OK", "data_source": "REAL_PUBLIC_SHADOW_RUNTIME"} if portfolio else _empty_meta()
    return _wrap({"portfolio": portfolio, "maxOpenPositions": MAX_OPEN, "count": len(portfolio), **meta})


def handle_portfolio_overview(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    positions = list(st.positions.values())
    open_positions = [p for p in positions if p.get("state") == "SHADOW_OPEN"]
    meta = {"data_status": "OK", "data_source": "REAL_PUBLIC_SHADOW_RUNTIME"} if positions else _empty_meta()
    return _wrap(
        {
            "ok": True,
            "positions": open_positions,
            "openCount": len(open_positions),
            "maxOpen": MAX_OPEN,
            "leverageFixed": FIXED_LEVERAGE,
            "mode": "SHADOW_READ_ONLY",
            **meta,
        }
    )


def handle_positions(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    positions = list(st.positions.values())
    meta = {"data_status": "OK", "data_source": "REAL_PUBLIC_SHADOW_RUNTIME"} if positions else _empty_meta()
    return _wrap(
        {
            "positions": positions,
            "maxOpenPositions": MAX_OPEN,
            "openCount": len([p for p in positions if p.get("state") == "SHADOW_OPEN"]),
            "count": len(positions),
            **meta,
        }
    )


def handle_outcomes(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    outcomes = list(st.outcomes)
    meta = {"data_status": "OK", "data_source": "REAL_PUBLIC_SHADOW_RUNTIME"} if outcomes else _empty_meta()
    return _wrap({"outcomes": outcomes, "count": len(outcomes), **meta})


def handle_reflections(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    reflections = list(st.reflections)
    meta = {"data_status": "OK", "data_source": "REAL_PUBLIC_SHADOW_RUNTIME"} if reflections else _empty_meta()
    return _wrap({"reflections": reflections, "count": len(reflections), **meta})


def handle_learning_overview(state: RealShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_real_shadow_api_state()
    constitution = LeverageConstitution().to_dict()
    counts = st.learning_counts or {}
    has_data = any(counts.values())
    meta = {"data_status": "OK", "data_source": "REAL_PUBLIC_SHADOW_RUNTIME"} if has_data else _empty_meta()
    return _wrap(
        {
            "fixed_leverage": FIXED_LEVERAGE,
            "ai_can_change_leverage": False,
            "target_net_oos_win_rate": TARGET_NET_OOS_WIN_RATE,
            "target_status": TargetStatus.INSUFFICIENT_SAMPLE.value,
            "min_margin": MIN_MARGIN,
            "max_margin": MAX_MARGIN,
            "counts": counts,
            **constitution,
            **meta,
        }
    )


ROUTE_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "/api/nexus/shadow/runtime/status": handle_runtime_status,
    "/api/nexus/shadow/runtime/workers": handle_runtime_workers,
    "/api/nexus/shadow/universe/latest": handle_universe_latest,
    "/api/nexus/shadow/markets": handle_markets,
    "/api/nexus/shadow/candidates": handle_candidates,
    "/api/nexus/shadow/reviews": handle_reviews,
    "/api/nexus/shadow/portfolio": handle_portfolio,
    "/api/nexus/shadow/portfolio/overview": handle_portfolio_overview,
    "/api/nexus/shadow/positions": handle_positions,
    "/api/nexus/shadow/outcomes": handle_outcomes,
    "/api/nexus/shadow/reflections": handle_reflections,
    "/api/nexus/shadow/learning/overview": handle_learning_overview,
}


def dispatch_route(path: str, **kwargs: Any) -> dict[str, Any]:
    handler = ROUTE_HANDLERS.get(path)
    if handler:
        return handler(**kwargs)
    return _wrap({"ok": False, "error": "unknown_route", **_empty_meta()})


def register_real_shadow_routes(app) -> None:
    """Register Wave 5 read-only routes (soft-fail at server level)."""

    @app.route("/api/nexus/shadow/runtime/status")
    def shadow_runtime_status():
        from flask import jsonify

        return jsonify(handle_runtime_status())

    @app.route("/api/nexus/shadow/runtime/workers")
    def shadow_runtime_workers():
        from flask import jsonify

        return jsonify(handle_runtime_workers())

    @app.route("/api/nexus/shadow/portfolio/overview")
    def shadow_portfolio_overview():
        from flask import jsonify

        return jsonify(handle_portfolio_overview())

    @app.route("/api/nexus/shadow/learning/overview")
    def shadow_learning_overview_wave5():
        from flask import jsonify

        return jsonify(handle_learning_overview())
