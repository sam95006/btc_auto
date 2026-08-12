"""Microstructure campaign finalizer V1 — synthetic/offline data-quality audit only.

Does not touch live capture processes, does not run Event Study, and never claims
profitability or strategy readiness.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.storage_metrics import audit_partition_file

SCHEMA = "microstructure_campaign_finalizer_v1"

# Frozen hold gates — readiness stays NOT_READY until all are satisfied + founder auth.
EVENT_STUDY_HOLD_GATES = {
    "calendar_days": 14,
    "complete_UTC_day_coverage": True,
    "symbol_diversity": 25,
    "liquidation_event_count": 500,
    "integrity_status": "PASS",
    "Founder_authorization": True,
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replay_partition_checksum(path: Path) -> dict[str, Any]:
    """Recompute uncompressed content checksum; detect truncated gzip tails."""
    if not path.is_file():
        return {
            "path": str(path),
            "replayed_checksum": None,
            "integrity_status": "MISSING",
            "truncated_tail": False,
            "error": "file_missing",
        }
    h = hashlib.sha256()
    truncated = False
    error = None
    try:
        with gzip.open(path, "rb") as fh:
            while True:
                chunk = fh.read(1024 * 256)
                if not chunk:
                    break
                h.update(chunk)
    except EOFError as exc:
        truncated = True
        error = f"EOFError:{exc}"
        return {
            "path": str(path),
            "replayed_checksum": None,
            "integrity_status": "TRUNCATED_OR_INCOMPLETE",
            "truncated_tail": True,
            "error": error,
        }
    except Exception as exc:  # noqa: BLE001 — audit must not abort finalize
        return {
            "path": str(path),
            "replayed_checksum": None,
            "integrity_status": "READ_FAILED",
            "truncated_tail": False,
            "error": f"{type(exc).__name__}:{exc}",
        }
    return {
        "path": str(path),
        "replayed_checksum": h.hexdigest(),
        "integrity_status": "OK",
        "truncated_tail": truncated,
        "error": None,
    }


def _manifest_path_for(gz_path: Path) -> Path:
    alt = gz_path.with_name(gz_path.name.replace(".jsonl.gz", ".manifest.json"))
    if alt.exists():
        return alt
    sibling = gz_path.with_suffix(".manifest.json")
    if sibling.exists():
        return sibling
    return alt


def discover_partitions(partitions_root: Path) -> list[dict[str, Any]]:
    """Scan partition tree and pair gzip payloads with manifests."""
    found: list[dict[str, Any]] = []
    if not partitions_root.is_dir():
        return found
    for gz in sorted(partitions_root.rglob("*.jsonl.gz")):
        man_path = _manifest_path_for(gz)
        manifest: dict[str, Any] = {}
        if man_path.is_file():
            try:
                manifest = _load_json(man_path)
            except Exception as exc:  # noqa: BLE001
                manifest = {"_manifest_load_error": f"{type(exc).__name__}:{exc}"}
        replay = replay_partition_checksum(gz)
        file_audit = audit_partition_file(gz)
        expected = (
            manifest.get("rolling_checksum")
            or manifest.get("checksum")
            or manifest.get("replayed_checksum")
        )
        checksum_match = bool(
            replay.get("replayed_checksum")
            and expected
            and replay["replayed_checksum"] == expected
        )
        integrity = replay["integrity_status"]
        if integrity == "OK" and expected and not checksum_match:
            integrity = "CHECKSUM_MISMATCH"
        found.append(
            {
                "path": str(gz),
                "manifest_path": str(man_path) if man_path.is_file() else None,
                "partition_id": manifest.get("partition_id") or gz.stem,
                "exchange": manifest.get("exchange"),
                "family": manifest.get("family"),
                "symbol": manifest.get("symbol"),
                "UTC_hour": manifest.get("UTC_hour"),
                "record_count": int(manifest.get("record_count") or file_audit.get("event_count") or 0),
                "first_exchange_timestamp": manifest.get("first_exchange_timestamp"),
                "last_exchange_timestamp": manifest.get("last_exchange_timestamp"),
                "previous_partition_id": manifest.get("previous_partition_id"),
                "capture_session_id": manifest.get("capture_session_id"),
                "rolling_checksum": expected,
                "replayed_checksum": replay.get("replayed_checksum"),
                "checksum_match": checksum_match if expected else None,
                "integrity_status": integrity,
                "truncated_tail": bool(replay.get("truncated_tail")),
                "compressed_bytes": int(file_audit.get("partition_compressed_bytes") or 0),
                "uncompressed_bytes": int(file_audit.get("partition_uncompressed_bytes") or 0),
                "manifest_present": man_path.is_file(),
            }
        )
    return found


def account_utc_hours(partitions: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify UTC hours as complete (full 3600s span) or partial."""
    by_hour: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in partitions:
        hour = p.get("UTC_hour")
        if not hour:
            continue
        by_hour[str(hour)].append(p)

    complete = 0
    partial = 0
    details: list[dict[str, Any]] = []
    for hour, parts in sorted(by_hour.items()):
        intact = [p for p in parts if p.get("integrity_status") == "OK" and p.get("checksum_match") is not False]
        if not intact:
            partial += 1
            details.append({"UTC_hour": hour, "status": "PARTIAL", "reason": "no_intact_partition"})
            continue
        firsts = [int(p["first_exchange_timestamp"]) for p in intact if p.get("first_exchange_timestamp") is not None]
        lasts = [int(p["last_exchange_timestamp"]) for p in intact if p.get("last_exchange_timestamp") is not None]
        if not firsts or not lasts:
            partial += 1
            details.append({"UTC_hour": hour, "status": "PARTIAL", "reason": "missing_timestamps"})
            continue
        span_ms = max(lasts) - min(firsts)
        # Complete hour: coverage spans >= 59 minutes of exchange time within the hour key.
        if span_ms >= 59 * 60 * 1000 and all(p.get("manifest_present") for p in intact):
            complete += 1
            details.append({"UTC_hour": hour, "status": "COMPLETE", "span_ms": span_ms, "partition_count": len(intact)})
        else:
            partial += 1
            details.append({"UTC_hour": hour, "status": "PARTIAL", "span_ms": span_ms, "partition_count": len(intact)})
    return {
        "complete_UTC_hours": complete,
        "partial_UTC_hours": partial,
        "UTC_hour_count": len(by_hour),
        "hours": details,
    }


def score_clock_quality(clock: dict[str, Any] | None) -> dict[str, Any]:
    clock = clock or {}
    samples = int(clock.get("server_clock_sample_count") or clock.get("sample_count") or 0)
    p95 = clock.get("local_minus_server_clock_offset_ms_p95")
    if p95 is None:
        p95 = clock.get("offset_ms_p95")
    status = "UNKNOWN"
    if samples <= 0 or p95 is None:
        status = "UNKNOWN"
    elif abs(float(p95)) <= 50:
        status = "GOOD"
    elif abs(float(p95)) <= 250:
        status = "ACCEPTABLE"
    else:
        status = "POOR"
    return {
        "clock_quality": status,
        "server_clock_sample_count": samples,
        "local_minus_server_clock_offset_ms_p95": p95,
    }


def score_heartbeat_quality(hb: dict[str, Any] | None) -> dict[str, Any]:
    hb = hb or {}
    status = hb.get("heartbeat_status") or "UNKNOWN"
    quality = "UNKNOWN"
    if status == "HEARTBEAT_VERIFIED":
        quality = "GOOD"
    elif status in {"HEARTBEAT_ACK_PARSING_FAILED", "HEARTBEAT_TIMEOUT"}:
        quality = "POOR"
    elif status == "UNKNOWN":
        quality = "UNKNOWN"
    else:
        quality = "ACCEPTABLE"
    return {
        "heartbeat_quality": quality,
        "heartbeat_status": status,
        "heartbeat_send_count": hb.get("heartbeat_send_count") or hb.get("send_count"),
        "heartbeat_ack_count": hb.get("heartbeat_ack_count") or hb.get("ack_count"),
        "heartbeat_timeout_count": hb.get("heartbeat_timeout_count") or hb.get("timeout_count"),
    }


def score_memory_quality(mem: dict[str, Any] | None) -> dict[str, Any]:
    mem = mem or {}
    growth = mem.get("memory_growth_status") or "UNKNOWN"
    quality = "UNKNOWN"
    if growth == "STABLE":
        quality = "GOOD"
    elif growth in {"BOUNDED_GROWTH", "ACCEPTABLE"}:
        quality = "ACCEPTABLE"
    elif growth in {"LINEAR_GROWTH_DETECTED", "INSTRUMENTATION_FAILED"}:
        quality = "POOR"
    return {
        "memory_quality": quality,
        "memory_growth_status": growth,
        "process_RSS_peak_bytes": mem.get("process_RSS_peak_bytes"),
        "RSS_growth_per_million_events": mem.get("RSS_growth_per_million_events"),
    }


def audit_cross_partition_linkage(partitions: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify previous_partition_id chains within (session, family, symbol)."""
    by_key: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for p in partitions:
        key = (p.get("capture_session_id"), p.get("family"), p.get("symbol"))
        by_key[key].append(p)

    broken = 0
    checked = 0
    issues: list[dict[str, Any]] = []
    for key, parts in by_key.items():
        # Stable order by UTC_hour then partition_id
        ordered = sorted(parts, key=lambda x: (str(x.get("UTC_hour") or ""), str(x.get("partition_id") or "")))
        ids = {p.get("partition_id") for p in ordered}
        prev: str | None = None
        for p in ordered:
            checked += 1
            claimed = p.get("previous_partition_id")
            if prev is None:
                if claimed not in (None, "", "null"):
                    # First partition should have null predecessor unless resume mid-chain.
                    if claimed not in ids:
                        broken += 1
                        issues.append(
                            {
                                "partition_id": p.get("partition_id"),
                                "issue": "orphan_previous_partition_id",
                                "previous_partition_id": claimed,
                            }
                        )
            else:
                if claimed != prev:
                    broken += 1
                    issues.append(
                        {
                            "partition_id": p.get("partition_id"),
                            "issue": "linkage_break",
                            "expected_previous": prev,
                            "claimed_previous": claimed,
                        }
                    )
            prev = p.get("partition_id")
    status = "PASS" if broken == 0 else "FAIL"
    return {
        "cross_partition_linkage_status": status,
        "chains_checked": len(by_key),
        "partitions_checked": checked,
        "linkage_breaks": broken,
        "issues": issues[:50],
    }


def evaluate_storage_cap(
    *,
    compressed_bytes: int,
    soft_cap: int | None,
    hard_cap: int | None,
    budget_status: str | None = None,
) -> dict[str, Any]:
    outcome = "WITHIN_CAPS"
    if hard_cap is not None and compressed_bytes >= hard_cap:
        outcome = "HARD_CAP_HIT"
    elif soft_cap is not None and compressed_bytes >= soft_cap:
        outcome = "SOFT_CAP_HIT"
    if budget_status == "STORAGE_BUDGET_BLOCKED":
        outcome = "HARD_CAP_HIT"
    elif budget_status == "DEGRADED_STORAGE_MODE" and outcome == "WITHIN_CAPS":
        outcome = "SOFT_CAP_HIT"
    return {
        "storage_cap_outcome": outcome,
        "compressed_bytes": compressed_bytes,
        "soft_storage_cap_bytes": soft_cap,
        "hard_storage_cap_bytes": hard_cap,
        "storage_cap_respected": outcome != "HARD_CAP_HIT" or budget_status == "STORAGE_BUDGET_BLOCKED",
        "budget_status": budget_status,
    }


def evaluate_event_study_readiness(metrics: dict[str, Any]) -> dict[str, Any]:
    """Apply frozen gates. Always returns NOT_READY unless every gate is met."""
    calendar_days = float(metrics.get("calendar_days") or 0)
    complete_days = bool(metrics.get("complete_UTC_day_coverage"))
    symbols = int(metrics.get("symbol_diversity") or metrics.get("symbol_count") or 0)
    liqs = int(metrics.get("liquidation_event_count") or 0)
    integrity = metrics.get("integrity_status") or "UNKNOWN"
    founder = bool(metrics.get("Founder_authorization"))

    gates = {
        "calendar_days": {
            "required": EVENT_STUDY_HOLD_GATES["calendar_days"],
            "actual": calendar_days,
            "passed": calendar_days >= EVENT_STUDY_HOLD_GATES["calendar_days"],
        },
        "complete_UTC_day_coverage": {
            "required": True,
            "actual": complete_days,
            "passed": complete_days is True,
        },
        "symbol_diversity": {
            "required": EVENT_STUDY_HOLD_GATES["symbol_diversity"],
            "actual": symbols,
            "passed": symbols >= EVENT_STUDY_HOLD_GATES["symbol_diversity"],
        },
        "liquidation_event_count": {
            "required": EVENT_STUDY_HOLD_GATES["liquidation_event_count"],
            "actual": liqs,
            "passed": liqs >= EVENT_STUDY_HOLD_GATES["liquidation_event_count"],
        },
        "integrity_status": {
            "required": "PASS",
            "actual": integrity,
            "passed": integrity == "PASS",
        },
        "Founder_authorization": {
            "required": True,
            "actual": founder,
            "passed": founder is True,
        },
    }
    all_passed = all(g["passed"] for g in gates.values())
    # Explicit hard rule: never claim READY from this finalizer without founder auth + depth.
    status = "READY" if all_passed else "NOT_READY"
    blockers = [name for name, g in gates.items() if not g["passed"]]
    return {
        "schema": "event_study_readiness_v1",
        "event_study_readiness_status": status,
        "event_study_real_execution": False,
        "hold_gates": EVENT_STUDY_HOLD_GATES,
        "gate_results": gates,
        "blockers": blockers,
        "note": "Event Study remains blocked until frozen hold gates and Founder authorization are satisfied",
        "created_at": _utc(),
    }


def extract_resume_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    resume = meta.get("resume") or meta.get("campaign_resume_metadata") or {}
    return {
        "campaign_resume_metadata": {
            "resumable": bool(resume.get("resumable", meta.get("resumable", False))),
            "last_checkpoint_at": resume.get("last_checkpoint_at") or meta.get("last_checkpoint_at"),
            "last_partition_id": resume.get("last_partition_id"),
            "checkpoint_path": resume.get("checkpoint_path"),
            "accumulation_run_id": resume.get("accumulation_run_id") or meta.get("accumulation_run_id"),
            "capture_session_ids": list(
                resume.get("capture_session_ids")
                or meta.get("session_ids")
                or meta.get("capture_session_ids")
                or []
            ),
            "resume_token": resume.get("resume_token"),
            "clean_shutdown": resume.get("clean_shutdown"),
        }
    }


def finalize_campaign(
    campaign_root: Path,
    *,
    output_dir: Path | None = None,
    write_artifacts: bool = False,
) -> dict[str, Any]:
    """Finalize a campaign from offline/synthetic partition fixtures.

    Expected layout under campaign_root:
      campaign_meta.json
      partitions/**/*.jsonl.gz (+ sibling .manifest.json)
    """
    campaign_root = Path(campaign_root)
    meta_path = campaign_root / "campaign_meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"campaign_meta.json missing under {campaign_root}")
    meta = _load_json(meta_path)
    partitions_root = campaign_root / "partitions"
    partitions = discover_partitions(partitions_root)

    # --- valid capture vs gaps (never equate wall clock with valid capture) ---
    valid_capture_seconds = int(meta.get("valid_capture_seconds") or 0)
    connection_gap_seconds = int(meta.get("connection_gap_seconds") or 0)
    wall_elapsed_seconds = int(meta.get("wall_elapsed_seconds") or 0)
    if valid_capture_seconds == 0 and meta.get("sessions"):
        for s in meta["sessions"]:
            valid_capture_seconds += int(s.get("valid_capture_seconds") or 0)
            connection_gap_seconds += int(s.get("connection_gap_seconds") or 0)

    hour_acct = account_utc_hours(partitions)
    symbols = sorted(
        {
            *(meta.get("symbol_coverage") or []),
            *(p.get("symbol") for p in partitions if p.get("symbol")),
        }
    )

    trade_events = int(meta.get("trade_event_count") or 0)
    liq_events = int(meta.get("liquidation_event_count") or 0)
    if trade_events == 0 and liq_events == 0:
        for p in partitions:
            if p.get("family") == "AGGRESSIVE_TRADE_FLOW":
                trade_events += int(p.get("record_count") or 0)
            elif p.get("family") == "LIQUIDATION_EVENTS":
                liq_events += int(p.get("record_count") or 0)

    intact = [p for p in partitions if p.get("integrity_status") == "OK" and p.get("checksum_match") is not False]
    truncated = [p for p in partitions if p.get("truncated_tail") or p.get("integrity_status") == "TRUNCATED_OR_INCOMPLETE"]
    checksum_failures = [
        p for p in partitions if p.get("checksum_match") is False or p.get("integrity_status") == "CHECKSUM_MISMATCH"
    ]
    missing_manifest = [p for p in partitions if not p.get("manifest_present")]

    partition_completeness = {
        "partition_count": len(partitions),
        "intact_partition_count": len(intact),
        "truncated_or_incomplete_partition_count": len(truncated),
        "checksum_mismatch_count": len(checksum_failures),
        "missing_manifest_count": len(missing_manifest),
        "partition_completeness_status": (
            "COMPLETE"
            if partitions and len(intact) == len(partitions) and not missing_manifest
            else ("PARTIAL" if intact else "EMPTY")
        ),
    }

    checksum_replay = {
        "checksum_replay_verified": len(checksum_failures) == 0
        and len(truncated) == 0
        and all(p.get("checksum_match") for p in partitions if p.get("rolling_checksum")),
        "partitions_replayed": len(partitions),
        "failures": [
            {
                "partition_id": p.get("partition_id"),
                "integrity_status": p.get("integrity_status"),
                "expected": p.get("rolling_checksum"),
                "replayed": p.get("replayed_checksum"),
            }
            for p in partitions
            if p.get("checksum_match") is False or p.get("truncated_tail")
        ][:50],
    }

    truncated_tail = {
        "truncated_tail_detected": len(truncated) > 0,
        "truncated_partition_count": len(truncated),
        "partition_ids": [p.get("partition_id") for p in truncated],
    }

    linkage = audit_cross_partition_linkage(partitions)
    compressed_bytes = sum(int(p.get("compressed_bytes") or 0) for p in partitions)
    cfg = meta.get("config") or {}
    storage = evaluate_storage_cap(
        compressed_bytes=int(meta.get("compressed_bytes") or compressed_bytes),
        soft_cap=cfg.get("soft_storage_cap_bytes", meta.get("soft_storage_cap_bytes")),
        hard_cap=cfg.get("hard_storage_cap_bytes", meta.get("hard_storage_cap_bytes")),
        budget_status=(meta.get("budget") or {}).get("status") or meta.get("budget_status"),
    )

    clock_q = score_clock_quality(meta.get("clock") or meta.get("clock_report"))
    hb_q = score_heartbeat_quality(meta.get("heartbeat") or meta.get("heartbeat_report"))
    mem_q = score_memory_quality(meta.get("memory") or meta.get("memory_report"))
    resume = extract_resume_metadata(meta)

    integrity_status = "PASS"
    if truncated or checksum_failures or missing_manifest or linkage["cross_partition_linkage_status"] != "PASS":
        integrity_status = "FAIL"
    elif not partitions:
        integrity_status = "EMPTY"

    calendar_days = float(meta.get("calendar_days") or 0)
    if calendar_days <= 0 and valid_capture_seconds > 0:
        # Valid capture alone must not invent calendar depth.
        calendar_days = 0.0
    complete_day_coverage = bool(meta.get("complete_UTC_day_coverage", False))
    if hour_acct["complete_UTC_hours"] < 24:
        complete_day_coverage = False

    readiness = evaluate_event_study_readiness(
        {
            "calendar_days": calendar_days,
            "complete_UTC_day_coverage": complete_day_coverage,
            "symbol_diversity": len(symbols),
            "liquidation_event_count": liq_events,
            "integrity_status": integrity_status,
            "Founder_authorization": bool(meta.get("Founder_authorization", False)),
        }
    )
    # Hard invariant for this agent: never emit READY from synthetic finalize package.
    if readiness["event_study_readiness_status"] != "NOT_READY" and not meta.get("Founder_authorization"):
        readiness["event_study_readiness_status"] = "NOT_READY"
        readiness["blockers"] = list(dict.fromkeys([*readiness.get("blockers", []), "Founder_authorization"]))

    clean = (
        integrity_status == "PASS"
        and checksum_replay["checksum_replay_verified"]
        and not truncated_tail["truncated_tail_detected"]
        and bool((resume["campaign_resume_metadata"].get("clean_shutdown") is not False))
    )

    data_quality_audit = {
        "schema": "microstructure_campaign_data_quality_audit_v1",
        "valid_capture_seconds": valid_capture_seconds,
        "valid_capture_hours": valid_capture_seconds / 3600.0,
        "wall_elapsed_seconds": wall_elapsed_seconds,
        "connection_gap_seconds": connection_gap_seconds,
        "connection_gap_accounting": {
            "connection_gap_seconds": connection_gap_seconds,
            "gap_events": meta.get("gap_events") or [],
            "note": "valid_capture_seconds excludes connection gaps; wall clock is not used as capture depth",
        },
        **hour_acct,
        "symbol_coverage": symbols,
        "symbol_count": len(symbols),
        "trade_event_count": trade_events,
        "liquidation_event_count": liq_events,
        **clock_q,
        **hb_q,
        **mem_q,
        "checksum_replay": checksum_replay,
        "partition_completeness": partition_completeness,
        "truncated_tail_detection": truncated_tail,
        "cross_partition_linkage": linkage,
        "storage_cap": storage,
        **resume,
        "integrity_status": integrity_status,
        "partitions": [
            {
                "partition_id": p.get("partition_id"),
                "symbol": p.get("symbol"),
                "family": p.get("family"),
                "UTC_hour": p.get("UTC_hour"),
                "integrity_status": p.get("integrity_status"),
                "checksum_match": p.get("checksum_match"),
                "truncated_tail": p.get("truncated_tail"),
                "previous_partition_id": p.get("previous_partition_id"),
            }
            for p in partitions
        ],
        "created_at": _utc(),
    }

    finalizer_status = {
        "schema": SCHEMA,
        "Microstructure_Finalizer_status": "PASS" if clean else "FAIL",
        "campaign_id": meta.get("campaign_id"),
        "clean_campaign_finalization": clean,
        "valid_capture_hours": valid_capture_seconds / 3600.0,
        "connection_gap_seconds": connection_gap_seconds,
        "complete_UTC_hours": hour_acct["complete_UTC_hours"],
        "partial_UTC_hours": hour_acct["partial_UTC_hours"],
        "symbol_coverage": symbols,
        "symbol_count": len(symbols),
        "clock_quality": clock_q["clock_quality"],
        "heartbeat_quality": hb_q["heartbeat_quality"],
        "memory_quality": mem_q["memory_quality"],
        "checksum_replay_verified": checksum_replay["checksum_replay_verified"],
        "partition_completeness_status": partition_completeness["partition_completeness_status"],
        "truncated_tail_detected": truncated_tail["truncated_tail_detected"],
        "cross_partition_linkage_status": linkage["cross_partition_linkage_status"],
        "storage_cap_outcome": storage["storage_cap_outcome"],
        "campaign_resume_metadata": resume["campaign_resume_metadata"],
        "integrity_status": integrity_status,
        "event_study_readiness_status": readiness["event_study_readiness_status"],
        "event_study_real_execution": False,
        "new_strategy_generated_count": 0,
        "profitability_claim_count": 0,
        "synthetic_fixtures_only": True,
        "live_campaign_interfered": False,
        "critical_findings": _critical_findings(data_quality_audit, readiness),
        "remaining_blockers": readiness.get("blockers") or [],
        "created_at": _utc(),
    }

    report = {
        "schema": "microstructure_campaign_finalize_report_v1",
        "finalizer_status": finalizer_status,
        "data_quality_audit": data_quality_audit,
        "event_study_readiness": readiness,
        "created_at": _utc(),
    }

    if write_artifacts and output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, payload in (
            ("finalizer_status.json", finalizer_status),
            ("data_quality_audit.json", data_quality_audit),
            ("event_study_readiness.json", readiness),
            ("campaign_finalize_report.json", report),
        ):
            (out / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return report


def _critical_findings(audit: dict[str, Any], readiness: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if audit.get("truncated_tail_detection", {}).get("truncated_tail_detected"):
        findings.append("truncated_tail_partitions_present")
    if not audit.get("checksum_replay", {}).get("checksum_replay_verified"):
        findings.append("checksum_replay_not_verified")
    if audit.get("cross_partition_linkage", {}).get("cross_partition_linkage_status") != "PASS":
        findings.append("cross_partition_linkage_breaks")
    if audit.get("partition_completeness", {}).get("partition_completeness_status") != "COMPLETE":
        findings.append("partition_set_incomplete")
    if audit.get("storage_cap", {}).get("storage_cap_outcome") == "HARD_CAP_HIT":
        findings.append("hard_storage_cap_hit")
    if readiness.get("event_study_readiness_status") == "NOT_READY":
        findings.append("event_study_hold_gates_unmet")
    # Informational: wall clock must not be treated as valid capture
    if int(audit.get("wall_elapsed_seconds") or 0) > int(audit.get("valid_capture_seconds") or 0):
        findings.append("wall_clock_exceeds_valid_capture_expected")
    return findings


def write_immutable_status_package(
    fixture_root: Path,
    artifact_dir: Path,
) -> dict[str, Any]:
    """Run finalizer on synthetic fixture and emit immutable readiness package."""
    report = finalize_campaign(fixture_root, output_dir=artifact_dir, write_artifacts=True)
    # Force explicit NOT_READY in published package (gates unmet for V9 synthetic finalize).
    readiness = report["event_study_readiness"]
    readiness["event_study_readiness_status"] = "NOT_READY"
    readiness["event_study_real_execution"] = False
    status = report["finalizer_status"]
    status["event_study_readiness_status"] = "NOT_READY"
    artifact_dir = Path(artifact_dir)
    (artifact_dir / "event_study_readiness.json").write_text(
        json.dumps(readiness, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "finalizer_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "campaign_finalize_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
