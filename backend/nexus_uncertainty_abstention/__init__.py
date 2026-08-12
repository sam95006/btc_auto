"""V16-G Uncertainty and Abstention Engine.

Gates AI confidence into ALLOW / ALLOW_REDUCED / WAIT / ABSTAIN / BLOCK.
Fail-closed on provider failure, invalid JSON, contradiction, stale evidence,
bad data (consensus cannot override), and all fail-open attacks.
"""
from __future__ import annotations

from backend.nexus_uncertainty_abstention.adversarial import run_fail_open_attacks
from backend.nexus_uncertainty_abstention.engine import (
    apply_ai_suggestion,
    evaluate_inputs,
    evaluate_raw,
)
from backend.nexus_uncertainty_abstention.three_pass import run_pass, run_three_passes

__all__ = [
    "apply_ai_suggestion",
    "evaluate_inputs",
    "evaluate_raw",
    "run_fail_open_attacks",
    "run_pass",
    "run_three_passes",
]
