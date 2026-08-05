"""Declared V16 module version registry for Founder diagnostics.

Versions are declared metadata for the diagnostics surface.
This package does NOT import private-core V16 modules (they live on
separate lanes and are not present on the PUBLIC_V2 tip).
"""
from __future__ import annotations

from typing import Any

# Declared lane tips observed at UX-C bootstrap (research registry only).
V16_MODULE_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "lane": "V16-A",
        "name": "Trade Error Ontology V1",
        "package": "backend.nexus_trade_error_ontology_v1",
        "version": "v1.0.0",
        "branch": "feature/v16-trade-error-ontology-v1",
        "schema": "v16_a_trade_error_ontology_v1",
        "onPublicV2Tip": False,
        "diagnosticsProjection": True,
    },
    {
        "lane": "V16-B",
        "name": "Counterfactual Replay Engine",
        "package": "backend.nexus_counterfactual_replay_v16",
        "version": "v1.0.0",
        "branch": "feature/v16-counterfactual-replay-engine",
        "schema": "v16_b_counterfactual_replay_engine",
        "onPublicV2Tip": False,
        "diagnosticsProjection": True,
    },
    {
        "lane": "V16-C",
        "name": "Probabilistic Regime Engine V2",
        "package": "backend.nexus_probabilistic_regime_v2",
        "version": "v2.0.0",
        "branch": "feature/v16-probabilistic-regime-engine-v2",
        "schema": "FOUNDER_V16_C_PROBABILISTIC_REGIME_V2",
        "onPublicV2Tip": False,
        "diagnosticsProjection": True,
    },
    {
        "lane": "V16-D",
        "name": "Strategy Expert Router",
        "package": "backend.nexus_strategy_expert_router",
        "version": "v1.0.0",
        "branch": "feature/v16-strategy-expert-router",
        "schema": "FOUNDER_V16_D_STRATEGY_EXPERT_ROUTER",
        "onPublicV2Tip": False,
        "diagnosticsProjection": True,
    },
    {
        "lane": "V16-E",
        "name": "Lesson Compiler",
        "package": "backend.nexus_lesson_compiler",
        "version": "v1.0.0",
        "branch": "feature/v16-lesson-compiler",
        "schema": "FOUNDER_V16_E_LESSON_COMPILER",
        "onPublicV2Tip": False,
        "diagnosticsProjection": True,
    },
    {
        "lane": "V16-F",
        "name": "Lesson Validation Firewall",
        "package": "backend.nexus_lesson_validation_firewall",
        "version": "v1.0.0",
        "branch": "feature/v16-lesson-validation-firewall",
        "schema": "FOUNDER_V16_F_LESSON_VALIDATION_FIREWALL",
        "onPublicV2Tip": False,
        "diagnosticsProjection": True,
    },
    {
        "lane": "V16-G",
        "name": "Uncertainty & Abstention Engine",
        "package": "backend.nexus_uncertainty_abstention",
        "version": "v1.0.0",
        "branch": "feature/v16-uncertainty-abstention-engine",
        "schema": "FOUNDER_V16_G_UNCERTAINTY_AND_ABSTENTION_ENGINE",
        "onPublicV2Tip": False,
        "diagnosticsProjection": True,
    },
    {
        "lane": "V16-H",
        "name": "Decision Memory Graph",
        "package": "backend.nexus_decision_memory_graph",
        "version": "v1.0.0",
        "branch": "feature/v16-decision-memory-graph",
        "schema": "FOUNDER_V16_H_DECISION_MEMORY_GRAPH",
        "onPublicV2Tip": False,
        "diagnosticsProjection": True,
    },
)


def module_version_panel_payload() -> dict[str, Any]:
    return {
        "moduleCount": len(V16_MODULE_REGISTRY),
        "modules": [
            {
                "lane": m["lane"],
                "name": m["name"],
                "version": m["version"],
                "schema": m["schema"],
                "onPublicV2Tip": m["onPublicV2Tip"],
                "diagnosticsProjection": m["diagnosticsProjection"],
            }
            for m in V16_MODULE_REGISTRY
        ],
        "integrationStatus": "PROJECTION_ONLY",
        "privateCoreImport": False,
        "realExecutionEnabled": False,
    }
