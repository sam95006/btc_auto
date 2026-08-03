"""Read-only functional research observability contract + status builder."""
from __future__ import annotations

from typing import Any


def observability_contract() -> dict[str, Any]:
    return {
        "schema": "functional_observability_contract_v1",
        "ui_redesign": False,
        "read_only": True,
        "secrets_displayed": False,
        "surfaces": {
            "dynamic_universe": [
                "discovered_symbols",
                "research_eligible_symbols",
                "price_capable_symbols",
                "derivatives_capable_symbols",
                "coverage_by_size_class",
                "download_progress",
                "data_gaps",
            ],
            "real_ai": [
                "provider_status",
                "model_identity",
                "request_count",
                "success_count",
                "schema_rejection_count",
                "rate_limit_count",
                "average_latency_ms",
                "last_successful_call",
            ],
            "learning_loop": [
                "reflections",
                "lessons_created",
                "lessons_deduplicated",
                "lesson_conflicts",
                "lessons_retrieved",
                "lessons_applied",
                "undetermined_classifications",
                "evidence_completeness",
            ],
            "strategy_research": [
                "hypotheses_proposed",
                "hypotheses_preregistered",
                "hypotheses_executed",
                "promising",
                "cost_dominated",
                "no_gross_edge",
                "concentrated",
                "insufficient_sample",
                "data_invalid",
            ],
        },
        "api_path": "/api/nexus/research/observability",
    }


def build_observability_status(
    *,
    coverage: dict[str, Any],
    providers: dict[str, Any],
    learning: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "functional_research_observability_status_v1",
        "read_only": True,
        "secrets_present_in_payload": False,
        "dynamic_universe": coverage,
        "real_ai": providers,
        "learning_loop": learning,
        "strategy_research": research,
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
    }
