"""Closed historical holdout — used-interval registry + deterministic period selection.

No performance inspection. No September OOS use. No policy mutation.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DAY_MS = 86_400_000
GAP_DAYS = 30
DURATION_CANDIDATES_DAYS = (180, 150, 120)
MIN_DURATION_DAYS = 120

# Canonical known research span from deleted/provenance filenames + V3 runner.
RESEARCH_V2_V3_START_MS = 1_739_007_000_000
RESEARCH_V2_V3_END_MS = 1_785_663_000_000

SEPTEMBER_OOS_START_MS = 1_785_663_000_001
SEPTEMBER_OOS_END_MS = 1_789_551_000_000

SELECTION_RULE = (
    "latest_fully_closed_contiguous_Nd_ending_at_least_30d_before_earliest_used;"
    "chronology_non_overlap_completeness_only;fallback_180_150_120;no_perf_inspection"
)

_TS_RE = re.compile(r"(?<!\d)(1[6-9]\d{11})(?!\d)")


@dataclass(frozen=True)
class UsedInterval:
    source: str
    label: str
    start_ms: int
    end_ms: int
    category: str

    def overlaps(self, a: int, b: int) -> bool:
        return not (b < self.start_ms or a > self.end_ms)


@dataclass
class PeriodSelection:
    reservation_id: str
    reservation_start: int
    reservation_end: int
    reservation_duration_days: int
    selection_rule: str
    interval_registry_checksum: str
    earliest_used_ms: int
    status: str
    reason: str | None
    used_intervals: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _add(
    out: list[UsedInterval],
    *,
    source: str,
    label: str,
    start_ms: int,
    end_ms: int,
    category: str,
) -> None:
    if end_ms < start_ms:
        start_ms, end_ms = end_ms, start_ms
    out.append(
        UsedInterval(
            source=source,
            label=label,
            start_ms=int(start_ms),
            end_ms=int(end_ms),
            category=category,
        )
    )


def _scan_path_timestamps(path: Path, root: Path) -> list[tuple[int, int]]:
    """Extract (start,end) pairs from filenames containing two epoch-ms stamps."""
    found: list[tuple[int, int]] = []
    name = path.name
    stamps = [int(x) for x in _TS_RE.findall(name)]
    if len(stamps) >= 2:
        found.append((min(stamps[0], stamps[1]), max(stamps[0], stamps[1])))
    return found


def build_used_interval_registry(root: Path) -> list[UsedInterval]:
    """Collect every timestamp interval previously touched for H3 research/qualification."""
    intervals: list[UsedInterval] = []

    _add(
        intervals,
        source="artifacts/readiness/MARKET_DATASET_MANIFEST.json+deleted_files_manifest",
        label="edge_research_v2_v3_market_span",
        start_ms=RESEARCH_V2_V3_START_MS,
        end_ms=RESEARCH_V2_V3_END_MS,
        category="training_replay_walk_forward_research",
    )
    _add(
        intervals,
        source="artifacts/readiness/OOS_H3_UNTOUCHED_V1_RESERVATION.json",
        label="OOS_H3_UNTOUCHED_V1_RESERVED",
        start_ms=SEPTEMBER_OOS_START_MS,
        end_ms=SEPTEMBER_OOS_END_MS,
        category="september_untouched_oos",
    )
    # Consumed failed OOS was cut from the trailing research span (last ~15%).
    span = RESEARCH_V2_V3_END_MS - RESEARCH_V2_V3_START_MS
    consumed_start = RESEARCH_V2_V3_START_MS + int(span * 0.85)
    _add(
        intervals,
        source="artifacts/readiness/immutable/consumed_failed_oos/consumed_oos_holdout.json",
        label="OOS_REAL_MARKET_2026Q_FAILED_HOLDOUT_e186d13",
        start_ms=consumed_start,
        end_ms=RESEARCH_V2_V3_END_MS,
        category="prior_consumed_oos",
    )

    # Scan deleted-file paths and readiness JSON for additional stamped ranges.
    scan_roots = [
        root / "artifacts" / "readiness",
        root / "artifacts" / "readiness" / "immutable",
    ]
    deleted = root / "artifacts" / "readiness" / "deleted_files_manifest.json"
    if deleted.is_file():
        try:
            payload = json.loads(deleted.read_text(encoding="utf-8"))
            for entry in payload.get("deleted") or payload.get("entries") or []:
                if isinstance(entry, dict):
                    p = str(entry.get("path") or "")
                else:
                    p = str(entry)
                if not p:
                    continue
                for a, b in _scan_path_timestamps(Path(p), root):
                    cat = "prior_research_cache"
                    if "oos" in p.lower():
                        cat = "prior_oos_cache"
                    if "OOS_H3_UNTOUCHED" in p:
                        cat = "september_untouched_oos"
                    _add(intervals, source=p, label=Path(p).name, start_ms=a, end_ms=b, category=cat)
        except (OSError, json.JSONDecodeError):
            pass

    for base in scan_roots:
        if not base.exists():
            continue
        for p in base.rglob("*.json"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # Explicit reserved_* fields
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict):
                rs = obj.get("reserved_start") or obj.get("reservation_start") or obj.get("start_ms")
                re_ = obj.get("reserved_end") or obj.get("reservation_end") or obj.get("end_ms")
                if isinstance(rs, (int, float)) and isinstance(re_, (int, float)):
                    rel = str(p.relative_to(root)).replace("\\", "/")
                    if "OOS_H3_UNTOUCHED" in rel or "h3_oos_v1" in rel:
                        cat = "september_untouched_oos"
                    elif "consumed" in rel.lower():
                        cat = "prior_consumed_oos"
                    else:
                        cat = "readiness_manifest_interval"
                    _add(
                        intervals,
                        source=rel,
                        label=p.name,
                        start_ms=int(rs),
                        end_ms=int(re_),
                        category=cat,
                    )
            for a, b in _scan_path_timestamps(p, root):
                rel = str(p.relative_to(root)).replace("\\", "/")
                _add(intervals, source=rel, label=p.name, start_ms=a, end_ms=b, category="filename_stamp")

    # Deduplicate identical ranges+labels
    uniq: dict[tuple[str, int, int], UsedInterval] = {}
    for iv in intervals:
        key = (iv.label, iv.start_ms, iv.end_ms)
        uniq[key] = iv
    return sorted(uniq.values(), key=lambda x: (x.start_ms, x.end_ms, x.label))


def earliest_used_ms(intervals: list[UsedInterval]) -> int:
    if not intervals:
        raise RuntimeError("empty_used_interval_registry")
    return min(iv.start_ms for iv in intervals)


def overlaps_any(intervals: list[UsedInterval], start_ms: int, end_ms: int) -> list[UsedInterval]:
    return [iv for iv in intervals if iv.overlaps(start_ms, end_ms)]


def select_closed_historical_period(
    *,
    root: Path,
    reservation_id: str = "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED",
) -> PeriodSelection:
    """Deterministic selection: chronology + non-overlap only. No performance peeking."""
    registry = build_used_interval_registry(root)
    earliest = earliest_used_ms(registry)
    registry_payload = [asdict(iv) for iv in registry]
    registry_checksum = _sha_obj(registry_payload)

    end_cap = earliest - GAP_DAYS * DAY_MS
    for days in DURATION_CANDIDATES_DAYS:
        start = end_cap - days * DAY_MS
        end = end_cap
        hits = overlaps_any(registry, start, end)
        if hits:
            continue
        return PeriodSelection(
            reservation_id=reservation_id,
            reservation_start=start,
            reservation_end=end,
            reservation_duration_days=days,
            selection_rule=SELECTION_RULE.replace("Nd", f"{days}d"),
            interval_registry_checksum=registry_checksum,
            earliest_used_ms=earliest,
            status="PERIOD_SELECTED",
            reason=None,
            used_intervals=registry_payload,
        )

    return PeriodSelection(
        reservation_id=reservation_id,
        reservation_start=0,
        reservation_end=0,
        reservation_duration_days=0,
        selection_rule=SELECTION_RULE,
        interval_registry_checksum=registry_checksum,
        earliest_used_ms=earliest,
        status="NO_CLEAN_CLOSED_HISTORICAL_HOLDOUT_AVAILABLE",
        reason="NO_CLEAN_CLOSED_HISTORICAL_HOLDOUT_AVAILABLE",
        used_intervals=registry_payload,
    )


def assert_september_partial_excluded(path_hint: str) -> None:
    norm = path_hint.replace("\\", "/").lower()
    if "oos_h3_untouched_v1_reserved" in norm:
        raise RuntimeError("SEPTEMBER_PARTIAL_OOS_EXCLUDED: forbidden in closed historical holdout")
