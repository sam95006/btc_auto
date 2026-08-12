"""Revision conflict testing — concurrent / divergent lineage detection."""
from __future__ import annotations

from typing import Any

from backend.nexus_pit_revision_v17.store import PitRevisionStore
from backend.nexus_pit_revision_v17.types import DualTimeStamp, RevisionRecord


class RevisionConflictError(RuntimeError):
    """Raised when two tip revisions diverge without a shared parent resolution."""


class RevisionConflictHarness:
    """Wraps PitRevisionStore with explicit conflict detection for deep engineering."""

    def __init__(self) -> None:
        self.store = PitRevisionStore()
        self.conflicts: list[dict[str, Any]] = []

    def ingest(self, record: RevisionRecord) -> RevisionRecord:
        return self.store.ingest(record)

    def detect_fork(
        self,
        *,
        series_id: str,
        as_known_at: int,
    ) -> dict[str, Any]:
        """Detect multiple tip parents at the same as_known_at window (fork)."""
        visible = self.store.visible_revisions(series_id, as_known_at=as_known_at)
        if not visible:
            return {
                "status": "EMPTY",
                "conflict": False,
                "series_id": series_id,
                "tips": [],
            }
        # Tips = revisions that are not parents of any other visible revision
        parent_ids = {r.parent_revision_id for r in visible if r.parent_revision_id}
        tips = [r for r in visible if r.revision_id not in parent_ids]
        conflict = len(tips) > 1
        payload = {
            "status": "CONFLICT" if conflict else "OK",
            "conflict": conflict,
            "series_id": series_id,
            "as_known_at": as_known_at,
            "tip_count": len(tips),
            "tips": [t.revision_id for t in tips],
            "tip_values": [t.value for t in tips],
        }
        if conflict:
            self.conflicts.append(payload)
        return payload

    def refuse_ambiguous_tip(self, *, series_id: str, as_known_at: int) -> dict[str, Any]:
        """Research query must not silently pick an arbitrary tip under conflict."""
        fork = self.detect_fork(series_id=series_id, as_known_at=as_known_at)
        if fork["conflict"]:
            raise RevisionConflictError(
                f"ambiguous_revision_tips:{series_id}:{','.join(fork['tips'])}"
            )
        if not fork["tips"]:
            return {"status": "EMPTY", "selected": None}
        tip_id = fork["tips"][0]
        rec = self.store.get(tip_id)
        return {"status": "OK", "selected": tip_id, "value": None if rec is None else rec.value}

    def build_conflict_fixture(self) -> dict[str, Any]:
        """Plant a divergent fork and prove it is detected / refused."""
        t0 = DualTimeStamp(
            event_time=1_700_000_000_000,
            available_time=1_700_000_000_100,
            revision_time=1_700_000_000_200,
            ingest_time=1_700_000_000_300,
        )
        root = RevisionRecord(
            revision_id="rev_root",
            series_id="btc.mark",
            kind="OBSERVATION",
            value={"px": 100.0},
            times=t0,
            fixture_only=True,
        )
        self.ingest(root)
        a = RevisionRecord(
            revision_id="rev_a",
            series_id="btc.mark",
            kind="OBSERVATION",
            value={"px": 101.0},
            times=DualTimeStamp(
                event_time=1_700_000_001_000,
                available_time=1_700_000_001_100,
                revision_time=1_700_000_001_200,
                ingest_time=1_700_000_001_300,
            ),
            parent_revision_id="rev_root",
            fixture_only=True,
        )
        b = RevisionRecord(
            revision_id="rev_b",
            series_id="btc.mark",
            kind="OBSERVATION",
            value={"px": 102.0},
            times=DualTimeStamp(
                event_time=1_700_000_001_000,
                available_time=1_700_000_001_100,
                revision_time=1_700_000_001_250,
                ingest_time=1_700_000_001_350,
            ),
            parent_revision_id="rev_root",
            fixture_only=True,
        )
        self.ingest(a)
        self.ingest(b)
        as_of = 1_700_000_002_000
        fork = self.detect_fork(series_id="btc.mark", as_known_at=as_of)
        refused = False
        detail = ""
        try:
            self.refuse_ambiguous_tip(series_id="btc.mark", as_known_at=as_of)
        except RevisionConflictError as exc:
            refused = True
            detail = str(exc)
        # Duplicate revision_id must also fail closed
        dup_blocked = False
        try:
            self.ingest(a)
        except ValueError:
            dup_blocked = True
        return {
            "fork_detected": fork["conflict"] is True,
            "tip_count": fork["tip_count"],
            "ambiguous_tip_refused": refused,
            "duplicate_revision_id_blocked": dup_blocked,
            "detail": detail,
            "attack_blocked": fork["conflict"] and refused and dup_blocked,
            "survivor": not (fork["conflict"] and refused and dup_blocked),
        }
