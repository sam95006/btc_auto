"""Write-once cryptographic lineage seal with anti-regeneration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_oos_seal_control.constants import (
    SEAL_STATUS_PLAN_SEALED_NOT_RESERVED,
    SEAL_STATUS_REGENERATION_REJECTED,
    SEAL_STATUS_WRITE_ONCE_VIOLATION,
)
from backend.nexus_oos_seal_control.intervals import sha_obj


@dataclass
class SealLineageStore:
    """In-memory write-once seal lineage authority."""

    seals: dict[str, dict[str, Any]] = field(default_factory=dict)

    def reset(self) -> None:
        self.seals.clear()


_DEFAULT_LINEAGE = SealLineageStore()


def reset_seal_lineage(store: SealLineageStore | None = None) -> None:
    (store or _DEFAULT_LINEAGE).reset()


def build_lineage_seal(
    *,
    plan: dict[str, Any],
    bindings: dict[str, Any],
    lineage_key: str = "default",
    store: SealLineageStore | None = None,
    force_overwrite: bool = False,
) -> dict[str, Any]:
    """Seal a planned (not reserved) OOS control document.

    Write-once: second write with mutated plan/bindings fails closed.
    Identical recompute returns the persisted seal.
    force_overwrite is always refused (anti-regeneration / write-once).
    """
    lineage = store if store is not None else _DEFAULT_LINEAGE
    seal_payload = {
        "plan_checksum": plan["plan_checksum"],
        "bindings_checksum": bindings["bindings_checksum"],
        "candidate_checksum": bindings["candidate"]["candidate_checksum"],
        "code_checksum": bindings["code"]["code_checksum"],
        "parameter_checksum": bindings["parameter"]["parameter_checksum"],
        "dataset_semantic_checksum": bindings["dataset"]["dataset_semantic_checksum"],
        "status": SEAL_STATUS_PLAN_SEALED_NOT_RESERVED,
        "fixture_only": True,
        "oos_reserved": False,
        "oos_downloaded": False,
        "oos_executed": False,
        "oos_consumed": False,
    }
    computed_seal = sha_obj(seal_payload)

    if force_overwrite:
        return {
            **seal_payload,
            "seal_algorithm": "sha256_json_canonical",
            "seal": None,
            "status": SEAL_STATUS_WRITE_ONCE_VIOLATION,
            "allowed": False,
            "fail_closed": True,
            "write_once": True,
            "anti_regeneration": True,
            "lineage_key": lineage_key,
            "reason": "FORCE_OVERWRITE_REFUSED",
            "computed_seal_rejected": computed_seal,
        }

    prior = lineage.seals.get(lineage_key)
    if prior is not None:
        mutated = (
            prior["plan_checksum"] != seal_payload["plan_checksum"]
            or prior["bindings_checksum"] != seal_payload["bindings_checksum"]
            or prior["candidate_checksum"] != seal_payload["candidate_checksum"]
            or prior["dataset_semantic_checksum"] != seal_payload["dataset_semantic_checksum"]
            or prior["seal"] != computed_seal
        )
        if mutated:
            return {
                **seal_payload,
                "seal_algorithm": "sha256_json_canonical",
                "seal": None,
                "status": SEAL_STATUS_REGENERATION_REJECTED,
                "prior_seal": prior["seal"],
                "computed_seal_rejected": computed_seal,
                "allowed": False,
                "fail_closed": True,
                "write_once": True,
                "anti_regeneration": True,
                "lineage_key": lineage_key,
            }
        return {
            **seal_payload,
            "seal_algorithm": "sha256_json_canonical",
            "seal": prior["seal"],
            "allowed": True,
            "fail_closed": False,
            "write_once": True,
            "anti_regeneration": True,
            "lineage_key": lineage_key,
            "lineage_verified": True,
        }

    result = {
        **seal_payload,
        "seal_algorithm": "sha256_json_canonical",
        "seal": computed_seal,
        "allowed": True,
        "fail_closed": False,
        "write_once": True,
        "anti_regeneration": True,
        "lineage_key": lineage_key,
        "lineage_verified": True,
    }
    lineage.seals[lineage_key] = {
        "seal": computed_seal,
        "plan_checksum": seal_payload["plan_checksum"],
        "bindings_checksum": seal_payload["bindings_checksum"],
        "candidate_checksum": seal_payload["candidate_checksum"],
        "dataset_semantic_checksum": seal_payload["dataset_semantic_checksum"],
        "status": SEAL_STATUS_PLAN_SEALED_NOT_RESERVED,
    }
    return result
