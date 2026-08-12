"""Research-family lineage for development candidates (not qualification)."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from backend.nexus_research_validation.constants import (
    CAMPAIGN_ID,
    DEVELOPMENT_INTERVAL_ID,
    RESEARCH_FAMILIES,
)


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_lineage(
    *,
    candidate_id: str,
    research_family: str,
    mechanism_semantic_id: str,
    parent_experiment_id: str | None,
    parameter_checksum: str,
    feature_version: str,
    universe_checksum: str,
    data_fixture_id: str,
    random_seed: int,
    cost_version: str = "COST_MODEL_CONTRACT_CONSUMER_V14D_SYNTHETIC",
) -> dict[str, Any]:
    if research_family not in RESEARCH_FAMILIES:
        raise ValueError(f"unknown research_family: {research_family}")
    record = {
        "schema": "v14_d_research_family_lineage",
        "campaign_id": CAMPAIGN_ID,
        "candidate_id": candidate_id,
        "research_family": research_family,
        "mechanism_semantic_id": mechanism_semantic_id,
        "parent_experiment_id": parent_experiment_id,
        "parameter_checksum": parameter_checksum,
        "feature_version": feature_version,
        "universe_checksum": universe_checksum,
        "data_fixture_id": data_fixture_id,
        "development_interval_id": DEVELOPMENT_INTERVAL_ID,
        "random_seed": int(random_seed),
        "cost_version": cost_version,
        "development_only": True,
        "oos_consumed": False,
        "formal_walk_forward": False,
        "qualification_claim": False,
    }
    record["lineage_digest"] = _digest(record)
    return record


def lineage_index(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, list[str]] = {f: [] for f in RESEARCH_FAMILIES}
    by_parent: dict[str, list[str]] = {}
    digests: list[str] = []
    for r in records:
        fam = str(r["research_family"])
        cid = str(r["candidate_id"])
        by_family.setdefault(fam, []).append(cid)
        parent = r.get("parent_experiment_id")
        if parent:
            by_parent.setdefault(str(parent), []).append(cid)
        digests.append(str(r.get("lineage_digest", "")))
    return {
        "schema": "v14_d_lineage_index",
        "candidate_count": len(records),
        "by_family": {k: sorted(v) for k, v in by_family.items() if v},
        "by_parent": {k: sorted(v) for k, v in by_parent.items()},
        "family_coverage": {
            f: len(by_family.get(f, [])) for f in RESEARCH_FAMILIES
        },
        "digest_checksum": _digest({"digests": sorted(digests)}),
        "development_only": True,
        "not_oos_claim": True,
    }
