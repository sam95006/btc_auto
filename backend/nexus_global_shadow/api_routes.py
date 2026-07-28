"""Read-only shadow API route handlers (no exchange write)."""
from __future__ import annotations

from typing import Any, Callable

from backend.nexus_global_shadow import BENCHMARK_SYMBOLS, MAX_OPEN_POSITIONS
from backend.nexus_global_shadow.scoreboard import GlobalMarketShadowScoreboard
from backend.nexus_global_shadow.workers import WorkerHealthRegistry

FIXTURE_LABELS = ["FIXTURE", "NOT_LIVE", "NOT_EXECUTED"]

READ_ONLY_META = {
    "read_only": True,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "mode": "SHADOW",
    "labels": ["SHADOW", "NOT_LIVE", "NO_EXCHANGE_WRITE", *FIXTURE_LABELS],
}


class ShadowApiState:
    """In-memory API backing store for tests."""

    def __init__(self) -> None:
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
            "labels": FIXTURE_LABELS,
            "mode": "SHADOW",
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


def _wrap(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    labels = list(payload.get("labels") or [])
    for label in READ_ONLY_META["labels"]:
        if label not in labels:
            labels.append(label)
    payload["labels"] = labels
    return {**READ_ONLY_META, **payload}


def _fixture_markets() -> list[dict[str, Any]]:
    return [
        {
            "symbol": sym,
            "status": "FIXTURE",
            "labels": FIXTURE_LABELS,
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


def handle_overview(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    sb = st.scoreboard.to_dict()
    latest = st.universe_snapshots[-1] if st.universe_snapshots else {}
    has_data = bool(latest or sb.get("markets_scanned"))
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
    if not has_data and not any(funnel.values()):
        funnel = _fixture_funnel()
    return _wrap(
        {
            "funnel": funnel,
            "scoreboard": sb,
            "maxOpenPositions": MAX_OPEN_POSITIONS,
            "dataSource": "live_state" if has_data else "fixture",
        }
    )


def handle_universe(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    snapshots = st.universe_snapshots
    if not snapshots:
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
                "labels": FIXTURE_LABELS,
            }
        ]
    return _wrap({"snapshots": snapshots, "count": len(snapshots)})


def handle_universe_latest(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    latest = st.universe_snapshots[-1] if st.universe_snapshots else {}
    if not latest:
        latest = {
            "total_markets": 128,
            "eligible_markets": 24,
            "excluded_markets": 104,
            "exclusion_reason_counts": {"LOW_LIQUIDITY": 40, "STALE_PRICE": 64},
            "captured_at": None,
            "freshness": "FIXTURE",
            "provider_status": "FIXTURE",
            "universe_snapshot_id": "fixture_universe_001",
            "labels": FIXTURE_LABELS,
        }
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
        }
    )


def handle_markets(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    markets = list(st.markets.values()) if st.markets else _fixture_markets()
    return _wrap({"markets": markets, "count": len(markets)})


def handle_market(symbol: str, state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    m = st.markets.get(symbol)
    if not m:
        for row in _fixture_markets():
            if row["symbol"] == symbol:
                m = row
                break
    if not m:
        return _wrap({"ok": False, "error": "not_found", "symbol": symbol})
    return _wrap({"market": m, "symbol": symbol})


def handle_candidates(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    candidates = list(st.candidates.values())
    if not candidates:
        candidates = [
            {
                "candidate_id": "fixture_cand_001",
                "symbol": "LINKUSDT",
                "direction": "LONG",
                "status": "FIXTURE",
                "labels": FIXTURE_LABELS,
            }
        ]
    return _wrap({"candidates": candidates, "count": len(candidates)})


def handle_candidate(candidate_id: str, state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    c = st.candidates.get(candidate_id)
    if not c and candidate_id == "fixture_cand_001":
        c = {
            "candidate_id": candidate_id,
            "symbol": "LINKUSDT",
            "direction": "LONG",
            "status": "FIXTURE",
            "labels": FIXTURE_LABELS,
        }
    if not c:
        return _wrap({"ok": False, "error": "not_found", "candidate_id": candidate_id})
    return _wrap({"candidate": c})


def handle_reviews(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    reviews = list(st.reviews.values())
    if not reviews:
        reviews = [
            {
                "candidate_id": "fixture_cand_001",
                "review_id": "fixture_review_001",
                "status": "FIXTURE",
                "labels": FIXTURE_LABELS,
                "roles_completed": 6,
            }
        ]
    return _wrap({"reviews": reviews, "count": len(reviews)})


def handle_review(candidate_id: str, state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    r = st.reviews.get(candidate_id)
    if not r and candidate_id == "fixture_cand_001":
        r = {
            "candidate_id": candidate_id,
            "review_id": "fixture_review_001",
            "status": "FIXTURE",
            "labels": FIXTURE_LABELS,
            "roles_completed": 6,
        }
    if not r:
        return _wrap({"ok": False, "error": "not_found", "candidate_id": candidate_id})
    return _wrap({"review": r})


def handle_risk_verdicts(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    verdicts = list(st.risk_verdicts.values())
    if not verdicts:
        verdicts = [
            {
                "candidate_id": "fixture_cand_001",
                "verdict": "WATCH",
                "role": "Risk Critic",
                "labels": FIXTURE_LABELS,
            }
        ]
    return _wrap({"riskVerdicts": verdicts, "count": len(verdicts)})


def handle_portfolio(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    portfolio = st.portfolio
    if not portfolio:
        portfolio = [
            {
                "symbol": "LINKUSDT",
                "weight": 0.5,
                "status": "FIXTURE",
                "labels": FIXTURE_LABELS,
            }
        ]
    return _wrap(
        {
            "portfolio": portfolio,
            "maxOpenPositions": MAX_OPEN_POSITIONS,
            "count": len(portfolio),
        }
    )


def handle_positions(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    positions = list(st.positions.values())
    return _wrap(
        {
            "positions": positions,
            "maxOpenPositions": MAX_OPEN_POSITIONS,
            "openCount": len([p for p in positions if p.get("state") == "SHADOW_OPEN"]),
            "count": len(positions),
        }
    )


def handle_position(position_id: str, state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    p = st.positions.get(position_id)
    if not p:
        return _wrap({"ok": False, "error": "not_found", "position_id": position_id})
    return _wrap({"position": p})


def handle_outcomes(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    outcomes = st.outcomes
    if not outcomes:
        outcomes = [
            {
                "outcome_id": "fixture_outcome_001",
                "symbol": "LINKUSDT",
                "status": "FIXTURE",
                "labels": FIXTURE_LABELS,
            }
        ]
    return _wrap({"outcomes": outcomes, "count": len(outcomes)})


def handle_reflections(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    reflections = st.reflections
    if not reflections:
        reflections = [
            {
                "reflection_id": "fixture_reflection_001",
                "symbol": "LINKUSDT",
                "status": "FIXTURE",
                "labels": FIXTURE_LABELS,
            }
        ]
    return _wrap({"reflections": reflections, "count": len(reflections)})


def handle_learning_patches(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    patches = st.patches
    if not patches:
        patches = [
            {
                "patch_id": "fixture_patch_001",
                "status": "PROPOSED",
                "labels": FIXTURE_LABELS,
                "applied": False,
            }
        ]
    return _wrap({"learningPatches": patches, "count": len(patches)})


def handle_replay_status(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    status = dict(st.replay_status)
    status.setdefault("labels", FIXTURE_LABELS)
    return _wrap({"replay": status})


def handle_workers_health(state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    return _wrap({"workers": st.workers.snapshot()})


def handle_evidence(record_id: str, state: ShadowApiState | None = None) -> dict[str, Any]:
    st = state or get_shadow_api_state()
    rec = st.evidence.get(record_id)
    if not rec and record_id == "fixture_evidence_001":
        rec = {
            "record_id": record_id,
            "symbol": "LINKUSDT",
            "status": "FIXTURE",
            "labels": FIXTURE_LABELS,
        }
    if not rec:
        return _wrap({"ok": False, "error": "not_found", "record_id": record_id})
    return _wrap({"evidence": rec})


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
    return _wrap({"ok": False, "error": "unknown_route"})


def register_shadow_routes(app) -> None:
    """Register read-only Flask routes if app provided."""

    @app.route("/api/nexus/shadow/overview")
    def shadow_overview():
        from flask import jsonify

        return jsonify(handle_overview())

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
