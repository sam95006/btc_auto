"""Read-only shadow API route handlers (no exchange write).

Product endpoints return truthful empty state when no real data exists.
Fixture/synthetic payloads are only available when explicit_fixture_mode=True
or via dedicated /api/nexus/shadow/fixture/* helpers for tests/replay.
"""
from __future__ import annotations

from typing import Any, Callable

from backend.nexus_global_shadow import BENCHMARK_SYMBOLS, MAX_OPEN_POSITIONS
from backend.nexus_global_shadow.scoreboard import GlobalMarketShadowScoreboard
from backend.nexus_global_shadow.workers import WorkerHealthRegistry

FIXTURE_LABELS = ["FIXTURE", "NOT_LIVE", "NOT_EXECUTED", "SYNTHETIC_TEST_DATA"]

READ_ONLY_META = {
    "read_only": True,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "mode": "SHADOW",
    "labels": ["SHADOW", "NOT_LIVE", "NO_EXCHANGE_WRITE"],
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


class ShadowApiState:
    """In-memory API backing store for tests and local shadow runtime."""

    def __init__(self) -> None:
        self.explicit_fixture_mode: bool = False
        self.universe_snapshots: list[dict[str, Any]] = []
        self.markets: dict[str, dict[str, Any]] = {}
        self.candidates: dict[str, dict[str, Any]] = {}
        self.reviews: dict[str, dict[str, Any]] = {}
        self.risk_verdicts: dict[str, dict[str, Any]] = {}
        self.portfolio: list[dict[str, Any]] = []
        self.positions: dict[str, dict[str, Any]] = {}
        self.outcomes: list[dict[str, Any]] = []
        self.reflections: list[dict[str, Any]] = []
        self.patches: list[dict[str, Any]] = []
        self.evidence: dict[str, dict[str, Any]] = {}
        self.scoreboard = GlobalMarketShadowScoreboard()
        self.workers = WorkerHealthRegistry()
        self.workers.ensure_all_types_registered()
        self.replay_status: dict[str, Any] = {
            "status": "IDLE",
            "labels": ["NOT_LIVE", "NO_EXCHANGE_WRITE"],
            "mode": "SHADOW",
            "data_status": "NO_DATA",
        }


_STATE: ShadowApiState | None = None


def get_shadow_api_state() -> ShadowApiState:
    global _STATE
    if _STATE is None:
        _STATE = ShadowApiState()
    return _STATE


def reset_shadow_api_state() -> None:
    global _STATE
    _STATE = ShadowApiState()


def enable_explicit_fixture_mode(enabled: bool = True) -> None:
    get_shadow_api_state().explicit_fixture_mode = bool(enabled)


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
        "explicit_fixture_mode": False,
    }


def _fixture_meta() -> dict[str, Any]:
    return {
        "data_status": "FIXTURE",
        "data_source": "FIXTURE",
        "dataSource": "FIXTURE",
        "freshness": "FIXTURE",
        "providerStatus": "FIXTURE",
        "explicit_fixture_mode": True,
        "labels": list(FIXTURE_LABELS),
    }


def _fixture_markets() -> list[dict[str, Any]]:
    return [
        {
            "symbol": sym,
            "status": "FIXTURE",
            "labels": list(FIXTURE_LABELS),
            "eligible": sym != "PEPEUSDT",
            "liquidityScore": 75.0 if sym != "PEPEUSDT" else 42.0,
            "regime": "RANGE",
            "freshness": "FIXTURE",
        }
        for sym in BENCHMARK_SYMBOLS
    ]


def _fixture_funnel() -> dict[str, int]:
    return {
        "marketsScanned": 128,
        "marketsEligible": 24,
        "candidatesGenerated": 6,
        "sixRoleReviewed": 4,
        "riskCriticPassed": 2,
        "riskCriticBlocked": 2,
        "portfolioSelected": 1,
        "openShadowPositions": 0,
    }


def _has_real_data(st: ShadowApiState) -> bool:
    sb = st.scoreboard.to_dict()
    return bool(
        st.universe_snapshots
        or st.markets
        or st.candidates
        or sb.get("markets_scanned")
        or sb.get("candidate_count")
    )


def handle_overview(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    sb = st.scoreboard.to_dict()
    latest = st.universe_snapshots[-1] if st.universe_snapshots else {}
    has_data = _has_real_data(st)

    if has_data:
        funnel = {
            "marketsScanned": sb.get("markets_scanned") or latest.get("total_markets", 0),
            "marketsEligible": sb.get("markets_eligible") or latest.get("eligible_markets", 0),
            "candidatesGenerated": sb.get("candidate_count", 0),
            "sixRoleReviewed": sb.get("six_role_review_count", 0),
            "riskCriticPassed": sb.get("risk_critic_pass_count", 0),
            "riskCriticBlocked": sb.get("risk_critic_block_count", 0),
            "portfolioSelected": sb.get("portfolio_selected_count", 0),
            "openShadowPositions": sb.get("open_shadow_positions", 0),
        }
        return _wrap(
            {
                "funnel": funnel,
                "scoreboard": sb,
                "maxOpenPositions": MAX_OPEN_POSITIONS,
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
                "dataSource": "SHADOW_STATE",
                "freshness": latest.get("freshness", sb.get("data_freshness", "UNKNOWN")),
                "providerStatus": latest.get("provider_status", "OK"),
            }
        )

    if fixture:
        return _wrap(
            {
                "funnel": _fixture_funnel(),
                "scoreboard": sb,
                "maxOpenPositions": MAX_OPEN_POSITIONS,
                **_fixture_meta(),
            }
        )

    return _wrap(
        {
            "funnel": dict(EMPTY_FUNNEL),
            "scoreboard": sb,
            "maxOpenPositions": MAX_OPEN_POSITIONS,
            **_empty_meta(),
        }
    )


def handle_universe(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    if st.universe_snapshots:
        return _wrap(
            {
                "snapshots": st.universe_snapshots,
                "count": len(st.universe_snapshots),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        snapshots = [
            {
                "universe_snapshot_id": "fixture_universe_001",
                "total_markets": 128,
                "eligible_markets": 24,
                "excluded_markets": 104,
                "exclusion_reason_counts": {"LOW_LIQUIDITY": 40, "STALE_PRICE": 64},
                "captured_at": None,
                "freshness": "FIXTURE",
                "provider_status": "FIXTURE",
                "labels": list(FIXTURE_LABELS),
            }
        ]
        return _wrap({"snapshots": snapshots, "count": len(snapshots), **_fixture_meta()})
    return _wrap({"snapshots": [], "count": 0, **_empty_meta()})


def handle_universe_latest(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    latest = st.universe_snapshots[-1] if st.universe_snapshots else {}
    if latest:
        return _wrap(
            {
                "totalMarkets": latest.get("total_markets", 0),
                "eligibleMarkets": latest.get("eligible_markets", 0),
                "excludedMarkets": latest.get("excluded_markets", 0),
                "exclusionReasonCounts": latest.get("exclusion_reason_counts", {}),
                "capturedAt": latest.get("captured_at"),
                "freshness": latest.get("freshness", "UNKNOWN"),
                "providerStatus": latest.get("provider_status", "UNKNOWN"),
                "snapshotId": latest.get("universe_snapshot_id"),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        return _wrap(
            {
                "totalMarkets": 128,
                "eligibleMarkets": 24,
                "excludedMarkets": 104,
                "exclusionReasonCounts": {"LOW_LIQUIDITY": 40, "STALE_PRICE": 64},
                "capturedAt": None,
                "freshness": "FIXTURE",
                "providerStatus": "FIXTURE",
                "snapshotId": "fixture_universe_001",
                **_fixture_meta(),
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


def handle_markets(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    if st.markets:
        markets = list(st.markets.values())
        return _wrap(
            {
                "markets": markets,
                "count": len(markets),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        markets = _fixture_markets()
        return _wrap({"markets": markets, "count": len(markets), **_fixture_meta()})
    return _wrap({"markets": [], "count": 0, **_empty_meta()})


def handle_market(
    symbol: str,
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    m = st.markets.get(symbol)
    if m:
        return _wrap({"market": m, "symbol": symbol, "data_status": "OK", "data_source": "SHADOW_STATE"})
    if fixture:
        for row in _fixture_markets():
            if row["symbol"] == symbol:
                return _wrap({"market": row, "symbol": symbol, **_fixture_meta()})
    return _wrap({"ok": False, "error": "not_found", "symbol": symbol, **_empty_meta()})


def handle_candidates(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    candidates = list(st.candidates.values())
    if candidates:
        return _wrap(
            {
                "candidates": candidates,
                "count": len(candidates),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        candidates = [
            {
                "candidate_id": "fixture_cand_001",
                "symbol": "LINKUSDT",
                "direction": "LONG",
                "status": "FIXTURE",
                "labels": list(FIXTURE_LABELS),
            }
        ]
        return _wrap({"candidates": candidates, "count": len(candidates), **_fixture_meta()})
    return _wrap({"candidates": [], "count": 0, **_empty_meta()})


def handle_candidate(
    candidate_id: str,
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    c = st.candidates.get(candidate_id)
    if c:
        return _wrap({"candidate": c, "data_status": "OK", "data_source": "SHADOW_STATE"})
    if fixture and candidate_id == "fixture_cand_001":
        c = {
            "candidate_id": candidate_id,
            "symbol": "LINKUSDT",
            "direction": "LONG",
            "status": "FIXTURE",
            "labels": list(FIXTURE_LABELS),
        }
        return _wrap({"candidate": c, **_fixture_meta()})
    return _wrap({"ok": False, "error": "not_found", "candidate_id": candidate_id, **_empty_meta()})


def handle_reviews(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    reviews = list(st.reviews.values())
    if reviews:
        return _wrap(
            {
                "reviews": reviews,
                "count": len(reviews),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        reviews = [
            {
                "candidate_id": "fixture_cand_001",
                "review_id": "fixture_review_001",
                "status": "FIXTURE",
                "labels": list(FIXTURE_LABELS),
                "roles_completed": 6,
            }
        ]
        return _wrap({"reviews": reviews, "count": len(reviews), **_fixture_meta()})
    return _wrap({"reviews": [], "count": 0, **_empty_meta()})


def handle_review(
    candidate_id: str,
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    r = st.reviews.get(candidate_id)
    if r:
        return _wrap({"review": r, "data_status": "OK", "data_source": "SHADOW_STATE"})
    if fixture and candidate_id == "fixture_cand_001":
        r = {
            "candidate_id": candidate_id,
            "review_id": "fixture_review_001",
            "status": "FIXTURE",
            "labels": list(FIXTURE_LABELS),
            "roles_completed": 6,
        }
        return _wrap({"review": r, **_fixture_meta()})
    return _wrap({"ok": False, "error": "not_found", "candidate_id": candidate_id, **_empty_meta()})


def handle_risk_verdicts(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    verdicts = list(st.risk_verdicts.values())
    if verdicts:
        return _wrap(
            {
                "riskVerdicts": verdicts,
                "count": len(verdicts),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        verdicts = [
            {
                "candidate_id": "fixture_cand_001",
                "verdict": "WATCH",
                "role": "Risk Critic",
                "labels": list(FIXTURE_LABELS),
            }
        ]
        return _wrap({"riskVerdicts": verdicts, "count": len(verdicts), **_fixture_meta()})
    return _wrap({"riskVerdicts": [], "count": 0, **_empty_meta()})


def handle_portfolio(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    portfolio = list(st.portfolio)
    if portfolio:
        return _wrap(
            {
                "portfolio": portfolio,
                "maxOpenPositions": MAX_OPEN_POSITIONS,
                "count": len(portfolio),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        portfolio = [
            {
                "symbol": "LINKUSDT",
                "weight": 0.5,
                "status": "FIXTURE",
                "labels": list(FIXTURE_LABELS),
            }
        ]
        return _wrap(
            {
                "portfolio": portfolio,
                "maxOpenPositions": MAX_OPEN_POSITIONS,
                "count": len(portfolio),
                **_fixture_meta(),
            }
        )
    return _wrap(
        {
            "portfolio": [],
            "maxOpenPositions": MAX_OPEN_POSITIONS,
            "count": 0,
            **_empty_meta(),
        }
    )


def handle_positions(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    positions = list(st.positions.values())
    meta = {"data_status": "OK", "data_source": "SHADOW_STATE"} if positions else _empty_meta()
    return _wrap(
        {
            "positions": positions,
            "maxOpenPositions": MAX_OPEN_POSITIONS,
            "openCount": len([p for p in positions if p.get("state") == "SHADOW_OPEN"]),
            "count": len(positions),
            **meta,
        }
    )


def handle_position(position_id: str, state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    p = st.positions.get(position_id)
    if not p:
        return _wrap({"ok": False, "error": "not_found", "position_id": position_id, **_empty_meta()})
    return _wrap({"position": p, "data_status": "OK", "data_source": "SHADOW_STATE"})


def handle_outcomes(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    outcomes = list(st.outcomes)
    if outcomes:
        return _wrap(
            {
                "outcomes": outcomes,
                "count": len(outcomes),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        outcomes = [
            {
                "outcome_id": "fixture_outcome_001",
                "symbol": "LINKUSDT",
                "status": "FIXTURE",
                "labels": list(FIXTURE_LABELS),
            }
        ]
        return _wrap({"outcomes": outcomes, "count": len(outcomes), **_fixture_meta()})
    return _wrap({"outcomes": [], "count": 0, **_empty_meta()})


def handle_reflections(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    reflections = list(st.reflections)
    if reflections:
        return _wrap(
            {
                "reflections": reflections,
                "count": len(reflections),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        reflections = [
            {
                "reflection_id": "fixture_reflection_001",
                "symbol": "LINKUSDT",
                "status": "FIXTURE",
                "labels": list(FIXTURE_LABELS),
            }
        ]
        return _wrap({"reflections": reflections, "count": len(reflections), **_fixture_meta()})
    return _wrap({"reflections": [], "count": 0, **_empty_meta()})


def handle_learning_patches(
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    patches = list(st.patches)
    if patches:
        return _wrap(
            {
                "learningPatches": patches,
                "count": len(patches),
                "data_status": "OK",
                "data_source": "SHADOW_STATE",
            }
        )
    if fixture:
        patches = [
            {
                "patch_id": "fixture_patch_001",
                "status": "PROPOSED",
                "labels": list(FIXTURE_LABELS),
                "applied": False,
            }
        ]
        return _wrap({"learningPatches": patches, "count": len(patches), **_fixture_meta()})
    return _wrap({"learningPatches": [], "count": 0, **_empty_meta()})


def handle_replay_status(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    status = dict(st.replay_status)
    return _wrap({"replay": status, **_empty_meta()})


def handle_workers_health(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    return _wrap({"workers": st.workers.snapshot(), "data_status": "OK", "data_source": "WORKER_REGISTRY"})


def handle_evidence(
    record_id: str,
    state: ShadowApiState | None = None,
    *,
    explicit_fixture_mode: bool | None = None,
) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    fixture = st.explicit_fixture_mode if explicit_fixture_mode is None else explicit_fixture_mode
    rec = st.evidence.get(record_id)
    if rec:
        return _wrap({"evidence": rec, "data_status": "OK", "data_source": "SHADOW_STATE"})
    if fixture and record_id == "fixture_evidence_001":
        rec = {
            "record_id": record_id,
            "symbol": "LINKUSDT",
            "status": "FIXTURE",
            "labels": list(FIXTURE_LABELS),
        }
        return _wrap({"evidence": rec, **_fixture_meta()})
    return _wrap({"ok": False, "error": "not_found", "record_id": record_id, **_empty_meta()})


def handle_fixture_overview() -> dict[str, Any]:
    """Dedicated fixture endpoint — never used as product default."""
    return handle_overview(explicit_fixture_mode=True)


ROUTE_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "/api/nexus/shadow/overview": handle_overview,
    "/api/nexus/shadow/universe": handle_universe,
    "/api/nexus/shadow/universe/latest": handle_universe_latest,
    "/api/nexus/shadow/markets": handle_markets,
    "/api/nexus/shadow/candidates": handle_candidates,
    "/api/nexus/shadow/reviews": handle_reviews,
    "/api/nexus/shadow/risk-verdicts": handle_risk_verdicts,
    "/api/nexus/shadow/portfolio": handle_portfolio,
    "/api/nexus/shadow/positions": handle_positions,
    "/api/nexus/shadow/outcomes": handle_outcomes,
    "/api/nexus/shadow/reflections": handle_reflections,
    "/api/nexus/shadow/learning-patches": handle_learning_patches,
    "/api/nexus/shadow/replay/status": handle_replay_status,
    "/api/nexus/shadow/workers/health": handle_workers_health,
    "/api/nexus/shadow/fixture/overview": handle_fixture_overview,
}


def dispatch_route(path: str, **kwargs: Any) -> dict[str, Any]:
    handler = ROUTE_HANDLERS.get(path)
    if handler:
        return handler(**kwargs)
    if path.startswith("/api/nexus/shadow/markets/"):
        symbol = path.rsplit("/", 1)[-1]
        return handle_market(symbol, **kwargs)
    if path.startswith("/api/nexus/shadow/candidates/"):
        candidate_id = path.rsplit("/", 1)[-1]
        return handle_candidate(candidate_id, **kwargs)
    if path.startswith("/api/nexus/shadow/reviews/"):
        candidate_id = path.rsplit("/", 1)[-1]
        return handle_review(candidate_id, **kwargs)
    if path.startswith("/api/nexus/shadow/positions/"):
        position_id = path.rsplit("/", 1)[-1]
        return handle_position(position_id, **kwargs)
    if path.startswith("/api/nexus/shadow/evidence/"):
        record_id = path.rsplit("/", 1)[-1]
        return handle_evidence(record_id, **kwargs)
    return _wrap({"ok": False, "error": "unknown_route", **_empty_meta()})


def register_shadow_routes(app) -> None:
    """Register read-only Flask routes if app provided."""

    @app.route("/api/nexus/shadow/overview")
    def shadow_overview():
        from flask import jsonify

        return jsonify(handle_overview())

    @app.route("/api/nexus/shadow/fixture/overview")
    def shadow_fixture_overview():
        from flask import jsonify

        return jsonify(handle_fixture_overview())

    @app.route("/api/nexus/shadow/universe")
    def shadow_universe():
        from flask import jsonify

        return jsonify(handle_universe())

    @app.route("/api/nexus/shadow/universe/latest")
    def shadow_universe_latest():
        from flask import jsonify

        return jsonify(handle_universe_latest())

    @app.route("/api/nexus/shadow/markets")
    def shadow_markets():
        from flask import jsonify

        return jsonify(handle_markets())

    @app.route("/api/nexus/shadow/markets/<symbol>")
    def shadow_market(symbol: str):
        from flask import jsonify

        return jsonify(handle_market(symbol))

    @app.route("/api/nexus/shadow/candidates")
    def shadow_candidates():
        from flask import jsonify

        return jsonify(handle_candidates())

    @app.route("/api/nexus/shadow/candidates/<candidate_id>")
    def shadow_candidate(candidate_id: str):
        from flask import jsonify

        return jsonify(handle_candidate(candidate_id))

    @app.route("/api/nexus/shadow/reviews")
    def shadow_reviews():
        from flask import jsonify

        return jsonify(handle_reviews())

    @app.route("/api/nexus/shadow/reviews/<candidate_id>")
    def shadow_review(candidate_id: str):
        from flask import jsonify

        return jsonify(handle_review(candidate_id))

    @app.route("/api/nexus/shadow/risk-verdicts")
    def shadow_risk_verdicts():
        from flask import jsonify

        return jsonify(handle_risk_verdicts())

    @app.route("/api/nexus/shadow/portfolio")
    def shadow_portfolio():
        from flask import jsonify

        return jsonify(handle_portfolio())

    @app.route("/api/nexus/shadow/positions")
    def shadow_positions():
        from flask import jsonify

        return jsonify(handle_positions())

    @app.route("/api/nexus/shadow/positions/<position_id>")
    def shadow_position(position_id: str):
        from flask import jsonify

        return jsonify(handle_position(position_id))

    @app.route("/api/nexus/shadow/outcomes")
    def shadow_outcomes():
        from flask import jsonify

        return jsonify(handle_outcomes())

    @app.route("/api/nexus/shadow/reflections")
    def shadow_reflections():
        from flask import jsonify

        return jsonify(handle_reflections())

    @app.route("/api/nexus/shadow/learning-patches")
    def shadow_learning_patches():
        from flask import jsonify

        return jsonify(handle_learning_patches())

    @app.route("/api/nexus/shadow/replay/status")
    def shadow_replay_status():
        from flask import jsonify

        return jsonify(handle_replay_status())

    @app.route("/api/nexus/shadow/evidence/<record_id>")
    def shadow_evidence(record_id: str):
        from flask import jsonify

        return jsonify(handle_evidence(record_id))

    @app.route("/api/nexus/shadow/workers/health")
    def shadow_workers_health():
        from flask import jsonify

        return jsonify(handle_workers_health())
