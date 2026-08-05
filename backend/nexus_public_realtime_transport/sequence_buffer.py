"""Sequence buffer with duplicate suppression and out-of-order handling."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_public_realtime_transport.constants import SEQUENCE_BUFFER_CAPACITY
from backend.nexus_public_realtime_transport.event_model import PublicStreamEvent


@dataclass
class ApplyResult:
    accepted: bool
    reason: str
    delivered: list[PublicStreamEvent] = field(default_factory=list)
    buffered_out_of_order: int = 0
    duplicates_suppressed: int = 0
    gaps_noticed: int = 0


class SequenceBuffer:
    """Ordered delivery buffer for public stream events.

    - Duplicate seq / event_id → suppressed
    - Future seq → held until gap filled (or gap_notice emitted on flush)
    - Past seq already delivered → suppressed
    """

    def __init__(self, *, capacity: int = SEQUENCE_BUFFER_CAPACITY) -> None:
        self.capacity = int(capacity)
        self._next_expected = 1
        self._seen_ids: OrderedDict[str, None] = OrderedDict()
        self._pending: dict[int, PublicStreamEvent] = {}
        self.duplicates_suppressed = 0
        self.gaps_noticed = 0

    @property
    def next_expected(self) -> int:
        return self._next_expected

    @property
    def last_delivered_seq(self) -> int:
        return self._next_expected - 1

    def reset_from_seq(self, last_seq: int) -> None:
        self._next_expected = int(last_seq) + 1
        self._pending.clear()

    def _remember_id(self, event_id: str) -> None:
        self._seen_ids[event_id] = None
        while len(self._seen_ids) > self.capacity:
            self._seen_ids.popitem(last=False)

    def apply(self, event: PublicStreamEvent) -> ApplyResult:
        if event.event_id in self._seen_ids:
            self.duplicates_suppressed += 1
            return ApplyResult(
                accepted=False,
                reason="duplicate_event_id",
                duplicates_suppressed=1,
            )
        if event.seq < self._next_expected:
            self.duplicates_suppressed += 1
            self._remember_id(event.event_id)
            return ApplyResult(
                accepted=False,
                reason="duplicate_or_stale_seq",
                duplicates_suppressed=1,
            )
        if event.seq > self._next_expected:
            if len(self._pending) >= self.capacity:
                return ApplyResult(accepted=False, reason="ooo_buffer_full")
            self._pending[event.seq] = event
            self._remember_id(event.event_id)
            return ApplyResult(
                accepted=True,
                reason="buffered_out_of_order",
                buffered_out_of_order=1,
            )

        # event.seq == next_expected
        delivered: list[PublicStreamEvent] = [event]
        self._remember_id(event.event_id)
        self._next_expected = event.seq + 1
        while self._next_expected in self._pending:
            nxt = self._pending.pop(self._next_expected)
            delivered.append(nxt)
            self._next_expected += 1
        return ApplyResult(accepted=True, reason="in_order", delivered=delivered)

    def flush_with_gap_notice(self) -> ApplyResult:
        """Force-deliver pending after emitting gap accounting (client-side recovery)."""
        if not self._pending:
            return ApplyResult(accepted=False, reason="no_pending")
        delivered: list[PublicStreamEvent] = []
        for seq in sorted(self._pending):
            if seq > self._next_expected:
                self.gaps_noticed += 1
            delivered.append(self._pending[seq])
            self._next_expected = seq + 1
        self._pending.clear()
        return ApplyResult(
            accepted=True,
            reason="flushed_with_gaps",
            delivered=delivered,
            gaps_noticed=self.gaps_noticed,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "next_expected": self._next_expected,
            "last_delivered_seq": self.last_delivered_seq,
            "pending_count": len(self._pending),
            "seen_id_count": len(self._seen_ids),
            "duplicates_suppressed": self.duplicates_suppressed,
            "gaps_noticed": self.gaps_noticed,
        }
