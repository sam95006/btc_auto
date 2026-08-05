"""NEXUS Runtime Durability V2 — hash-chained ledger, snapshots, checkpoints.

Hard rules:
  * No silent recovery guess
  * No exchange write
  * Ambiguous state blocks (BLOCKED_AMBIGUOUS_STATE)
  * Hash corruption is detected, never repaired silently
  * Duplicate events are idempotent
  * Ledger sequence is strictly monotonic
"""
from backend.nexus_runtime.durability_v2.ledger import (  # noqa: F401
    AppendResult,
    DurableEventLedgerV2,
)
from backend.nexus_runtime.durability_v2.engine import (  # noqa: F401
    RuntimeDurabilityV2,
    SnapshotResult,
)
from backend.nexus_runtime.durability_v2.metrics import (  # noqa: F401
    LatencyHistogram,
    percentile,
)
from backend.nexus_runtime.durability_v2.constants import (  # noqa: F401
    SCHEMA_VERSION,
    GENESIS_HASH,
    BLOCKED_AMBIGUOUS_STATE,
    CORRUPTION_DETECTED,
)
