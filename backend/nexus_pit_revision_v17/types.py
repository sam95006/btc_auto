"""Typed dual-time revision records for V17-D."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DualTimeStamp:
    """Four-axis point-in-time stamp.

    event_time: when the underlying event occurred
    available_time: when the value became knowable / publishable
    revision_time: when this specific revision was issued
    ingest_time: when NEXUS ingested the payload
    """

    event_time: int
    available_time: int
    revision_time: int
    ingest_time: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    def validate(self) -> None:
        for name, value in (
            ("event_time", self.event_time),
            ("available_time", self.available_time),
            ("revision_time", self.revision_time),
            ("ingest_time", self.ingest_time),
        ):
            if int(value) <= 0:
                raise ValueError(f"{name} must be positive epoch-ms")
        if self.available_time < self.event_time:
            # Late-arriving / delayed availability is allowed (available > event).
            # available < event is clock nonsense for this model.
            raise ValueError("available_time must be >= event_time")
        if self.revision_time < self.available_time:
            raise ValueError("revision_time must be >= available_time")
        if self.ingest_time < self.revision_time:
            raise ValueError("ingest_time must be >= revision_time")


@dataclass(frozen=True)
class RevisionRecord:
    """Immutable revision of a series observation or label."""

    revision_id: str
    series_id: str
    kind: str  # OBSERVATION | LABEL | BACKFILL | LATE_ARRIVING
    value: Any
    times: DualTimeStamp
    parent_revision_id: str | None = None
    label_name: str | None = None
    content_hash: str = ""
    fixture_only: bool = True
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["times"] = self.times.to_dict()
        d["tags"] = list(self.tags)
        return d

    @property
    def event_time(self) -> int:
        return self.times.event_time

    @property
    def available_time(self) -> int:
        return self.times.available_time

    @property
    def revision_time(self) -> int:
        return self.times.revision_time

    @property
    def ingest_time(self) -> int:
        return self.times.ingest_time


@dataclass(frozen=True)
class ResearchQuery:
    """Research query contract — AS_KNOWN_AT is mandatory."""

    series_id: str
    as_known_at: int
    event_time: int | None = None
    label_name: str | None = None
    allow_latest_revision: bool = False  # always refused for past backtests
    query_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueryResult:
    status: str
    series_id: str
    as_known_at: int
    value: Any = None
    revision_id: str | None = None
    selected_revision: dict[str, Any] | None = None
    lineage: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    reason: str = ""
    leakage_blocked: bool = False
    fixture_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lineage"] = list(self.lineage)
        return d
