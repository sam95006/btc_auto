"""Checksum helpers for formal qualification infrastructure (synthetic-safe).

Produces candidate / semantic / parameter digests. Does not select or promote
strategies. Does not execute Walk-forward or OOS.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def candidate_identity_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Stable identity fields for a frozen candidate (synthetic fixtures OK)."""
    keys = (
        "candidate_id",
        "candidate_label",
        "strategy_family",
        "economic_mechanism",
        "parameter_source",
        "preregistration_timestamp",
        "fixture_only",
    )
    return {k: deepcopy(candidate.get(k)) for k in keys}


def semantic_identity_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Economic/semantic identity — excludes run ids and timestamps."""
    keys = (
        "strategy_family",
        "economic_mechanism",
        "required_data_capabilities",
        "eligible_symbol_profile",
        "eligible_regimes",
        "context_timeframe",
        "event_timeframe",
        "entry_timeframe",
        "parameter_source",
        "economic_rationale",
    )
    return {k: deepcopy(candidate.get(k)) for k in keys}


def parameter_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Frozen parameter body only."""
    params = candidate.get("parameters")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise TypeError("parameters_must_be_dict")
    return deepcopy(params)


def compute_candidate_checksum(candidate: dict[str, Any]) -> str:
    return sha_obj(candidate_identity_payload(candidate))


def compute_semantic_checksum(candidate: dict[str, Any]) -> str:
    return sha_obj(semantic_identity_payload(candidate))


def compute_parameter_checksum(candidate: dict[str, Any]) -> str:
    return sha_obj(parameter_payload(candidate))


def stamp_checksums(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with all three checksums stamped (does not mutate input)."""
    out = deepcopy(candidate)
    out["candidate_checksum"] = compute_candidate_checksum(out)
    out["semantic_checksum"] = compute_semantic_checksum(out)
    out["parameter_checksum"] = compute_parameter_checksum(out)
    return out


def validate_checksums(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if candidate.get("candidate_checksum") != compute_candidate_checksum(candidate):
        errors.append("candidate_checksum_mismatch")
    if candidate.get("semantic_checksum") != compute_semantic_checksum(candidate):
        errors.append("semantic_checksum_mismatch")
    if candidate.get("parameter_checksum") != compute_parameter_checksum(candidate):
        errors.append("parameter_checksum_mismatch")
    return errors
