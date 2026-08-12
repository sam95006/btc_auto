"""Public Opportunity DTO — no private execution/reflection/secrets."""
from __future__ import annotations

from typing import Any

FORBIDDEN_DTO_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "wallet_before",
        "wallet_after",
        "bybit_orderId",
        "reflection",
        "mistake_signature",
        "candidate_lesson",
        "lifecycle",
        "exact_pnl_accounting",
    }
)


def build_public_opportunity_dto(snapshot: dict[str, Any], *, signal: dict[str, Any] | None = None) -> dict[str, Any]:
    side = str(snapshot.get("side") or "WAIT").upper()
    eq = float(snapshot.get("entry_quality_score") or 0)
    nexus_score = int(round(eq * 100))
    action = snapshot.get("final_action") or "WAIT"
    state_map = {"SELECT": "READY", "WATCH": "WATCH", "WAIT": "WAIT", "BLOCK": "BLOCK"}
    state = state_map.get(str(action).upper(), "WAIT")
    support = list(snapshot.get("supporting_evidence") or [])
    contradict = list(snapshot.get("contradicting_evidence") or [])
    dto: dict[str, Any] = {
        "symbol": snapshot.get("symbol"),
        "direction": side if side in {"LONG", "SHORT"} else "WAIT",
        "nexus_score_0_100": nexus_score,
        "rank": snapshot.get("rank"),
        "rank_percentile": snapshot.get("rank_percentile"),
        "state": state,
        "market_regime": snapshot.get("regime"),
        "market_structure": snapshot.get("market_structure"),
        "risk_level": "ELEVATED" if "POST_COST_EDGE_NEGATIVE" in contradict else "NORMAL",
        "supporting_evidence": support,
        "contradicting_evidence": contradict,
        "why_now": "; ".join(support[:4]) if support else "insufficient_supporting_evidence",
        "why_not": "; ".join(contradict[:4]) if contradict else None,
        "expected_net_edge": snapshot.get("expected_net_edge"),
        "entry_quality_score": snapshot.get("entry_quality_score"),
        "direction_confidence_quant": snapshot.get("direction_confidence_quant"),
        "invalidation_conditions": [
            x for x in contradict if x in {"MOMENTUM_5M_AGAINST", "REGIME_UNCERTAIN", "SPREAD_WIDE", "POST_COST_EDGE_NEGATIVE"}
        ],
        "data_freshness_ms": snapshot.get("data_freshness_ms"),
        "signal_id": (signal or {}).get("signal_id"),
        "signal_lifecycle_state": (signal or {}).get("lifecycle_state"),
        "historical_similar_setup_stats": None,
        "activity_source": snapshot.get("activity_source"),
        "activity_fallback": snapshot.get("activity_fallback"),
    }
    return sanitize_public_dto(dto)


def sanitize_public_dto(dto: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in dto.items():
        if k.lower() in FORBIDDEN_DTO_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = sanitize_public_dto(v)
        elif isinstance(v, list):
            out[k] = [sanitize_public_dto(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


def dto_leaks_private_data(dto: dict[str, Any]) -> bool:
    text = str(dto).lower()
    banned = ("api_secret", "wallet_balance", "reflection_created", "mistake_signature", "bybit_order")
    return any(b in text for b in banned)
