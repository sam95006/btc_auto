"""Canonical checkpoint envelope authority (V11.1 C4).

One envelope for Session / Reflection / Microstructure / Qualification / Decision.
Subsystems own payload schema; this package owns durable envelope semantics.
"""
from __future__ import annotations

from backend.nexus_checkpoint.constants import (
    AUTHORITY_ID,
    BLOCKED_AMBIGUOUS_STATE,
    CANONICAL_CHECKPOINT_ENVELOPE_COUNT,
    CANONICAL_MODULE,
    CANONICAL_SYMBOL,
    CORRUPTION_DETECTED,
    ENVELOPE_SCHEMA,
    ENVELOPE_SCHEMA_VERSION,
    PAYLOAD_TYPES,
)
from backend.nexus_checkpoint.envelope import (
    build_envelope,
    compute_envelope_checksum,
    compute_payload_checksum,
    detect_corruption,
    validate_envelope,
)
from backend.nexus_checkpoint.store import CanonicalCheckpointStore, atomic_write_json

__all__ = [
    "AUTHORITY_ID",
    "BLOCKED_AMBIGUOUS_STATE",
    "CANONICAL_CHECKPOINT_ENVELOPE_COUNT",
    "CANONICAL_MODULE",
    "CANONICAL_SYMBOL",
    "CORRUPTION_DETECTED",
    "CanonicalCheckpointStore",
    "ENVELOPE_SCHEMA",
    "ENVELOPE_SCHEMA_VERSION",
    "PAYLOAD_TYPES",
    "atomic_write_json",
    "build_envelope",
    "compute_envelope_checksum",
    "compute_payload_checksum",
    "detect_corruption",
    "validate_envelope",
]
