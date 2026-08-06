"""Point-in-time revision store and research query API (AS_KNOWN_AT mandatory)."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from backend.nexus_pit_revision_v17.hard_bans import (
    FutureLeakageError,
    MissingAsKnownAtError,
    TodayRevisionForPastBacktestError,
    UnavailableAtTimeError,
    refuse_future_leakage,
    refuse_missing_as_known_at,
    refuse_today_revision_for_past_backtest,
    refuse_unavailable_silent_fill,
)
from backend.nexus_pit_revision_v17.types import (
    DualTimeStamp,
    QueryResult,
    ResearchQuery,
    RevisionRecord,
)


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def is_visible_as_known_at(record: RevisionRecord, *, as_known_at: int) -> bool:
    """A revision is visible only when both availability and revision are known."""
    if as_known_at <= 0:
        return False
    return (
        record.available_time <= as_known_at
        and record.revision_time <= as_known_at
        and record.ingest_time <= as_known_at
    )


def assert_no_future_axes(record: RevisionRecord, *, as_known_at: int) -> None:
    for axis, value in (
        ("available_time", record.available_time),
        ("revision_time", record.revision_time),
        ("ingest_time", record.ingest_time),
    ):
        if value > as_known_at:
            refuse_future_leakage(axis=axis, value=value, as_known_at=as_known_at)


class PitRevisionStore:
    """Append-oriented in-memory revision store with dual-time visibility."""

    def __init__(self) -> None:
        self._by_id: dict[str, RevisionRecord] = {}
        self._by_series: dict[str, list[str]] = {}

    def ingest(self, record: RevisionRecord) -> RevisionRecord:
        record.times.validate()
        if record.kind not in {"OBSERVATION", "LABEL", "BACKFILL", "LATE_ARRIVING"}:
            raise ValueError(f"unknown kind: {record.kind}")
        if record.parent_revision_id and record.parent_revision_id not in self._by_id:
            raise ValueError(f"missing parent revision: {record.parent_revision_id}")
        stamped = RevisionRecord(
            revision_id=record.revision_id,
            series_id=record.series_id,
            kind=record.kind,
            value=record.value,
            times=record.times,
            parent_revision_id=record.parent_revision_id,
            label_name=record.label_name,
            content_hash=record.content_hash or _sha_obj(record.to_dict()),
            fixture_only=record.fixture_only,
            notes=record.notes,
            tags=record.tags,
        )
        if stamped.revision_id in self._by_id:
            raise ValueError(f"duplicate revision_id: {stamped.revision_id}")
        self._by_id[stamped.revision_id] = stamped
        self._by_series.setdefault(stamped.series_id, []).append(stamped.revision_id)
        return stamped

    def ingest_many(self, records: Iterable[RevisionRecord]) -> list[RevisionRecord]:
        return [self.ingest(r) for r in records]

    def get(self, revision_id: str) -> RevisionRecord | None:
        return self._by_id.get(revision_id)

    def series_revisions(self, series_id: str) -> list[RevisionRecord]:
        return [self._by_id[rid] for rid in self._by_series.get(series_id, [])]

    def revision_lineage(self, revision_id: str) -> list[RevisionRecord]:
        """Walk parent chain from root → tip for the given revision."""
        node = self._by_id.get(revision_id)
        if node is None:
            return []
        chain: list[RevisionRecord] = [node]
        seen = {revision_id}
        while node.parent_revision_id:
            parent = self._by_id.get(node.parent_revision_id)
            if parent is None or parent.revision_id in seen:
                break
            chain.append(parent)
            seen.add(parent.revision_id)
            node = parent
        chain.reverse()
        return chain

    def latest_revision(self, series_id: str) -> RevisionRecord | None:
        revs = self.series_revisions(series_id)
        if not revs:
            return None
        return max(revs, key=lambda r: (r.revision_time, r.ingest_time, r.revision_id))

    def visible_revisions(self, series_id: str, *, as_known_at: int) -> list[RevisionRecord]:
        return [
            r
            for r in self.series_revisions(series_id)
            if is_visible_as_known_at(r, as_known_at=as_known_at)
        ]

    def select_as_known_at(
        self,
        series_id: str,
        *,
        as_known_at: int,
        label_name: str | None = None,
        event_time: int | None = None,
    ) -> RevisionRecord | None:
        """Pick the newest revision that was knowable at AS_KNOWN_AT."""
        candidates = self.visible_revisions(series_id, as_known_at=as_known_at)
        if label_name is not None:
            candidates = [r for r in candidates if r.label_name == label_name]
        if event_time is not None:
            candidates = [r for r in candidates if r.event_time == event_time]
        if not candidates:
            return None
        return max(candidates, key=lambda r: (r.revision_time, r.ingest_time, r.revision_id))


def research_query(
    store: PitRevisionStore,
    query: ResearchQuery | dict[str, Any] | None = None,
    *,
    as_known_at: int | None = None,
    series_id: str | None = None,
    event_time: int | None = None,
    label_name: str | None = None,
    allow_latest_revision: bool = False,
    raise_on_unavailable: bool = False,
) -> QueryResult:
    """Mandatory AS_KNOWN_AT research query.

    Ban: using today's / tip revision when AS_KNOWN_AT is earlier than that tip.
    Guard: unavailable-at-time returns UNAVAILABLE_AT_TIME (no silent fill).
    """
    if query is None and as_known_at is None:
        refuse_missing_as_known_at()
    if isinstance(query, dict):
        if "as_known_at" not in query or query.get("as_known_at") is None:
            refuse_missing_as_known_at()
        q = ResearchQuery(
            series_id=str(query["series_id"]),
            as_known_at=int(query["as_known_at"]),
            event_time=query.get("event_time"),
            label_name=query.get("label_name"),
            allow_latest_revision=bool(query.get("allow_latest_revision", False)),
            query_id=str(query.get("query_id") or ""),
        )
    elif isinstance(query, ResearchQuery):
        q = query
        if q.as_known_at is None or int(q.as_known_at) <= 0:  # type: ignore[unreachable]
            refuse_missing_as_known_at()
    else:
        if as_known_at is None or int(as_known_at) <= 0:
            refuse_missing_as_known_at()
        if not series_id:
            raise ValueError("series_id required")
        q = ResearchQuery(
            series_id=series_id,
            as_known_at=int(as_known_at),
            event_time=event_time,
            label_name=label_name,
            allow_latest_revision=allow_latest_revision,
        )

    aka = int(q.as_known_at)
    if aka <= 0:
        refuse_missing_as_known_at()

    latest = store.latest_revision(q.series_id)
    # Ban using today's revision for past backtests (explicit opt-in still refused).
    if latest is not None and latest.revision_time > aka:
        if q.allow_latest_revision:
            refuse_today_revision_for_past_backtest(
                as_known_at=aka, latest_revision_time=latest.revision_time
            )

    selected = store.select_as_known_at(
        q.series_id,
        as_known_at=aka,
        label_name=q.label_name,
        event_time=q.event_time,
    )
    if selected is None:
        if raise_on_unavailable:
            refuse_unavailable_silent_fill(series_id=q.series_id, as_known_at=aka)
        return QueryResult(
            status="UNAVAILABLE_AT_TIME",
            series_id=q.series_id,
            as_known_at=aka,
            reason="no_revision_visible_at_as_known_at",
            leakage_blocked=True,
        )

    # Defense in depth — selected must pass axis check.
    try:
        assert_no_future_axes(selected, as_known_at=aka)
    except FutureLeakageError as exc:
        return QueryResult(
            status="REJECTED_FUTURE_LEAKAGE",
            series_id=q.series_id,
            as_known_at=aka,
            reason=str(exc),
            leakage_blocked=True,
        )

    lineage = [r.to_dict() for r in store.revision_lineage(selected.revision_id)]
    # Lineage for the response is truncated to revisions visible at AS_KNOWN_AT.
    visible_lineage = [
        r
        for r in lineage
        if int(r["times"]["revision_time"]) <= aka and int(r["times"]["available_time"]) <= aka
    ]

    return QueryResult(
        status="AVAILABLE",
        series_id=q.series_id,
        as_known_at=aka,
        value=selected.value,
        revision_id=selected.revision_id,
        selected_revision=selected.to_dict(),
        lineage=tuple(visible_lineage),
        reason="as_known_at_revision_selected",
        leakage_blocked=False,
        fixture_only=selected.fixture_only,
    )


def prove_pit_visibility(
    store: PitRevisionStore,
    *,
    series_id: str,
    as_known_at: int,
) -> dict[str, Any]:
    all_revs = store.series_revisions(series_id)
    visible = store.visible_revisions(series_id, as_known_at=as_known_at)
    future = [r for r in all_revs if not is_visible_as_known_at(r, as_known_at=as_known_at)]
    leaked_ids = [
        r.revision_id
        for r in visible
        if r.revision_time > as_known_at
        or r.available_time > as_known_at
        or r.ingest_time > as_known_at
    ]
    return {
        "schema": "v17_d_pit_visibility_proof",
        "series_id": series_id,
        "as_known_at": as_known_at,
        "input_count": len(all_revs),
        "visible_count": len(visible),
        "future_count": len(future),
        "leaked_revision_ids": leaked_ids,
        "pit_holds": len(leaked_ids) == 0,
        "rule": (
            "available_time <= AS_KNOWN_AT AND "
            "revision_time <= AS_KNOWN_AT AND "
            "ingest_time <= AS_KNOWN_AT"
        ),
    }


__all__ = [
    "DualTimeStamp",
    "PitRevisionStore",
    "ResearchQuery",
    "QueryResult",
    "RevisionRecord",
    "assert_no_future_axes",
    "is_visible_as_known_at",
    "prove_pit_visibility",
    "research_query",
]
