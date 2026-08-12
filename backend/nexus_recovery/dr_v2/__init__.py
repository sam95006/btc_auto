"""NEXUS Disaster Recovery V2 — fail-closed recovery drills.

Never silently guesses recovery. Ambiguous states block.
No exchange writes. No evidence-loss claims without proof.
"""
from backend.nexus_recovery.dr_v2.recovery import (  # noqa: F401
    DisasterRecoveryV2,
    DrillResult,
)
from backend.nexus_recovery.dr_v2.matrix import (  # noqa: F401
    run_injection_matrix,
    INJECTION_EXPECTATIONS,
)
