"""Freeze rules for formal Walk-forward plans (plan-only; never applied at runtime)."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def build_parameter_freeze_rules(candidate: dict[str, Any]) -> dict[str, Any]:
    params = candidate.get("parameters") or {}
    checksum = candidate.get("parameter_checksum") or _sha(params)
    return {
        "rule_kind": "parameter_freeze",
        "frozen": False,  # plan only — freeze not applied
        "planned": True,
        "parameter_checksum": checksum,
        "parameters_snapshot": dict(params),
        "mutation_allowed_after_plan": False,
        "note": "Parameters must freeze before any future formal WF execution; not applied here.",
        "executed": False,
    }


def build_candidate_freeze_rules(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_kind": "candidate_freeze",
        "frozen": False,
        "planned": True,
        "candidate_id": candidate.get("candidate_id"),
        "semantic_checksum": candidate.get("semantic_checksum"),
        "selection_allowed": False,
        "promotion_allowed": False,
        "note": "Candidate freeze is planned only; formal freeze/selection remains blocked.",
        "executed": False,
    }


def build_cost_version_freeze(candidate: dict[str, Any]) -> dict[str, Any]:
    cost_version = candidate.get("cost_version") or candidate.get("cost_model_version") or "UNPINNED"
    return {
        "rule_kind": "cost_version_freeze",
        "frozen": False,
        "planned": True,
        "cost_version": cost_version,
        "note": "Cost model version must be pinned before formal WF; pin not applied here.",
        "executed": False,
    }


def build_code_version_freeze(candidate: dict[str, Any], *, code_version: str) -> dict[str, Any]:
    code_checksum = candidate.get("code_checksum") or _sha(
        {"code_ref": candidate.get("code_ref"), "code_version": code_version}
    )
    return {
        "rule_kind": "code_version_freeze",
        "frozen": False,
        "planned": True,
        "code_version": code_version,
        "code_checksum": code_checksum,
        "code_ref": candidate.get("code_ref"),
        "note": "Code version must freeze before formal WF; freeze not applied here.",
        "executed": False,
    }


def build_dataset_freeze(candidate: dict[str, Any]) -> dict[str, Any]:
    dataset_id = candidate.get("dataset_id") or candidate.get("dataset_ref") or "UNPINNED"
    dataset_checksum = candidate.get("dataset_checksum") or _sha({"dataset_id": dataset_id})
    return {
        "rule_kind": "dataset_freeze",
        "frozen": False,
        "planned": True,
        "dataset_id": dataset_id,
        "dataset_checksum": dataset_checksum,
        "category_required": "DEVELOPMENT",
        "oos_reserved_forbidden": True,
        "oos_untouched_forbidden": True,
        "note": "Dataset freeze plans DEVELOPMENT-only data; OOS remains untouched.",
        "executed": False,
    }


def build_all_freeze_rules(
    candidate: dict[str, Any],
    *,
    code_version: str,
) -> dict[str, Any]:
    return {
        "parameter_freeze_rules": build_parameter_freeze_rules(candidate),
        "candidate_freeze_rules": build_candidate_freeze_rules(candidate),
        "cost_version_freeze": build_cost_version_freeze(candidate),
        "code_version_freeze": build_code_version_freeze(candidate, code_version=code_version),
        "dataset_freeze": build_dataset_freeze(candidate),
        "any_freeze_applied": False,
        "formal_walk_forward_executed": False,
    }
