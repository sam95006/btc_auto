"""NEXUS crash recovery primitives.

These primitives back the Founder-only Autonomous Session Orchestrator V1.1
recovery paths. All ambiguous state must be routed to BLOCKED_AMBIGUOUS —
never guessed or silently resumed.
"""
from backend.nexus_recovery.crash_recovery import (  # noqa: F401
    AmbiguousStateError,
    RecoveryOutcome,
    SessionCrashRecovery,
    recover_from_checkpoint,
)
from backend.nexus_recovery.invariants import (  # noqa: F401
    RecoveryInvariantResult,
    check_recovery_invariants,
)
