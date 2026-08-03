"""Read-only functional research observability — V1.1 extended fields."""
from __future__ import annotations

from typing import Any


def observability_contract() -> dict[str, Any]:
    return {
        "schema": "functional_observability_contract_v1_1",
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
                "actual_loaded_dataset_count",
                "actual_price_dataset_count",
                "actual_derivatives_dataset_count",
                "multi_timeframe_bundle_status",
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
                "evidence_completeness_ratio",
                "AI_deterministic_agreement_ratio",
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
                "component_implemented_count",
                "component_not_implemented_count",
                "semantic_collision_count",
                "candidate_funnel_by_hypothesis",
                "zero_trade_root_causes",
                "derivative_proxy_violation_count",
                "V1_results_interpretation",
                "V1_1_research_status",
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
    v11_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extra = v11_extra or {}
    return {
        "schema": "functional_research_observability_status_v1_1",
        "read_only": True,
        "secrets_present_in_payload": False,
        "dynamic_universe": coverage,
        "real_ai": providers,
        "learning_loop": learning,
        "strategy_research": research,
        "actual_loaded_dataset_count": extra.get("actual_loaded_dataset_count"),
        "actual_price_dataset_count": extra.get("actual_price_dataset_count"),
        "actual_derivatives_dataset_count": extra.get("actual_derivatives_dataset_count"),
        "component_implemented_count": extra.get("component_implemented_count"),
        "component_not_implemented_count": extra.get("component_not_implemented_count"),
        "semantic_collision_count": extra.get("semantic_collision_count"),
        "candidate_funnel_by_hypothesis": extra.get("candidate_funnel_by_hypothesis"),
        "zero_trade_root_causes": extra.get("zero_trade_root_causes"),
        "multi_timeframe_bundle_status": extra.get("multi_timeframe_bundle_status"),
        "derivative_proxy_violation_count": extra.get("derivative_proxy_violation_count"),
        "evidence_completeness_ratio": extra.get("evidence_completeness_ratio"),
        "AI_deterministic_agreement_ratio": extra.get("AI_deterministic_agreement_ratio"),
        "V1_results_interpretation": extra.get("V1_results_interpretation"),
        "V1_1_research_status": extra.get("V1_1_research_status"),
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
    }
