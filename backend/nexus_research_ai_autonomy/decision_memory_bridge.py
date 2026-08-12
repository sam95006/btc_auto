"""Decision Memory links — reuse existing graph; no new graph DB."""
from __future__ import annotations

import time
from typing import Any

from backend.nexus_decision_memory_graph import DecisionMemoryGraph


class DecisionMemoryBridge:
    def __init__(self, graph: DecisionMemoryGraph | None = None) -> None:
        self.graph = graph or DecisionMemoryGraph()
        self.links: list[dict[str, Any]] = []

    def link_research_lifecycle(
        self,
        *,
        regime: str,
        strategy_family: str,
        symbol: str,
        decision_id: str,
        trade: dict[str, Any] | None,
        management_journal: list[dict[str, Any]] | None,
        outcome: dict[str, Any] | None,
        reflection: dict[str, Any] | None,
        error_classes: list[str] | None,
        lesson_candidate: dict[str, Any] | None,
    ) -> dict[str, Any]:
        as_of = int(time.time() * 1000)
        nodes: dict[str, Any] = {}

        def seal(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
            return self.graph.seal_node(kind=kind, as_of_ms=as_of, payload=payload)

        nodes["regime"] = seal("REGIME", {"regime": regime, "provenance": "RESEARCH_AI_DEMO"})
        nodes["strategy"] = seal("STRATEGY_EXPERT", {"strategy_family": strategy_family, "provenance": "RESEARCH_AI_DEMO"})
        nodes["symbol"] = seal("SYMBOL", {"symbol": symbol})
        nodes["decision"] = seal(
            "DECISION",
            {"decision_id": decision_id, "execution_purpose": "RESEARCH_AI_DEMO"},
        )
        if trade:
            nodes["entry"] = seal("ENTRY", {"trade": trade, "execution_purpose": "RESEARCH_AI_DEMO"})
        if outcome:
            nodes["outcome"] = seal("OUTCOME", {**outcome, "execution_purpose": "RESEARCH_AI_DEMO"})
        if reflection:
            nodes["reflection"] = seal("REFLECTION", {**reflection, "execution_purpose": "RESEARCH_AI_DEMO"})
        if error_classes:
            nodes["error"] = seal("ERROR_CLASSIFICATION", {"classes": list(error_classes)})
        if lesson_candidate:
            nodes["lesson"] = seal(
                "LESSON",
                {**lesson_candidate, "status": "LESSON_CANDIDATE", "active": False},
            )
        if management_journal:
            nodes["management"] = seal(
                "VALIDATION",
                {"management_journal_n": len(management_journal), "provenance": "RESEARCH_AI_DEMO"},
            )

        # Edges (best-effort; graph validates kinds)
        def edge(kind: str, src: str, dst: str) -> None:
            if src in nodes and dst in nodes and nodes[src].get("node_id") and nodes[dst].get("node_id"):
                try:
                    self.graph.seal_edge(
                        kind=kind,
                        from_id=nodes[src]["node_id"],
                        to_id=nodes[dst]["node_id"],
                        as_of_ms=as_of,
                    )
                except Exception:
                    pass

        edge("IN_REGIME", "decision", "regime")
        edge("ROUTED_TO_EXPERT", "decision", "strategy")
        edge("OF_SYMBOL", "decision", "symbol")
        edge("ENTERED_VIA", "decision", "entry")
        edge("RESULTED_IN", "decision", "outcome")
        edge("REFLECTED_IN", "decision", "reflection")
        edge("CLASSIFIED_AS", "outcome", "error")
        edge("PRODUCED_LESSON", "reflection", "lesson")

        link = {
            "decision_id": decision_id,
            "node_ids": {k: v.get("node_id") for k, v in nodes.items()},
            "provenance": "RESEARCH_AI_DEMO",
            "contaminates_formal_wf_oos": False,
        }
        self.links.append(link)
        return link
