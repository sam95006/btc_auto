"""NEXUS V15-B — Mechanism Execution Compiler.

Compiles V14-C semantic mechanisms into deterministic development-only executors.
Never emits edge, profitability, or qualification claims.
qualification_ready_count is always 0.
Does not write *_status.json report files.
"""
from __future__ import annotations

from backend.nexus_mechanism_execution_compiler.adversarial import run_adversarial_review
from backend.nexus_mechanism_execution_compiler.artifacts import (
    build_summary_payload,
    write_immutable_artifacts,
)
from backend.nexus_mechanism_execution_compiler.campaign import run_compiler_campaign
from backend.nexus_mechanism_execution_compiler.compiler import (
    assert_executors_distinct,
    compile_all_executors,
    executor_catalog,
)
from backend.nexus_mechanism_execution_compiler.constants import (
    CAMPAIGN_ID,
    EXPECTED_MECHANISM_COUNT,
    HARD_BANS,
    MIN_EXECUTOR_COUNT,
    PACKAGE,
    SCHEMA,
)
from backend.nexus_mechanism_execution_compiler.replay import assert_replay_stable

__all__ = [
    "CAMPAIGN_ID",
    "EXPECTED_MECHANISM_COUNT",
    "HARD_BANS",
    "MIN_EXECUTOR_COUNT",
    "PACKAGE",
    "SCHEMA",
    "assert_executors_distinct",
    "assert_replay_stable",
    "build_summary_payload",
    "compile_all_executors",
    "executor_catalog",
    "run_adversarial_review",
    "run_compiler_campaign",
    "write_immutable_artifacts",
]
