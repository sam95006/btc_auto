"""NEXUS V11 Security Mutation Red Team — simulated adversarial mutation campaign.

Execution posture: SIMULATED / LOCAL / FAIL-CLOSED.
Never places exchange orders. Never uses real exchange credentials.
"""
from __future__ import annotations

from backend.nexus_autonomy.security_mutation_v11.redteam import (
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    evaluate_security_mutation_redteam,
    run_security_mutation_redteam,
    write_immutable_artifacts,
)

__all__ = [
    "OWNED_PATHS",
    "PASS_RECOMMENDATION",
    "evaluate_security_mutation_redteam",
    "run_security_mutation_redteam",
    "write_immutable_artifacts",
]
