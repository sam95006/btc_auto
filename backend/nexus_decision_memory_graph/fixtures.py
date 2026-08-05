"""Synthetic fixtures for V16-H Decision Memory Graph tests."""
from __future__ import annotations

from typing import Any

from backend.nexus_decision_memory_graph.graph import DecisionMemoryGraph


def build_linked_decision_fixture(
    graph: DecisionMemoryGraph | None = None,
    *,
    as_of_ms: int = 1_700_000_000_000,
) -> dict[str, Any]:
    """Seal a full linked decision chain covering all required node kinds."""
    g = graph or DecisionMemoryGraph()
    t0 = int(as_of_ms)

    symbol = g.seal_node(
        kind="SYMBOL",
        as_of_ms=t0,
        payload={"symbol": "BTCUSDT", "label": "BTCUSDT", "data_class": "FIXTURE"},
    )
    snapshot = g.seal_node(
        kind="MARKET_SNAPSHOT",
        as_of_ms=t0,
        payload={
            "symbol": "BTCUSDT",
            "summary": "fixture snapshot",
            "freshness": "fresh",
            "as_of_ms": t0,
            "pit_bound": True,
            "data_class": "FIXTURE",
            "similarity_tags": ["btc", "perp"],
        },
        parent_lineage_hashes=[symbol["lineage_hash"]],
    )
    regime = g.seal_node(
        kind="REGIME",
        as_of_ms=t0,
        payload={
            "regime_label": "vol_expansion",
            "label": "vol_expansion",
            "similarity_tags": ["vol_expansion"],
            "data_class": "FIXTURE",
        },
    )
    candidate = g.seal_node(
        kind="CANDIDATE",
        as_of_ms=t0,
        payload={
            "label": "cand_fixture_1",
            "status": "DEVELOPMENT_REVIEW",
            "similarity_tags": ["trend", "btc"],
            "data_class": "FIXTURE",
        },
    )
    expert = g.seal_node(
        kind="STRATEGY_EXPERT",
        as_of_ms=t0,
        payload={"expert_label": "TREND", "label": "TREND", "data_class": "FIXTURE"},
    )
    reasoner = g.seal_node(
        kind="REASONER",
        as_of_ms=t0,
        payload={"summary": "fixture reasoner", "recommendation": "WAIT", "data_class": "FIXTURE"},
    )
    critic = g.seal_node(
        kind="CRITIC",
        as_of_ms=t0,
        payload={"summary": "fixture critic", "recommendation": "WAIT", "data_class": "FIXTURE"},
    )
    supporting = g.seal_node(
        kind="SUPPORTING_EVIDENCE",
        as_of_ms=t0,
        payload={"summary": "support", "evidence_count": 2, "data_class": "FIXTURE"},
    )
    contradicting = g.seal_node(
        kind="CONTRADICTING_EVIDENCE",
        as_of_ms=t0,
        payload={"summary": "contradict", "evidence_count": 1, "data_class": "FIXTURE"},
    )
    risk = g.seal_node(
        kind="RISK_DECISION",
        as_of_ms=t0,
        payload={"status": "ALLOW_REDUCED", "summary": "risk ok reduced", "data_class": "FIXTURE"},
    )
    entry = g.seal_node(
        kind="ENTRY",
        as_of_ms=t0 + 1,
        payload={"side": "LONG", "status": "SIMULATED", "data_class": "FIXTURE"},
    )
    exit_n = g.seal_node(
        kind="EXIT",
        as_of_ms=t0 + 2,
        payload={"side": "FLAT", "status": "SIMULATED", "data_class": "FIXTURE"},
    )
    costs = g.seal_node(
        kind="COSTS",
        as_of_ms=t0 + 2,
        payload={"summary": "fee+slip fixture", "data_class": "FIXTURE"},
    )
    outcome = g.seal_node(
        kind="OUTCOME",
        as_of_ms=t0 + 3,
        payload={"outcome_class": "GOOD_PROCESS_LOSS", "data_class": "FIXTURE"},
    )
    error = g.seal_node(
        kind="ERROR_CLASSIFICATION",
        as_of_ms=t0 + 3,
        payload={"error_class": "GOOD_PROCESS_LOSS", "data_class": "FIXTURE"},
    )
    reflection = g.seal_node(
        kind="REFLECTION",
        as_of_ms=t0 + 4,
        payload={"summary": "fixture reflection", "data_class": "FIXTURE"},
    )
    lesson = g.seal_node(
        kind="LESSON",
        as_of_ms=t0 + 5,
        payload={"lesson_label": "cand_lesson", "status": "CANDIDATE", "data_class": "FIXTURE"},
    )
    counterfactual = g.seal_node(
        kind="COUNTERFACTUAL",
        as_of_ms=t0 + 5,
        payload={"summary": "no-entry alt", "data_class": "FIXTURE"},
    )
    validation = g.seal_node(
        kind="VALIDATION",
        as_of_ms=t0 + 6,
        payload={"validation_status": "PENDING", "status": "PENDING", "data_class": "FIXTURE"},
    )
    code_v = g.seal_node(
        kind="CODE_VERSION",
        as_of_ms=t0,
        payload={"version_label": "code_v1", "label": "code_v1", "data_class": "FIXTURE"},
    )
    model_v = g.seal_node(
        kind="MODEL_VERSION",
        as_of_ms=t0,
        payload={"version_label": "model_none", "label": "model_none", "data_class": "FIXTURE"},
    )
    policy_v = g.seal_node(
        kind="POLICY_VERSION",
        as_of_ms=t0,
        payload={"version_label": "policy_v1", "label": "policy_v1", "data_class": "FIXTURE"},
    )
    decision = g.seal_node(
        kind="DECISION",
        as_of_ms=t0,
        payload={
            "status": "HISTORICAL_REPLAY",
            "recommendation": "WAIT",
            "symbol": "BTCUSDT",
            "similarity_tags": ["btc", "trend", "vol_expansion"],
            "data_class": "FIXTURE",
        },
        parent_lineage_hashes=[
            snapshot["lineage_hash"],
            regime["lineage_hash"],
            candidate["lineage_hash"],
        ],
    )

    edges = [
        g.seal_edge(kind="OF_SYMBOL", from_id=snapshot["node_id"], to_id=symbol["node_id"], as_of_ms=t0),
        g.seal_edge(kind="OBSERVES", from_id=decision["node_id"], to_id=snapshot["node_id"], as_of_ms=t0),
        g.seal_edge(kind="IN_REGIME", from_id=decision["node_id"], to_id=regime["node_id"], as_of_ms=t0),
        g.seal_edge(kind="PROPOSED_BY", from_id=decision["node_id"], to_id=candidate["node_id"], as_of_ms=t0),
        g.seal_edge(kind="ROUTED_TO_EXPERT", from_id=decision["node_id"], to_id=expert["node_id"], as_of_ms=t0),
        g.seal_edge(kind="REASONED_BY", from_id=decision["node_id"], to_id=reasoner["node_id"], as_of_ms=t0),
        g.seal_edge(kind="CRITICIZED_BY", from_id=decision["node_id"], to_id=critic["node_id"], as_of_ms=t0),
        g.seal_edge(kind="SUPPORTED_BY", from_id=decision["node_id"], to_id=supporting["node_id"], as_of_ms=t0),
        g.seal_edge(kind="CONTRADICTED_BY", from_id=decision["node_id"], to_id=contradicting["node_id"], as_of_ms=t0),
        g.seal_edge(kind="RISK_VERDICT", from_id=decision["node_id"], to_id=risk["node_id"], as_of_ms=t0),
        g.seal_edge(kind="ENTERED_VIA", from_id=decision["node_id"], to_id=entry["node_id"], as_of_ms=t0 + 1),
        g.seal_edge(kind="EXITED_VIA", from_id=decision["node_id"], to_id=exit_n["node_id"], as_of_ms=t0 + 2),
        g.seal_edge(kind="INCURRED_COST", from_id=decision["node_id"], to_id=costs["node_id"], as_of_ms=t0 + 2),
        g.seal_edge(kind="RESULTED_IN", from_id=decision["node_id"], to_id=outcome["node_id"], as_of_ms=t0 + 3),
        g.seal_edge(kind="CLASSIFIED_AS", from_id=decision["node_id"], to_id=error["node_id"], as_of_ms=t0 + 3),
        g.seal_edge(kind="REFLECTED_IN", from_id=decision["node_id"], to_id=reflection["node_id"], as_of_ms=t0 + 4),
        g.seal_edge(kind="PRODUCED_LESSON", from_id=reflection["node_id"], to_id=lesson["node_id"], as_of_ms=t0 + 5),
        g.seal_edge(kind="COUNTERFACTUAL_OF", from_id=counterfactual["node_id"], to_id=decision["node_id"], as_of_ms=t0 + 5),
        g.seal_edge(kind="VALIDATED_BY", from_id=lesson["node_id"], to_id=validation["node_id"], as_of_ms=t0 + 6),
        g.seal_edge(kind="PINNED_CODE", from_id=decision["node_id"], to_id=code_v["node_id"], as_of_ms=t0),
        g.seal_edge(kind="PINNED_MODEL", from_id=decision["node_id"], to_id=model_v["node_id"], as_of_ms=t0),
        g.seal_edge(kind="PINNED_POLICY", from_id=decision["node_id"], to_id=policy_v["node_id"], as_of_ms=t0),
        g.seal_edge(kind="PART_OF_DECISION", from_id=candidate["node_id"], to_id=decision["node_id"], as_of_ms=t0),
    ]

    return {
        "graph": g,
        "decision": decision,
        "symbol": symbol,
        "snapshot": snapshot,
        "nodes": {
            "symbol": symbol,
            "snapshot": snapshot,
            "regime": regime,
            "candidate": candidate,
            "expert": expert,
            "reasoner": reasoner,
            "critic": critic,
            "supporting": supporting,
            "contradicting": contradicting,
            "risk": risk,
            "entry": entry,
            "exit": exit_n,
            "costs": costs,
            "outcome": outcome,
            "error": error,
            "reflection": reflection,
            "lesson": lesson,
            "counterfactual": counterfactual,
            "validation": validation,
            "code_version": code_v,
            "model_version": model_v,
            "policy_version": policy_v,
            "decision": decision,
        },
        "edges": edges,
        "as_of_ms": t0,
    }
