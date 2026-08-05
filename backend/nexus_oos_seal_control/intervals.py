"""Interval planning for V15-G (plans only — never real reservation)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_oos_seal_control.constants import PLAN_STATUS_PLANNED_NOT_RESERVED


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class IntervalRecord:
    interval_id: str
    label: str
    start_ms: int
    end_ms: int
    category: str
    symbols: tuple[str, ...] = ()
    intervals: tuple[str, ...] = ()

    def overlaps(self, other: "IntervalRecord") -> bool:
        return not (self.end_ms < other.start_ms or other.end_ms < self.start_ms)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["symbols"] = list(self.symbols)
        d["intervals"] = list(self.intervals)
        return d


@dataclass
class IntervalRegistry:
    kind: str
    intervals: list[IntervalRecord] = field(default_factory=list)

    def add(self, record: IntervalRecord) -> None:
        if record.end_ms < record.start_ms:
            raise ValueError(f"interval_inverted:{record.interval_id}")
        self.intervals.append(record)

    def checksum(self) -> str:
        body = [
            r.to_dict()
            for r in sorted(self.intervals, key=lambda x: (x.start_ms, x.end_ms, x.interval_id))
        ]
        return sha_obj({"kind": self.kind, "intervals": body})

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "interval_count": len(self.intervals),
            "checksum": self.checksum(),
            "intervals": [r.to_dict() for r in self.intervals],
        }


def synthetic_planning_registries(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, IntervalRegistry]:
    """Synthetic registries for control-plane proofs. Planned OOS is never reserved."""
    development = IntervalRegistry("development")
    planned_oos = IntervalRegistry("planned_oos")
    consumed_failed = IntervalRegistry("consumed_failed_holdout")

    development.add(
        IntervalRecord(
            interval_id="SYN_V15G_DEV_WINDOW",
            label="synthetic_development_window",
            start_ms=as_of_ms - 90 * 86_400_000,
            end_ms=as_of_ms - 30 * 86_400_000,
            category="development",
            symbols=("SYNTHUSDT",),
            intervals=("15", "60"),
        )
    )
    planned_oos.add(
        IntervalRecord(
            interval_id="SYN_V15G_PLANNED_OOS",
            label="synthetic_planned_oos_not_reserved",
            start_ms=as_of_ms - 20 * 86_400_000,
            end_ms=as_of_ms - 5 * 86_400_000,
            category="planned_oos",
            symbols=("SYNTHUSDT", "SYNETHUSDT"),
            intervals=("15", "60", "240"),
        )
    )
    consumed_failed.add(
        IntervalRecord(
            interval_id="SYN_V15G_CONSUMED_FAILED",
            label="synthetic_prior_failed_holdout",
            start_ms=as_of_ms - 120 * 86_400_000,
            end_ms=as_of_ms - 100 * 86_400_000,
            category="consumed_failed_holdout",
            symbols=("SYNTHUSDT",),
            intervals=("60",),
        )
    )
    return {
        "development": development,
        "planned_oos": planned_oos,
        "consumed_failed_holdout": consumed_failed,
    }


def build_interval_plan(
    registries: dict[str, IntervalRegistry],
    *,
    plan_id: str = "V15G_OOS_PLAN_SYNTHETIC_001",
) -> dict[str, Any]:
    """Build a writeable plan document. Does not create a real reservation."""
    planned = registries["planned_oos"]
    development = registries["development"]
    consumed = registries["consumed_failed_holdout"]

    overlap_violations: list[dict[str, Any]] = []
    for planned_iv in planned.intervals:
        for other in list(development.intervals) + list(consumed.intervals):
            if planned_iv.overlaps(other):
                overlap_violations.append(
                    {"planned": planned_iv.to_dict(), "conflict": other.to_dict()}
                )

    chronologically_later = all(
        all(p.start_ms > d.end_ms for d in development.intervals) for p in planned.intervals
    )

    plan = {
        "plan_id": plan_id,
        "plan_status": PLAN_STATUS_PLANNED_NOT_RESERVED,
        "fixture_only": True,
        "real_oos_reservation_executed": False,
        "oos_reserved": False,
        "oos_downloaded": False,
        "oos_executed": False,
        "oos_consumed": False,
        "registries": {k: v.to_dict() for k, v in registries.items()},
        "checks": {
            "no_overlap_with_development": len(overlap_violations) == 0,
            "no_overlap_with_consumed_failed": all(
                not p.overlaps(c)
                for p in planned.intervals
                for c in consumed.intervals
            ),
            "chronologically_later_than_development": chronologically_later,
            "overlap_violations": overlap_violations,
        },
    }
    plan["plan_checksum"] = sha_obj(
        {
            "plan_id": plan["plan_id"],
            "plan_status": plan["plan_status"],
            "registries": plan["registries"],
            "checks": {
                k: v
                for k, v in plan["checks"].items()
                if k != "overlap_violations"
            },
        }
    )
    return plan


def prove_non_consumption(plan: dict[str, Any]) -> dict[str, Any]:
    """Prove planned OOS intervals were neither reserved nor consumed."""
    registries = plan.get("registries") or {}
    planned = registries.get("planned_oos") or {}
    consumed = registries.get("consumed_failed_holdout") or {}
    violations: list[dict[str, Any]] = []

    for p in planned.get("intervals") or []:
        for c in consumed.get("intervals") or []:
            p_start, p_end = int(p["start_ms"]), int(p["end_ms"])
            c_start, c_end = int(c["start_ms"]), int(c["end_ms"])
            if not (p_end < c_start or c_end < p_start):
                violations.append({"planned": p, "consumed": c})

    flags_ok = (
        plan.get("oos_reserved") is False
        and plan.get("oos_downloaded") is False
        and plan.get("oos_executed") is False
        and plan.get("oos_consumed") is False
        and plan.get("real_oos_reservation_executed") is False
    )
    proven = flags_ok and len(violations) == 0 and plan.get("plan_status") == PLAN_STATUS_PLANNED_NOT_RESERVED
    return {
        "status": "OOS_NON_CONSUMPTION_PROVEN" if proven else "OOS_NON_CONSUMPTION_FAILED",
        "proven": proven,
        "oos_reserved": False,
        "oos_downloaded": False,
        "oos_executed": False,
        "oos_consumed": False,
        "violations": violations,
        "plan_checksum": plan.get("plan_checksum"),
        "registry_checksums": {
            k: (v or {}).get("checksum") for k, v in registries.items() if isinstance(v, dict)
        },
    }
