"""NEXUS V14-C — Strategy Mechanism Lab V4.

Synthetic / development research surface only.
Never emits edge, profitability, or qualification claims.
qualification_ready_count is always 0.
"""
from __future__ import annotations

from backend.nexus_mechanism_lab_v4.adversarial import run_adversarial_review
from backend.nexus_mechanism_lab_v4.artifacts import (
    build_status_payload,
    write_immutable_artifacts,
    write_runtime_status,
)
from backend.nexus_mechanism_lab_v4.catalog import assert_catalog_distinct, mechanism_catalog
from backend.nexus_mechanism_lab_v4.constants import (
    CAMPAIGN_ID,
    HARD_BANS,
    MECHANISM_FAMILIES,
    MIN_MECHANISM_COUNT,
    PACKAGE,
    SCHEMA,
)
from backend.nexus_mechanism_lab_v4.lab import run_mechanism_lab

__all__ = [
    "CAMPAIGN_ID",
    "HARD_BANS",
    "MECHANISM_FAMILIES",
    "MIN_MECHANISM_COUNT",
    "PACKAGE",
    "SCHEMA",
    "assert_catalog_distinct",
    "build_status_payload",
    "mechanism_catalog",
    "run_adversarial_review",
    "run_mechanism_lab",
    "write_immutable_artifacts",
    "write_runtime_status",
]
