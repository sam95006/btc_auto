"""Founder R2 — Durability + Microstructure cross-lane review."""

from tools.review.r2_durability_microstructure.adversarial_matrix import (
    ADVERSARIAL_SCENARIOS,
    run_adversarial_matrix,
)
from tools.review.r2_durability_microstructure.findings import build_findings_report

__all__ = [
    "ADVERSARIAL_SCENARIOS",
    "run_adversarial_matrix",
    "build_findings_report",
]
