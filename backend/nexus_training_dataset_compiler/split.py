"""Deterministic split assignment for V17-H.

Reserved splits are never produced by hashing — only via explicit declaration.
Trainable rows without a declared split hash into DEVELOPMENT | VALIDATION.
"""
from __future__ import annotations

import hashlib

from backend.nexus_training_dataset_compiler.constants import (
    DATASET_SPLITS,
    RESERVED_SPLITS,
    SPLIT_SEED,
    TRAINABLE_SPLIT_WEIGHTS,
    TRAINABLE_SPLITS,
)


class SplitAssignmentError(Exception):
    """Fail-closed split rejection."""


def _stable_bucket(key: str, modulus: int) -> int:
    digest = hashlib.sha256(f"{SPLIT_SEED}:{key}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % modulus


def assign_trainable_split(sample_id: str, symbol: str, ts_ms: int) -> str:
    """Hash-stable DEVELOPMENT/VALIDATION assignment."""
    total = sum(w for _, w in TRAINABLE_SPLIT_WEIGHTS)
    bucket = _stable_bucket(f"{sample_id}|{symbol}|{ts_ms}", total)
    cursor = 0
    for name, weight in TRAINABLE_SPLIT_WEIGHTS:
        cursor += weight
        if bucket < cursor:
            return name
    return TRAINABLE_SPLIT_WEIGHTS[-1][0]


def resolve_split(
    *,
    sample_id: str,
    symbol: str,
    ts_ms: int,
    declared_split: str | None,
) -> str:
    """Resolve final split. Explicit reserved declarations are honored; hashing never invents reserved."""
    if declared_split is not None:
        split = str(declared_split).strip().upper()
        if split not in DATASET_SPLITS:
            raise SplitAssignmentError(f"unknown_split:{split}")
        return split
    return assign_trainable_split(sample_id, symbol, ts_ms)


def is_trainable(split: str) -> bool:
    return split in TRAINABLE_SPLITS


def assert_split_partition_integrity(splits: list[str] | tuple[str, ...]) -> None:
    """Every row must land in exactly one canonical split name."""
    for s in splits:
        if s not in DATASET_SPLITS:
            raise SplitAssignmentError(f"partition_integrity_fail:{s}")
        if s in RESERVED_SPLITS and s in TRAINABLE_SPLITS:
            raise SplitAssignmentError(f"split_both_reserved_and_trainable:{s}")


def deterministic_split_digest(assignments: dict[str, str]) -> str:
    blob = "|".join(f"{k}={assignments[k]}" for k in sorted(assignments))
    return hashlib.sha256(f"{SPLIT_SEED}:{blob}".encode("utf-8")).hexdigest()
