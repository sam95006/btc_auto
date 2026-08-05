"""Hourly partition + daily completeness accounting (read-only)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import (
    EXPECTED_HOURS_PER_DAY,
    FAMILIES,
    MIN_SYMBOL_COUNT,
    TARGET_CALENDAR_DAYS,
)
from backend.nexus_capture_supervisor.util import finding, parse_iso_utc, utc_hour_key, utc_now, utc_stamp


def _hour_from_name(name: str) -> str | None:
    # ..._YYYYMMDD_HH_N.jsonl.gz
    stem = name
    if stem.endswith(".jsonl.gz"):
        stem = stem[: -len(".jsonl.gz")]
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    day, hour = parts[-3], parts[-2]
    if len(day) == 8 and day.isdigit() and len(hour) == 2 and hour.isdigit():
        return f"{day}_{hour}"
    return None


def _iter_expected_hours(start: datetime, end: datetime) -> list[str]:
    """Inclusive start hour through end hour (UTC)."""
    cur = start.replace(minute=0, second=0, microsecond=0)
    end_h = end.replace(minute=0, second=0, microsecond=0)
    out: list[str] = []
    while cur <= end_h:
        out.append(utc_hour_key(cur))
        cur += timedelta(hours=1)
    return out


def scan_partition_tree(partitions_root: Path) -> dict[str, Any]:
    """Lightweight path scan — does not mutate or rewrite partitions."""
    root = Path(partitions_root)
    if not root.is_dir():
        return {
            "status": "MISSING",
            "path": str(root),
            "partitions": [],
            "silent_fallback": False,
        }

    rows: list[dict[str, Any]] = []
    for gz in sorted(root.rglob("*.jsonl.gz")):
        hour = _hour_from_name(gz.name)
        man = Path(str(gz).replace(".jsonl.gz", ".jsonl.manifest.json"))
        if not man.is_file():
            # alternate naming used by some writers
            alt = Path(str(gz) + ".manifest.json")
            man_present = alt.is_file()
            man_path = alt if man_present else man
        else:
            man_present = True
            man_path = man
        open_marker = Path(str(gz) + ".open")
        if not open_marker.is_file():
            open_marker = Path(str(gz).replace(".jsonl.gz", ".open"))
        open_present = open_marker.is_file()
        parts = gz.parts
        family = None
        symbol = None
        for fam in FAMILIES:
            if fam in parts:
                idx = parts.index(fam)
                family = fam
                if idx + 1 < len(parts):
                    symbol = parts[idx + 1]
                break
        rows.append(
            {
                "path": str(gz),
                "UTC_hour": hour,
                "family": family,
                "symbol": symbol,
                "compressed_bytes": gz.stat().st_size,
                "mtime": gz.stat().st_mtime,
                "manifest_present": man_present,
                "manifest_path": str(man_path) if man_present else None,
                "open_marker_present": open_present,
                "is_open_tail": (not man_present) or open_present,
            }
        )
    return {"status": "OK", "path": str(root), "partitions": rows, "silent_fallback": False}


def account_partitions(
    *,
    partitions_root: Path,
    campaign_id: str,
    capture_start_utc: str | None,
    expected_symbol_count: int = MIN_SYMBOL_COUNT,
    families: tuple[str, ...] = FAMILIES,
) -> dict[str, Any]:
    scan = scan_partition_tree(partitions_root)
    findings: list[dict[str, Any]] = []
    if scan["status"] != "OK":
        findings.append(
            finding(
                code="PARTITIONS_ROOT_MISSING",
                severity="CRITICAL",
                summary="Partitions root missing — cannot account hourly completeness",
                evidence={"path": scan.get("path")},
            )
        )
        return {
            "schema": "v14_a_partition_accounting",
            "observed_at": utc_stamp(),
            "campaign_id": campaign_id,
            "status": "UNAVAILABLE",
            "scan": scan,
            "findings": findings,
        }

    rows: list[dict[str, Any]] = scan["partitions"]
    by_hour: dict[str, list[dict[str, Any]]] = defaultdict(list)
    symbols: set[str] = set()
    family_counts: dict[str, int] = defaultdict(int)
    open_tails = 0
    sealed = 0
    total_bytes = 0
    for r in rows:
        hour = r.get("UTC_hour") or "UNKNOWN"
        by_hour[str(hour)].append(r)
        if r.get("symbol"):
            symbols.add(str(r["symbol"]))
        if r.get("family"):
            family_counts[str(r["family"])] += 1
        total_bytes += int(r.get("compressed_bytes") or 0)
        if r.get("is_open_tail"):
            open_tails += 1
        else:
            sealed += 1

    start = parse_iso_utc(capture_start_utc)
    now = utc_now()
    expected_hours: list[str] = []
    missing_hours: list[str] = []
    if start is not None:
        expected_hours = _iter_expected_hours(start, now)
        # Current hour may be partial — still expected to exist if elapsed > few minutes
        present = set(by_hour.keys())
        missing_hours = [h for h in expected_hours if h not in present]
        # Drop UNKNOWN from missing logic
        missing_hours = [h for h in missing_hours if h != "UNKNOWN"]
    else:
        findings.append(
            finding(
                code="CAPTURE_START_UNKNOWN",
                severity="HIGH",
                summary="capture_start_UTC unavailable — cannot compute expected hour set",
                evidence={"capture_start_utc": capture_start_utc},
            )
        )

    # Daily completeness: group by YYYYMMDD
    by_day: dict[str, dict[str, Any]] = {}
    for hour, items in by_hour.items():
        if "_" not in hour:
            continue
        day = hour.split("_", 1)[0]
        bucket = by_day.setdefault(
            day,
            {"day_key": day, "hours_present": set(), "partition_count": 0, "open_tails": 0, "sealed": 0},
        )
        bucket["hours_present"].add(hour)
        bucket["partition_count"] += len(items)
        bucket["open_tails"] += sum(1 for i in items if i.get("is_open_tail"))
        bucket["sealed"] += sum(1 for i in items if not i.get("is_open_tail"))

    daily: list[dict[str, Any]] = []
    for day, bucket in sorted(by_day.items()):
        hours_present = sorted(bucket["hours_present"])
        completeness = len(hours_present) / float(EXPECTED_HOURS_PER_DAY)
        daily.append(
            {
                "day_key": day,
                "hours_present": hours_present,
                "hours_present_count": len(hours_present),
                "expected_hours_per_day": EXPECTED_HOURS_PER_DAY,
                "completeness_ratio": round(completeness, 4),
                "complete": len(hours_present) >= EXPECTED_HOURS_PER_DAY,
                "partition_count": bucket["partition_count"],
                "open_tails": bucket["open_tails"],
                "sealed": bucket["sealed"],
                "status": "COMPLETE"
                if len(hours_present) >= EXPECTED_HOURS_PER_DAY
                else "IN_PROGRESS",
            }
        )

    if missing_hours:
        # Missing completed hours (exclude current UTC hour) is HIGH
        current = utc_hour_key(now)
        completed_missing = [h for h in missing_hours if h != current]
        if completed_missing:
            findings.append(
                finding(
                    code="HOURLY_GAPS",
                    severity="HIGH",
                    summary=f"Missing completed UTC hours: {completed_missing}",
                    evidence={
                        "missing_hours": completed_missing,
                        "expected_hours": expected_hours,
                        "present_hours": sorted(by_hour.keys()),
                    },
                    recommendation="Investigate WS gap / hour rotation; do not fill gaps with synthetic data",
                )
            )

    if len(symbols) < expected_symbol_count:
        findings.append(
            finding(
                code="SYMBOL_COVERAGE_LOW",
                severity="HIGH",
                summary=f"Symbol coverage {len(symbols)} < expected {expected_symbol_count}",
                evidence={"symbol_count": len(symbols), "symbols": sorted(symbols)},
            )
        )

    for fam in families:
        if family_counts.get(fam, 0) == 0:
            findings.append(
                finding(
                    code="FAMILY_MISSING",
                    severity="HIGH",
                    summary=f"No partitions observed for family {fam}",
                    evidence={"family": fam},
                )
            )

    status = "PASS" if not any(f["severity"] in {"CRITICAL", "HIGH"} for f in findings) else "FINDINGS"

    hourly = [
        {
            "UTC_hour": hour,
            "partition_count": len(items),
            "open_tail_count": sum(1 for i in items if i.get("is_open_tail")),
            "sealed_count": sum(1 for i in items if not i.get("is_open_tail")),
            "symbols": sorted({str(i.get("symbol")) for i in items if i.get("symbol")}),
            "bytes": sum(int(i.get("compressed_bytes") or 0) for i in items),
        }
        for hour, items in sorted(by_hour.items())
    ]

    return {
        "schema": "v14_a_partition_accounting",
        "observed_at": utc_stamp(),
        "campaign_id": campaign_id,
        "status": status,
        "partitions_root": str(partitions_root),
        "partition_count": len(rows),
        "sealed_count": sealed,
        "open_tail_count": open_tails,
        "total_compressed_bytes": total_bytes,
        "symbol_count": len(symbols),
        "symbols": sorted(symbols),
        "family_counts": dict(family_counts),
        "expected_hours": expected_hours,
        "missing_hours": missing_hours,
        "hourly": hourly,
        "daily": daily,
        "target_calendar_days": TARGET_CALENDAR_DAYS,
        "days_observed": len(daily),
        "findings": findings,
        "silent_fallback": False,
    }
