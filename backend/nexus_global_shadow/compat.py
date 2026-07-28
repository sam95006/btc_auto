"""Backward compatibility — fleet_id deprecated adapter only."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow.contracts import strip_fleet_id


def adapt_legacy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Read fleet_id if present, drop from formal schema, mark deprecated."""
    out = strip_fleet_id(payload)
    if "deprecated_fleet_id_ignored" in out:
        out["deprecated"] = True
    return out


def normalize_candidate_record(record: dict[str, Any]) -> dict[str, Any]:
    return adapt_legacy_payload(record)
