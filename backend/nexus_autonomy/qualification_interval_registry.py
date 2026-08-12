"""Interval registries for formal qualification infrastructure.

Tracks data / consumed / reserved intervals, future-data exclusion, and OOS
non-consumption proofs. Synthetic fixtures only — no downloads, no OOS exec.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_autonomy.qualification_checksums import sha_obj


@dataclass(frozen=True)
class IntervalRecord:
    interval_id: str
    label: str
    start_ms: int
    end_ms: int
    category: str  # data | consumed | reserved | excluded_future

    def overlaps(self, a: int, b: int) -> bool:
        return not (b < self.start_ms or a > self.end_ms)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntervalRegistry:
    kind: str
    intervals: list[IntervalRecord] = field(default_factory=list)

    def add(self, record: IntervalRecord) -> None:
        if record.end_ms < record.start_ms:
            raise ValueError(f"interval_inverted:{record.interval_id}")
        self.intervals.append(record)

    def overlaps(self, start_ms: int, end_ms: int) -> list[IntervalRecord]:
        return [r for r in self.intervals if r.overlaps(start_ms, end_ms)]

    def checksum(self) -> str:
        body = [r.to_dict() for r in sorted(self.intervals, key=lambda x: (x.start_ms, x.end_ms, x.interval_id))]
        return sha_obj({"kind": self.kind, "intervals": body})

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "interval_count": len(self.intervals),
            "checksum": self.checksum(),
            "intervals": [r.to_dict() for r in self.intervals],
        }


def build_empty_registries() -> dict[str, IntervalRegistry]:
    return {
        "data": IntervalRegistry(kind="data"),
        "consumed": IntervalRegistry(kind="consumed"),
        "reserved": IntervalRegistry(kind="reserved"),
    }


def assert_future_data_excluded(
    *,
    proposed_start_ms: int,
    proposed_end_ms: int,
    as_of_ms: int,
) -> dict[str, Any]:
    """Fail-closed: any interval extending past as_of is excluded."""
    future_touch = proposed_end_ms > as_of_ms
    status = "FUTURE_DATA_EXCLUDED" if not future_touch else "FUTURE_DATA_VIOLATION"
    return {
        "status": status,
        "proposed_start_ms": int(proposed_start_ms),
        "proposed_end_ms": int(proposed_end_ms),
        "as_of_ms": int(as_of_ms),
        "future_data_excluded": not future_touch,
        "allowed": not future_touch,
    }


def assert_no_overlap_with_consumed(
    consumed: IntervalRegistry,
    *,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    hits = consumed.overlaps(start_ms, end_ms)
    return {
        "status": "NO_CONSUMED_OVERLAP" if not hits else "CONSUMED_OVERLAP_VIOLATION",
        "allowed": len(hits) == 0,
        "hits": [h.to_dict() for h in hits],
    }


def prove_oos_non_consumption(
    *,
    reserved: IntervalRegistry,
    consumed: IntervalRegistry,
    data: IntervalRegistry,
) -> dict[str, Any]:
    """Prove reserved OOS intervals were never consumed and never used as data."""
    violations: list[dict[str, Any]] = []
    for reserved_iv in reserved.intervals:
        for hit in consumed.overlaps(reserved_iv.start_ms, reserved_iv.end_ms):
            violations.append(
                {
                    "kind": "reserved_vs_consumed",
                    "reserved": reserved_iv.to_dict(),
                    "hit": hit.to_dict(),
                }
            )
        for hit in data.overlaps(reserved_iv.start_ms, reserved_iv.end_ms):
            # Data registry may list the reserved window as known/available,
            # but category must remain reserved — treat non-reserved categories as consumption.
            if hit.category not in {"reserved", "excluded_future"}:
                violations.append(
                    {
                        "kind": "reserved_vs_data_consumed",
                        "reserved": reserved_iv.to_dict(),
                        "hit": hit.to_dict(),
                    }
                )

    ok = len(violations) == 0 and len(reserved.intervals) >= 0
    return {
        "status": "OOS_NON_CONSUMPTION_PROVEN" if ok else "OOS_NON_CONSUMPTION_FAILED",
        "proven": ok,
        "reserved_count": len(reserved.intervals),
        "consumed_count": len(consumed.intervals),
        "data_count": len(data.intervals),
        "violations": violations,
        "registry_checksums": {
            "data": data.checksum(),
            "consumed": consumed.checksum(),
            "reserved": reserved.checksum(),
        },
        "oos_executed": False,
        "formal_walk_forward_executed": False,
    }
