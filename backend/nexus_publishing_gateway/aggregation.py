"""Aggregation thresholds — suppress thin / identifying slices."""
from __future__ import annotations

from typing import Any

from backend.nexus_publishing_gateway.constants import (
    AGGREGATION_MIN_COUNT,
    CONFIDENCE_BUCKETS,
)
from backend.nexus_publishing_gateway.exceptions import AggregationThresholdError


def bucket_confidence(raw: Any) -> str:
    """Map numeric or free-form confidence into coarse public bands."""
    if raw is None:
        return "UNAVAILABLE"
    if isinstance(raw, str):
        up = raw.strip().upper()
        if up in CONFIDENCE_BUCKETS:
            return up
        return "UNAVAILABLE"
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return "UNAVAILABLE"
    if val < 0.34:
        return "LOW"
    if val < 0.67:
        return "MEDIUM"
    return "HIGH"


def enforce_aggregation_threshold(
    items: list[Any] | tuple[Any, ...] | None,
    *,
    min_count: int = AGGREGATION_MIN_COUNT,
    label: str = "items",
) -> list[Any]:
    """Require at least min_count items before publishing a collection slice.

    Below threshold → raise (fail-closed) so callers cannot leak thin cohorts.
    """
    seq = list(items or [])
    if len(seq) < min_count:
        raise AggregationThresholdError(
            f"aggregation_threshold:{label}:count={len(seq)}:min={min_count}"
        )
    return seq


def apply_public_aggregations(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize confidence and suppress under-threshold nested collections."""
    out = dict(payload)
    if "confidence_calibration" in out:
        out["confidence_calibration"] = bucket_confidence(out["confidence_calibration"])
        out["confidence_band"] = out["confidence_calibration"]

    for key in ("evidence_summaries", "risk_alerts", "contradicting_evidence", "symbols"):
        if key in out and isinstance(out[key], list):
            # Empty lists are allowed (availability messaging); non-empty must meet threshold
            # OR be replaced with a coarse count-only bucket to avoid thin leaks.
            if 0 < len(out[key]) < AGGREGATION_MIN_COUNT:
                out[key] = {
                    "bucket": "SUPPRESSED_BELOW_THRESHOLD",
                    "count": len(out[key]),
                    "status": "AGGREGATED",
                    "message": "detail_suppressed",
                }
    return out
