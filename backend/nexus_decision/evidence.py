"""Evidence completeness validation for Decision Lifecycle V11.

Fail-closed on missing, stale, mismatched, or corrupted evidence.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


REQUIRED_EVIDENCE_MIN = 1
FRESHNESS_MAX_AGE_SECONDS_DEFAULT = 300.0


class EvidenceValidationError(ValueError):
    """Evidence incomplete, stale, or corrupted — fail closed."""


def hash_evidence_blob(blob: str | bytes) -> str:
    if isinstance(blob, str):
        blob = blob.encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def validate_evidence_completeness(
    *,
    evidence_ids: list[str],
    evidence_hashes: list[str],
    data_freshness: dict[str, Any],
    data_completeness: dict[str, Any],
    evidence_blobs: dict[str, str | bytes] | None = None,
    max_age_seconds: float = FRESHNESS_MAX_AGE_SECONDS_DEFAULT,
    require_complete: bool = True,
) -> dict[str, Any]:
    """Validate evidence contract. Returns a summary dict on success."""
    if not evidence_ids:
        raise EvidenceValidationError("evidence_ids_empty")
    if len(evidence_ids) < REQUIRED_EVIDENCE_MIN:
        raise EvidenceValidationError("evidence_below_minimum")
    if len(evidence_ids) != len(evidence_hashes):
        raise EvidenceValidationError(
            f"evidence_length_mismatch:{len(evidence_ids)}!={len(evidence_hashes)}"
        )
    if len(set(evidence_ids)) != len(evidence_ids):
        raise EvidenceValidationError("duplicate_evidence_ids")
    if any(not eid for eid in evidence_ids):
        raise EvidenceValidationError("empty_evidence_id")
    if any(not h or len(h) != 64 for h in evidence_hashes):
        raise EvidenceValidationError("invalid_evidence_hash")

    completeness_ratio = float(data_completeness.get("ratio", 0.0))
    required_fields = list(data_completeness.get("required_fields") or [])
    present_fields = list(data_completeness.get("present_fields") or [])
    if require_complete:
        if completeness_ratio < 1.0:
            raise EvidenceValidationError(f"data_incomplete:ratio={completeness_ratio}")
        missing = [f for f in required_fields if f not in present_fields]
        if missing:
            raise EvidenceValidationError(f"data_fields_missing:{missing}")

    age = data_freshness.get("age_seconds")
    if age is None:
        raise EvidenceValidationError("freshness_age_missing")
    age_f = float(age)
    if age_f < 0:
        raise EvidenceValidationError("freshness_age_negative")
    if age_f > max_age_seconds:
        raise EvidenceValidationError(f"evidence_stale:age={age_f}>max={max_age_seconds}")
    if data_freshness.get("stale") is True:
        raise EvidenceValidationError("freshness_flag_stale")

    if evidence_blobs is not None:
        for eid, expected in zip(evidence_ids, evidence_hashes):
            if eid not in evidence_blobs:
                raise EvidenceValidationError(f"evidence_blob_missing:{eid}")
            actual = hash_evidence_blob(evidence_blobs[eid])
            if actual != expected:
                raise EvidenceValidationError(f"evidence_hash_mismatch:{eid}")

    return {
        "ok": True,
        "evidence_count": len(evidence_ids),
        "completeness_ratio": completeness_ratio,
        "age_seconds": age_f,
        "max_age_seconds": max_age_seconds,
    }


def evidence_binding_hash(evidence_ids: list[str], evidence_hashes: list[str]) -> str:
    """Stable binding over id/hash pairs — detects post-observe tampering."""
    pairs = sorted(zip(evidence_ids, evidence_hashes), key=lambda x: x[0])
    payload = json.dumps(pairs, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_evidence_loss(
    *,
    expected_ids: list[str],
    expected_hashes: list[str],
    actual_ids: list[str],
    actual_hashes: list[str],
) -> list[str]:
    """Return loss descriptors. Empty list means no loss detected."""
    losses: list[str] = []
    if len(actual_ids) < len(expected_ids):
        losses.append(f"count_drop:{len(expected_ids)}->{len(actual_ids)}")
    expected_map = dict(zip(expected_ids, expected_hashes))
    actual_map = dict(zip(actual_ids, actual_hashes))
    for eid, eh in expected_map.items():
        if eid not in actual_map:
            losses.append(f"missing_id:{eid}")
        elif actual_map[eid] != eh:
            losses.append(f"hash_changed:{eid}")
    return losses
