"""Checksum helpers for V13-F qualification dry-run (synthetic-safe)."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def semantic_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "semantic_mechanism_id",
        "strategy_family",
        "economic_mechanism",
        "discovery_label",
        "required_data_capabilities",
        "eligible_symbol_profile",
        "eligible_regimes",
        "parameter_source",
        "cost_model_version",
    )
    return {k: deepcopy(candidate.get(k)) for k in keys}


def parameter_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    params = candidate.get("parameters")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise TypeError("parameters_must_be_dict")
    return deepcopy(params)


def code_payload(candidate: dict[str, Any], *, code_ref_digest: str | None = None) -> dict[str, Any]:
    return {
        "code_ref": candidate.get("code_ref"),
        "code_ref_digest": code_ref_digest or candidate.get("code_ref_digest"),
        "factory_version": candidate.get("factory_version"),
        "implementation_fingerprint": candidate.get("implementation_fingerprint"),
    }


def dataset_payload(candidate: dict[str, Any], market: dict[str, Any] | None = None) -> dict[str, Any]:
    market = market or {}
    return {
        "dataset_ref": candidate.get("dataset_ref"),
        "dataset_lineage": deepcopy(candidate.get("dataset_lineage")),
        "development_interval": deepcopy(candidate.get("development_interval")),
        "universe_checksum": market.get("universe_checksum"),
        "as_of_ms": market.get("as_of_ms") or candidate.get("as_of_ms"),
        "availability_timestamp_ms": market.get("availability_timestamp_ms"),
        "retrieval_timestamp_ms": market.get("retrieval_timestamp_ms"),
    }


def compute_semantic_checksum(candidate: dict[str, Any]) -> str:
    return sha_obj(semantic_payload(candidate))


def compute_parameter_checksum(candidate: dict[str, Any]) -> str:
    return sha_obj(parameter_payload(candidate))


def compute_code_checksum(candidate: dict[str, Any], *, code_ref_digest: str | None = None) -> str:
    return sha_obj(code_payload(candidate, code_ref_digest=code_ref_digest))


def compute_dataset_checksum(
    candidate: dict[str, Any],
    market: dict[str, Any] | None = None,
) -> str:
    return sha_obj(dataset_payload(candidate, market))


def stamp_all_checksums(
    candidate: dict[str, Any],
    *,
    market: dict[str, Any] | None = None,
    code_ref_digest: str | None = None,
) -> dict[str, Any]:
    out = deepcopy(candidate)
    out["semantic_checksum"] = compute_semantic_checksum(out)
    out["parameter_checksum"] = compute_parameter_checksum(out)
    out["code_checksum"] = compute_code_checksum(out, code_ref_digest=code_ref_digest)
    out["dataset_checksum"] = compute_dataset_checksum(out, market)
    return out


def validate_checksums(
    candidate: dict[str, Any],
    *,
    market: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if candidate.get("semantic_checksum") != compute_semantic_checksum(candidate):
        errors.append("semantic_checksum_mismatch")
    if candidate.get("parameter_checksum") != compute_parameter_checksum(candidate):
        errors.append("parameter_checksum_mismatch")
    if candidate.get("code_checksum") != compute_code_checksum(candidate):
        errors.append("code_checksum_mismatch")
    if candidate.get("dataset_checksum") != compute_dataset_checksum(candidate, market):
        errors.append("dataset_checksum_mismatch")
    return errors
