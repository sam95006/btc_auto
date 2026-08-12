"""V17-G Gold Feature Factory — compute all features from a market fixture."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from backend.nexus_gold_feature_factory.catalog import feature_catalog, formula_authority_map
from backend.nexus_gold_feature_factory.constants import (
    FEATURE_IDS,
    FEATURE_SCHEMA_VERSION,
    FEATURE_VERSION,
    HARD_BANS,
    LANE,
    REQUIRED_METADATA_FIELDS,
)
from backend.nexus_gold_feature_factory.formulas import FORMULA_DISPATCH
from backend.nexus_gold_feature_factory.guards import (
    assert_no_silent_forward_fill,
    assert_observation_marks_missing,
    assert_single_authoritative_formula,
    owned_ast_has_no_future_label_assignment,
    reject_duplicate_authority,
)
from backend.nexus_gold_feature_factory.hashing import canonical_json
from backend.nexus_gold_feature_factory.types import FeatureObservation


def compute_feature(
    feature_id: str,
    market: dict[str, Any],
    *,
    as_of: Optional[int] = None,
) -> FeatureObservation:
    if feature_id not in FORMULA_DISPATCH:
        raise KeyError(f"unknown_feature:{feature_id}")
    # Enforce single authority at call time
    reject_duplicate_authority(feature_id, formula_authority_map()[feature_id])
    cutoff = int(as_of if as_of is not None else market["as_of_default"])
    return FORMULA_DISPATCH[feature_id](market, as_of=cutoff)


def compute_all_features(
    market: dict[str, Any],
    *,
    as_of: Optional[int] = None,
) -> dict[str, Any]:
    cutoff = int(as_of if as_of is not None else market["as_of_default"])
    features: dict[str, dict[str, Any]] = {}
    for fid in FEATURE_IDS:
        obs = compute_feature(fid, market, as_of=cutoff)
        d = obs.to_dict()
        for field in REQUIRED_METADATA_FIELDS:
            if field not in d:
                raise RuntimeError(f"missing_metadata:{fid}:{field}")
        assert_observation_marks_missing(d)
        features[fid] = d

    bundle = {
        "schema": "v17_g_gold_feature_bundle",
        "lane": LANE,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_version": FEATURE_VERSION,
        "as_of": cutoff,
        "evidence_class": market.get("evidence_class", "fixture"),
        "primary_symbol": market.get("primary_symbol"),
        "features": features,
        "feature_count": len(features),
        "predictive_edge_claimed": False,
        "hard_bans": HARD_BANS,
        "catalog": feature_catalog(),
        "authoritative_formulas": formula_authority_map(),
        "exchange_write_attempt_count": int(market.get("exchange_write_attempt_count", 0)),
        "mainnet": bool(market.get("mainnet", False)),
    }
    bundle["bundle_checksum"] = hashlib.sha256(
        canonical_json({k: v for k, v in bundle.items() if k != "bundle_checksum"}).encode("utf-8")
    ).hexdigest()
    return bundle


def prove_pit_excludes_future(market: dict[str, Any], *, as_of: int) -> dict[str, Any]:
    """Recompute at as_of and verify no observation used exchange_ts > as_of."""
    bundle = compute_all_features(market, as_of=as_of)
    # Structural proof: every available_at <= as_of when present; as_of field equals cutoff.
    violations: list[str] = []
    for fid, obs in bundle["features"].items():
        if obs["as_of"] != as_of:
            violations.append(f"{fid}:as_of_mismatch")
        aa = obs.get("available_at")
        if aa is not None and int(aa) > as_of:
            violations.append(f"{fid}:available_at_after_as_of")
    return {
        "as_of": as_of,
        "ok": len(violations) == 0,
        "violations": violations,
        "feature_count": bundle["feature_count"],
    }


def verify_deterministic_replay(market: dict[str, Any], *, as_of: Optional[int] = None) -> dict[str, Any]:
    a = compute_all_features(market, as_of=as_of)
    b = compute_all_features(market, as_of=as_of)
    return {
        "ok": a["bundle_checksum"] == b["bundle_checksum"],
        "checksum_a": a["bundle_checksum"],
        "checksum_b": b["bundle_checksum"],
    }


def run_factory_guards(root: Any) -> dict[str, Any]:
    from pathlib import Path

    root_path = Path(root)
    assert_no_silent_forward_fill(root_path)
    auth = assert_single_authoritative_formula()
    future_hits = owned_ast_has_no_future_label_assignment(root_path)
    return {
        "silent_forward_fill_ok": True,
        "single_authority_ok": True,
        "authoritative_formulas": auth,
        "future_label_ast_hits": future_hits,
        "future_label_ast_ok": len(future_hits) == 0,
    }


def fingerprint_bundle(bundle: dict[str, Any]) -> str:
    return str(bundle.get("bundle_checksum") or "")
