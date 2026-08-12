"""Manifest presence + checksum sampling (read-only, bounded sample)."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import MANIFEST_SAMPLE_MAX
from backend.nexus_capture_supervisor.partition_accounting import scan_partition_tree
from backend.nexus_capture_supervisor.util import finding, utc_stamp


def _sha256_file(path: Path, *, limit_bytes: int | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        remaining = limit_bytes
        while True:
            chunk_size = 1024 * 256
            if remaining is not None:
                if remaining <= 0:
                    break
                chunk_size = min(chunk_size, remaining)
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return h.hexdigest()


def sample_manifests_and_checksums(
    *,
    partitions_root: Path,
    campaign_id: str,
    sample_max: int = MANIFEST_SAMPLE_MAX,
    seed: int = 14,
) -> dict[str, Any]:
    scan = scan_partition_tree(partitions_root)
    findings: list[dict[str, Any]] = []
    if scan["status"] != "OK":
        findings.append(
            finding(
                code="MANIFEST_SCAN_UNAVAILABLE",
                severity="CRITICAL",
                summary="Cannot sample manifests — partitions root missing",
                evidence={"path": scan.get("path")},
            )
        )
        return {
            "schema": "v14_a_manifest_checksum_sample",
            "observed_at": utc_stamp(),
            "campaign_id": campaign_id,
            "status": "UNAVAILABLE",
            "findings": findings,
        }

    rows = list(scan["partitions"])
    sealed = [r for r in rows if r.get("manifest_present")]
    open_tails = [r for r in rows if r.get("is_open_tail")]

    rng = random.Random(seed)
    sample_pool = sealed if sealed else rows
    sample_n = min(int(sample_max), len(sample_pool))
    sample = rng.sample(sample_pool, sample_n) if sample_n else []

    samples: list[dict[str, Any]] = []
    mismatch = 0
    unreadable = 0
    for r in sample:
        entry: dict[str, Any] = {
            "path": r["path"],
            "manifest_present": r.get("manifest_present"),
            "UTC_hour": r.get("UTC_hour"),
            "symbol": r.get("symbol"),
        }
        if not r.get("manifest_present"):
            entry["sample_status"] = "OPEN_TAIL_SKIP_CHECKSUM"
            samples.append(entry)
            continue
        man_path = Path(r["manifest_path"])
        try:
            man = json.loads(man_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            unreadable += 1
            entry["sample_status"] = "MANIFEST_UNREADABLE"
            entry["error"] = f"{type(exc).__name__}:{exc}"
            samples.append(entry)
            continue

        expected = (
            man.get("rolling_checksum")
            or man.get("checksum")
            or man.get("replayed_checksum")
            or man.get("sha256")
        )
        # Bounded content hash of gzip bytes as presence/stability signal.
        # Full gzip replay is expensive; sample uses file sha256 vs manifest fields when present.
        file_sha = _sha256_file(Path(r["path"]))
        entry["manifest_checksum"] = expected
        entry["file_sha256"] = file_sha
        entry["record_count"] = man.get("record_count")
        entry["partition_id"] = man.get("partition_id")
        # Compare only when manifest stores original_sha256_file / file digest.
        listed = man.get("original_sha256_file") or man.get("gzip_sha256") or man.get("file_sha256")
        if listed:
            match = str(listed) == file_sha
            entry["file_sha_match"] = match
            entry["sample_status"] = "MATCH" if match else "MISMATCH"
            if not match:
                mismatch += 1
        elif expected:
            # Rolling checksum is over records, not raw gzip — record presence only.
            entry["file_sha_match"] = None
            entry["sample_status"] = "CHECKSUM_FIELD_PRESENT_NO_FILE_DIGEST"
            entry["rolling_or_record_checksum"] = expected
        else:
            entry["sample_status"] = "NO_CHECKSUM_FIELD"
            findings.append(
                finding(
                    code="MANIFEST_MISSING_CHECKSUM_FIELD",
                    severity="HIGH",
                    summary="Sampled sealed manifest lacks checksum field",
                    evidence={"path": r["path"], "manifest_path": str(man_path)},
                )
            )
        samples.append(entry)

    if mismatch:
        findings.append(
            finding(
                code="CHECKSUM_SAMPLE_MISMATCH",
                severity="CRITICAL",
                summary=f"{mismatch} sampled manifests disagree with file digest",
                evidence={"mismatch_count": mismatch},
                recommendation="Coordinator: safe-stop; quarantine mismatched partitions (no rewrite)",
            )
        )
    if unreadable:
        findings.append(
            finding(
                code="MANIFEST_UNREADABLE_SAMPLE",
                severity="HIGH",
                summary=f"{unreadable} sampled manifests unreadable",
                evidence={"unreadable_count": unreadable},
            )
        )

    sealed_ratio = (len(sealed) / len(rows)) if rows else 0.0
    status = "PASS"
    if any(f["severity"] == "CRITICAL" for f in findings):
        status = "FAIL"
    elif findings:
        status = "WARN"

    return {
        "schema": "v14_a_manifest_checksum_sample",
        "observed_at": utc_stamp(),
        "campaign_id": campaign_id,
        "status": status,
        "partition_count": len(rows),
        "sealed_count": len(sealed),
        "open_tail_count": len(open_tails),
        "sealed_ratio": round(sealed_ratio, 4),
        "sample_size": len(samples),
        "sample_max": sample_max,
        "mismatch_count": mismatch,
        "unreadable_count": unreadable,
        "samples": samples,
        "findings": findings,
        "silent_fallback": False,
    }
