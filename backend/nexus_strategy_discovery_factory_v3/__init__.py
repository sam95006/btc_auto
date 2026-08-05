"""NEXUS V13-C — Cost-Aware Strategy Discovery Factory V3.

Development / synthetic / non-OOS only. Never emits qualified or profitability claims.
qualification_ready_count is always 0.
"""
from __future__ import annotations

from backend.nexus_strategy_discovery_factory_v3.adversarial import run_adversarial_review
from backend.nexus_strategy_discovery_factory_v3.artifacts import (
    build_status_payload,
    write_immutable_artifacts,
    write_runtime_status,
)
from backend.nexus_strategy_discovery_factory_v3.classifier import classify_candidate
from backend.nexus_strategy_discovery_factory_v3.constants import (
    ALLOWED_LABELS,
    CAMPAIGN_ID,
    MECHANISM_FAMILIES,
    PACKAGE,
    REQUIRED_COST_COMPONENTS,
    SCHEMA,
)
from backend.nexus_strategy_discovery_factory_v3.factory import run_discovery_factory
from backend.nexus_strategy_discovery_factory_v3.families import family_catalog

__all__ = [
    "ALLOWED_LABELS",
    "CAMPAIGN_ID",
    "MECHANISM_FAMILIES",
    "PACKAGE",
    "REQUIRED_COST_COMPONENTS",
    "SCHEMA",
    "build_status_payload",
    "classify_candidate",
    "family_catalog",
    "run_adversarial_review",
    "run_discovery_factory",
    "write_immutable_artifacts",
    "write_runtime_status",
]
