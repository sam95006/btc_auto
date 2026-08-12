"""Canonical checkpoint envelope constants (V11.1 C4)."""
from __future__ import annotations

ENVELOPE_SCHEMA = "nexus_checkpoint_envelope_v1"
ENVELOPE_SCHEMA_VERSION = 1
LKG_SCHEMA = "nexus_checkpoint_lkg_v1"
CANONICAL_CHECKPOINT_ENVELOPE_COUNT = 1
CANONICAL_MODULE = "backend.nexus_checkpoint.store"
CANONICAL_SYMBOL = "CanonicalCheckpointStore"
AUTHORITY_ID = "private_core.checkpoint.envelope_v1"

# Subsystems own payload schemas; envelope owns identity + integrity metadata.
PAYLOAD_TYPES: tuple[str, ...] = (
    "session",
    "reflection",
    "microstructure",
    "qualification",
    "decision",
    "control_plane",
)

BLOCKED_AMBIGUOUS_STATE = "BLOCKED_AMBIGUOUS_STATE"
CORRUPTION_DETECTED = "CORRUPTION_DETECTED"
RECOVERED_EXACT = "RECOVERED_EXACT"
RECOVERED_LAST_KNOWN_GOOD = "RECOVERED_LAST_KNOWN_GOOD"
RECOVERY_FAILED = "RECOVERY_FAILED"
CHECKPOINT_OK = "CHECKPOINT_OK"
MIGRATION_DRY_RUN = "MIGRATION_DRY_RUN"
MIGRATION_BLOCKED = "MIGRATION_BLOCKED"

# Hard ban: never write into the live V2.3 checkpoint path from this authority.
LIVE_V23_CHECKPOINT_NAME = "blind_reflection_v23_checkpoint.json"
DESTRUCTIVE_LIVE_MIGRATION_FORBIDDEN = True

REQUIRED_ENVELOPE_FIELDS: tuple[str, ...] = (
    "checkpoint_id",
    "schema_version",
    "payload_type",
    "payload_checksum",
    "manifest_checksum",
    "created_at",
    "ledger_sequence",
    "previous_checkpoint_id",
    "idempotency_key",
    "source_runtime",
    "migration_history",
)
