"""Read-only Wave 3 adaptive policy / learning API routes."""
from __future__ import annotations

from typing import Any, Callable

from backend.nexus_adaptive_policy import (
    FIXED_LEVERAGE,
    MAX_MARGIN,
    MIN_MARGIN,
    TARGET_NET_OOS_WIN_RATE,
)
from backend.nexus_adaptive_policy.constitution import LeverageConstitution
from backend.nexus_adaptive_policy.metrics import TargetStatus

READ_ONLY_META = {
    "read_only": True,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "mode": "SHADOW",
    "labels": ["SHADOW", "NOT_LIVE", "NO_EXCHANGE_WRITE", "WAVE3_ADAPTIVE_POLICY"],
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


class AdaptivePolicyApiState:
    """In-memory backing store for tests and local shadow runtime."""

    def __init__(self) -> None:
        self.trade_cases: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.mistakes: list[dict[str, Any]] = []
        self.reflections: list[dict[str, Any]] = []
        self.proposals: list[dict[str, Any]] = []
        self.patches: list[dict[str, Any]] = []
        self.experiments: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.metrics: dict[str, Any] | None = None
        self.policy_snapshot: dict[str, Any] | None = None
        self.champion: dict[str, Any] | None = None
        self.challengers: list[dict[str, Any]] = []


_STATE: AdaptivePolicyApiState | None = None


def get_adaptive_policy_api_state() -> AdaptivePolicyApiState:
    global _STATE
    if _STATE is None:
        _STATE = AdaptivePolicyApiState()
    return _STATE


def reset_adaptive_policy_api_state() -> None:
    global _STATE
    _STATE = AdaptivePolicyApiState()


def _has_data(st: AdaptivePolicyApiState) -> bool:
    return bool(
        st.trade_cases
        or st.failures
        or st.mistakes
        or st.reflections
        or st.proposals
        or st.patches
        or st.experiments
        or st.decisions
        or st.metrics
        or st.policy_snapshot
        or st.champion
        or st.challengers
    )


def handle_learning_overview() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    if not _has_data(st):
        return _wrap(
            {
                **_empty_meta(),
                "fixed_leverage": FIXED_LEVERAGE,
                "ai_can_change_leverage": False,
                "target_net_oos_win_rate": TARGET_NET_OOS_WIN_RATE,
                "target_status": TargetStatus.INSUFFICIENT_SAMPLE.value,
                "counts": {
                    "trade_cases": 0,
                    "failures": 0,
                    "mistakes": 0,
                    "reflections": 0,
                    "proposals": 0,
                    "patches": 0,
                    "experiments": 0,
                },
            }
        )
    metrics = st.metrics or {}
    return _wrap(
        {
            "data_status": "OK",
            "data_source": "ADAPTIVE_POLICY_STORE",
            "dataSource": "ADAPTIVE_POLICY_STORE",
            "freshness": "OK",
            "providerStatus": "CONNECTED",
            "fixed_leverage": FIXED_LEVERAGE,
            "ai_can_change_leverage": False,
            "target_net_oos_win_rate": TARGET_NET_OOS_WIN_RATE,
            "target_status": metrics.get("target_status", TargetStatus.INSUFFICIENT_SAMPLE.value),
            "counts": {
                "trade_cases": len(st.trade_cases),
                "failures": len(st.failures),
                "mistakes": len(st.mistakes),
                "reflections": len(st.reflections),
                "proposals": len(st.proposals),
                "patches": len(st.patches),
                "experiments": len(st.experiments),
            },
            "metrics": metrics,
        }
    )


def handle_policy_overview() -> dict[str, Any]:
    constitution = LeverageConstitution()
    st = get_adaptive_policy_api_state()
    base = {
        "fixed_leverage": FIXED_LEVERAGE,
        "min_margin": MIN_MARGIN,
        "max_margin": MAX_MARGIN,
        "ai_can_change_leverage": False,
        "constitution": constitution.to_dict(),
    }
    if not _has_data(st):
        return _wrap({**_empty_meta(), **base})
    return _wrap(
        {
            "data_status": "OK",
            "data_source": "ADAPTIVE_POLICY_STORE",
            "dataSource": "ADAPTIVE_POLICY_STORE",
            "freshness": "OK",
            "providerStatus": "CONNECTED",
            **base,
            "snapshot": st.policy_snapshot,
            "champion": st.champion,
            "challenger_count": len(st.challengers),
        }
    )


def _list_handler(items: list, *, key: str = "items") -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    if not items:
        return _wrap({**_empty_meta(), "count": 0, key: []})
    return _wrap(
        {
            "data_status": "OK",
            "data_source": "ADAPTIVE_POLICY_STORE",
            "dataSource": "ADAPTIVE_POLICY_STORE",
            "freshness": "OK",
            "providerStatus": "CONNECTED",
            "count": len(items),
            key: list(items),
        }
    )


def handle_trade_cases() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    return _list_handler(st.trade_cases, key="trade_cases")


def handle_failures() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    return _list_handler(st.failures, key="failures")


def handle_mistakes() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    return _list_handler(st.mistakes, key="mistakes")


def handle_reflections() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    return _list_handler(st.reflections, key="reflections")


def handle_proposals() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    return _list_handler(st.proposals, key="proposals")


def handle_learning_metrics() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    if not st.metrics:
        return _wrap(
            {
                **_empty_meta(),
                "target_net_oos_win_rate": TARGET_NET_OOS_WIN_RATE,
                "target_status": TargetStatus.INSUFFICIENT_SAMPLE.value,
            }
        )
    return _wrap(
        {
            "data_status": "OK",
            "data_source": "ADAPTIVE_POLICY_STORE",
            "dataSource": "ADAPTIVE_POLICY_STORE",
            "freshness": "OK",
            "providerStatus": "CONNECTED",
            **st.metrics,
        }
    )


def handle_patches() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    return _list_handler(st.patches, key="patches")


def handle_experiments() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    return _list_handler(st.experiments, key="experiments")


def handle_constitution() -> dict[str, Any]:
    constitution = LeverageConstitution()
    meta = _empty_meta()
    if _has_data(get_adaptive_policy_api_state()):
        meta = {
            "data_status": "OK",
            "data_source": "CONSTITUTION",
            "dataSource": "CONSTITUTION",
            "freshness": "OK",
            "providerStatus": "CONNECTED",
        }
    return _wrap({**meta, "constitution": constitution.to_dict()})


def handle_policy_snapshot() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    if not st.policy_snapshot:
        return _wrap({**_empty_meta(), "snapshot": None})
    return _wrap(
        {
            "data_status": "OK",
            "data_source": "ADAPTIVE_POLICY_STORE",
            "dataSource": "ADAPTIVE_POLICY_STORE",
            "freshness": "OK",
            "providerStatus": "CONNECTED",
            "snapshot": st.policy_snapshot,
        }
    )


def handle_decisions() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    return _list_handler(st.decisions, key="decisions")


def handle_champion() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    if not st.champion:
        return _wrap({**_empty_meta(), "champion": None})
    return _wrap(
        {
            "data_status": "OK",
            "data_source": "ADAPTIVE_POLICY_STORE",
            "dataSource": "ADAPTIVE_POLICY_STORE",
            "freshness": "OK",
            "providerStatus": "CONNECTED",
            "champion": st.champion,
        }
    )


def handle_challengers() -> dict[str, Any]:
    st = get_adaptive_policy_api_state()
    return _list_handler(st.challengers, key="challengers")


ROUTE_TABLE: dict[str, Callable[[], dict[str, Any]]] = {
    "/api/nexus/shadow/learning/overview": handle_learning_overview,
    "/api/nexus/shadow/learning/trade-cases": handle_trade_cases,
    "/api/nexus/shadow/learning/failures": handle_failures,
    "/api/nexus/shadow/learning/mistakes": handle_mistakes,
    "/api/nexus/shadow/learning/reflections": handle_reflections,
    "/api/nexus/shadow/learning/proposals": handle_proposals,
    "/api/nexus/shadow/learning/metrics": handle_learning_metrics,
    "/api/nexus/shadow/learning/patches": handle_patches,
    "/api/nexus/shadow/learning/experiments": handle_experiments,
    "/api/nexus/shadow/policy/overview": handle_policy_overview,
    "/api/nexus/shadow/policy/constitution": handle_constitution,
    "/api/nexus/shadow/policy/snapshot": handle_policy_snapshot,
    "/api/nexus/shadow/policy/decisions": handle_decisions,
    "/api/nexus/shadow/policy/champion": handle_champion,
    "/api/nexus/shadow/policy/challengers": handle_challengers,
}


def dispatch_route(path: str) -> dict[str, Any]:
    handler = ROUTE_TABLE.get(path)
    if handler is None:
        return _wrap({"error": "unknown_route", "path": path, **_empty_meta()})
    return handler()


def register_adaptive_policy_routes(app) -> None:
    for path, handler in ROUTE_TABLE.items():

        def _make_view(h: Callable[[], dict[str, Any]]):
            def view():
                from flask import jsonify

                return jsonify(h())

            view.__name__ = f"adaptive_policy_{path.replace('/', '_')}"
            return view

        app.add_url_rule(path, endpoint=f"adaptive_policy{path.replace('/', '_')}", view_func=_make_view(handler))
