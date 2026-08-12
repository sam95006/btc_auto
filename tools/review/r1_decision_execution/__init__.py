"""FOUNDER R1 — Decision + Execution cross-lane review (reviewer-owned).

Does not modify Lane A/B implementation paths. Loads Lane A/B from sibling
worktrees or git refs for adversarial inspection only.
"""
from __future__ import annotations

from tools.review.r1_decision_execution.runner import (
    ARTIFACT_DIR,
    OWNED_PATHS,
    PASS_STATUS,
    run_r1_review,
    write_artifacts,
)

__all__ = [
    "ARTIFACT_DIR",
    "OWNED_PATHS",
    "PASS_STATUS",
    "run_r1_review",
    "write_artifacts",
]
