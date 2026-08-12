"""V17-G calculation hashing and deterministic JSON helpers."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def calculation_hash(
    *,
    feature_id: str,
    formula_id: str,
    feature_version: str,
    lookback: int,
    normalization: str,
    inputs_fingerprint: str,
    as_of: int,
) -> str:
    payload = {
        "feature_id": feature_id,
        "formula_id": formula_id,
        "feature_version": feature_version,
        "lookback": lookback,
        "normalization": normalization,
        "inputs_fingerprint": inputs_fingerprint,
        "as_of": as_of,
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def fingerprint_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> str:
    slim = [{k: r.get(k) for k in keys} for r in rows]
    return hashlib.sha256(canonical_json(slim).encode("utf-8")).hexdigest()
