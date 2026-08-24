"""Certified durable RepeatMistakeGuard — SessionMistakeMemory is telemetry-only."""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_research_decision_path import research_decision_path
from backend.nexus_demo_execution.p2_run8_learning_closure import DurableDecisionMemory


def evaluate_certified_guard(*, candidate: dict[str, Any], store: DurableLessonStore) -> dict[str, Any]:
    memory = DurableDecisionMemory(store)
    path = research_decision_path(candidate, memory=memory)
    guard = path.get("guard") or {}
    blocked = guard.get("decision_after_learning") == "SKIP"
    return {
        "blocked": blocked,
        "guard": guard,
        "memory_hits": path.get("memory_hits") or [],
        "research_recommendation": path.get("research_recommendation"),
        "policy_authority": "DURABLE_POSTGRES_LESSON",
    }
