"""Field-level provenance helpers for V18.2.27 founder demo monitor."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_source_timestamp(raw: dict[str, Any]) -> str | None:
    for key in ("source_timestamp", "generated_at", "generatedAt", "as_of", "asOf"):
        val = raw.get(key)
        if val:
            return str(val).strip() or None
    return None


def freshness_seconds(source_timestamp: str | None) -> float | None:
    if not source_timestamp:
        return None
    text = source_timestamp.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
    return max(0.0, delta.total_seconds())


def field_provenance(
    *,
    value: Any,
    source_timestamp: str | None,
    lane: str | None,
    provenance: str,
    freshness_sec: float | None = None,
) -> dict[str, Any]:
    fresh = freshness_sec
    if fresh is None and source_timestamp:
        fresh = freshness_seconds(source_timestamp)
    return {
        "value": value,
        "source_timestamp": source_timestamp,
        "freshness_sec": fresh,
        "lane": lane,
        "provenance": provenance,
    }


def build_field_provenance_map(
    *,
    source_timestamp: str | None,
    lane: str | None,
    provenance: str,
    fields: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    fresh = freshness_seconds(source_timestamp)
    out: dict[str, dict[str, Any]] = {}
    for name, value in fields.items():
        out[name] = field_provenance(
            value=value,
            source_timestamp=source_timestamp,
            lane=lane,
            provenance=provenance,
            freshness_sec=fresh,
        )
    return out
