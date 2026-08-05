"""Lineage records for every public-safe live value (PUB-C)."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.nexus_public_live_data.constants import (
    COMPLETENESS_BLOCKED,
    COMPLETENESS_COMPLETE,
    COMPLETENESS_DEMO,
    COMPLETENESS_MISSING,
    COMPLETENESS_PARTIAL,
    DEGRADED_SECONDS,
    FRESH_SECONDS,
    LINEAGE_REQUIRED_KEYS,
    MODE_FIXTURE,
    MODE_LIVE,
    STALE_SECONDS,
    STATE_BLOCKED,
    STATE_DEGRADED,
    STATE_DEMO,
    STATE_FRESH,
    STATE_LIVE,
    STATE_STALE,
    STATE_UNAVAILABLE,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime | None = None) -> str:
    value = dt or utc_now()
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def freshness_from_age(age_seconds: float | None, *, mode: str, available: bool, blocked: bool = False) -> str:
    if mode == MODE_FIXTURE:
        return STATE_DEMO
    if blocked:
        return STATE_BLOCKED
    if not available or age_seconds is None:
        return STATE_UNAVAILABLE
    if age_seconds <= FRESH_SECONDS:
        return STATE_LIVE if age_seconds <= 5.0 else STATE_FRESH
    if age_seconds <= STALE_SECONDS:
        return STATE_STALE
    if age_seconds <= DEGRADED_SECONDS:
        return STATE_DEGRADED
    return STATE_STALE


def completeness_for(*, mode: str, value: Any, blocked: bool = False, partial: bool = False) -> str:
    if mode == MODE_FIXTURE:
        return COMPLETENESS_DEMO
    if blocked:
        return COMPLETENESS_BLOCKED
    if value is None:
        return COMPLETENESS_MISSING
    if partial:
        return COMPLETENESS_PARTIAL
    return COMPLETENESS_COMPLETE


def make_lineage_id(field_id: str, source_system: str, as_of: str | None, retrieved_at: str) -> str:
    raw = f"{field_id}|{source_system}|{as_of or 'none'}|{retrieved_at}|{uuid.uuid4().hex[:8]}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"lin_{digest}"


@dataclass
class LineageBoundValue:
    """One public-safe field binding with mandatory lineage metadata."""

    field_id: str
    value: Any
    unit: str | None
    mode: str
    source_system: str
    source_endpoint: str
    source_field: str
    as_of: str | None
    retrieved_at: str
    freshness: str
    completeness: str
    lineage_id: str
    fallback: str
    quality: str
    demo_data: bool = False
    display_state: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        body = asdict(self)
        for key in LINEAGE_REQUIRED_KEYS:
            if key not in body or body[key] is None and key != "as_of":
                # as_of may be null when UNAVAILABLE; all other required keys must exist
                if key == "as_of":
                    continue
                raise ValueError(f"missing lineage key: {key}")
        if self.mode == MODE_FIXTURE and not self.demo_data:
            raise ValueError("fixture mode requires demo_data=True and DEMO_DATA banner")
        if self.mode == MODE_LIVE and self.demo_data:
            raise ValueError("live mode must not carry DEMO_DATA")
        return body


def unavailable_bound(
    *,
    field_id: str,
    source_system: str,
    source_endpoint: str,
    source_field: str,
    fallback: str,
    reason: str,
    blocked: bool = False,
    retrieved_at: str | None = None,
) -> LineageBoundValue:
    retrieved = retrieved_at or utc_iso()
    freshness = STATE_BLOCKED if blocked else STATE_UNAVAILABLE
    completeness = COMPLETENESS_BLOCKED if blocked else COMPLETENESS_MISSING
    display = STATE_BLOCKED if blocked else STATE_UNAVAILABLE
    return LineageBoundValue(
        field_id=field_id,
        value=None,
        unit=None,
        mode=MODE_LIVE,
        source_system=source_system,
        source_endpoint=source_endpoint,
        source_field=source_field,
        as_of=None,
        retrieved_at=retrieved,
        freshness=freshness,
        completeness=completeness,
        lineage_id=make_lineage_id(field_id, source_system, None, retrieved),
        fallback=fallback,
        quality=reason,
        demo_data=False,
        display_state=display,
        notes=[reason, f"display={display}"],
    )


def demo_bound(
    *,
    field_id: str,
    value: Any,
    unit: str | None,
    source_field: str,
    as_of: str,
    note: str = "Fixture catalog value",
) -> LineageBoundValue:
    retrieved = utc_iso()
    return LineageBoundValue(
        field_id=field_id,
        value=value,
        unit=unit,
        mode=MODE_FIXTURE,
        source_system="FIXTURE_CATALOG",
        source_endpoint="fixture://demo_catalog.json",
        source_field=source_field,
        as_of=as_of,
        retrieved_at=retrieved,
        freshness=STATE_DEMO,
        completeness=COMPLETENESS_DEMO,
        lineage_id=make_lineage_id(field_id, "FIXTURE_CATALOG", as_of, retrieved),
        fallback="none_fixture_primary",
        quality="DEMO_DATA",
        demo_data=True,
        display_state=STATE_DEMO,
        notes=["DEMO_DATA", note],
    )


def assert_lineage_complete(payload: dict[str, Any]) -> None:
    for key in LINEAGE_REQUIRED_KEYS:
        if key not in payload:
            raise ValueError(f"lineage incomplete: missing {key}")
