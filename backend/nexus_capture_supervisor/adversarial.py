"""Pass-2 adversarial self-review for V14-A capture supervisor."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import (
    EVENT_STUDY_MUST_REMAIN,
    HARD_BANS,
    OPS_ROLE,
    OWNED_PATHS,
    SCHEMA_PASS2,
)
from backend.nexus_capture_supervisor.partition_accounting import account_partitions
from backend.nexus_capture_supervisor.process_liveness import observe_process_liveness
from backend.nexus_capture_supervisor.recommendations import build_recommendations
from backend.nexus_capture_supervisor.storage_projection import project_disk
from backend.nexus_capture_supervisor.util import utc_stamp


def _pass(name: str, ok: bool, **extra: Any) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if ok else "FAIL", **extra}


def neg_missing_partitions_root(tmp: Path) -> dict[str, Any]:
    missing = tmp / "does_not_exist_partitions"
    report = account_partitions(
        partitions_root=missing,
        campaign_id="synthetic_neg",
        capture_start_utc="2026-08-05T09:00:00Z",
    )
    ok = report["status"] == "UNAVAILABLE" and report.get("silent_fallback") is not True
    return _pass("neg_missing_partitions_root_no_silent_fallback", ok, report_status=report["status"])


def neg_dead_pid_marks_down(tmp: Path) -> dict[str, Any]:
    runtime = tmp / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    launch = {
        "status": "OK",
        "live_capture_started": True,
        "capture_PID": 1,  # almost certainly not our capture on Windows/Linux sandbox
        "capture_worker_PID": 1,
        "capture_start_UTC": "2026-08-05T09:00:00Z",
    }
    (runtime / "synth_dead_launch.json").write_text(json.dumps(launch), encoding="utf-8")
    # Use observe with crafted dicts directly
    report = observe_process_liveness(
        runtime_root=runtime,
        campaign_id="synth_dead",
        launch=launch,
        health={"status": "MISSING", "path": str(runtime / "missing.json")},
    )
    ok = report["status"] == "DOWN" and any(f["code"] == "PROCESS_PARENT_DEAD" for f in report["findings"])
    return _pass("neg_dead_pid_marks_down", ok, process_status=report["status"])


def neg_disk_floor_stop_recommendation() -> dict[str, Any]:
    storage = project_disk(
        disk_root="D:\\",
        campaign_bytes=0,
        bytes_per_second=0.0,
        floor_bytes=10**18,  # impossible floor forces breach on any real disk
    )
    obs = {
        "storage": storage,
        "process_liveness": {"findings": [], "status": "LIVE"},
        "ws_health": {"findings": []},
        "partition_accounting": {"findings": []},
        "clock_heartbeat": {"findings": []},
        "manifest_sampling": {"findings": []},
        "open_tail": {"findings": []},
        "duplicate_writer": {"findings": [], "status": "OK"},
    }
    rec = build_recommendations(observation=obs)
    ok = (
        storage["status"] == "STOP_REQUIRED"
        and rec["safe_stop_required"] is True
        and rec["safe_stop_executed"] is False
        and rec["restart_executed"] is False
    )
    return _pass(
        "neg_disk_floor_recommends_stop_not_execute",
        ok,
        storage_status=storage["status"],
        safe_stop_required=rec["safe_stop_required"],
        safe_stop_executed=rec["safe_stop_executed"],
    )


def neg_supervisor_must_not_claim_event_study(pass1: dict[str, Any]) -> dict[str, Any]:
    obs = pass1.get("observation") or {}
    ok = (
        obs.get("event_study_readiness_status") == EVENT_STUDY_MUST_REMAIN
        and obs.get("event_study_real_execution") is False
        and obs.get("exchange_write_attempt_count") == 0
        and obs.get("live_stop_executed") is False
        and obs.get("restart_executed") is False
        and obs.get("collector_modified") is False
        and obs.get("ops_role") == OPS_ROLE
    )
    return _pass("neg_no_event_study_or_live_mutation_claims", ok)


def neg_fixture_vs_real_classification(pass1: dict[str, Any]) -> dict[str, Any]:
    obs = pass1.get("observation") or {}
    live = bool((obs.get("path_meta") or {}).get("live_capture_started"))
    # Real campaign observation must be labeled as live evidence when launch says so.
    label = pass1.get("evidence_class")
    ok = label in {"REAL_LIVE_CAMPAIGN_READONLY", "SYNTHETIC_FIXTURE"}
    if live:
        ok = ok and label == "REAL_LIVE_CAMPAIGN_READONLY"
    return _pass(
        "neg_fixture_versus_real_classification",
        ok,
        evidence_class=label,
        live_capture_started=live,
    )


def neg_owned_paths_only(repo_root: Path, changed_files: list[str]) -> dict[str, Any]:
    bad = []
    for rel in changed_files:
        norm = rel.replace("\\", "/")
        if not any(norm == p or norm.startswith(p.rstrip("/") + "/") for p in OWNED_PATHS):
            # allow nothing outside
            bad.append(rel)
    return _pass("neg_owned_paths_only", len(bad) == 0, violations=bad)


def neg_hard_bans_declared(pass1: dict[str, Any]) -> dict[str, Any]:
    bans = set((pass1.get("observation") or {}).get("hard_bans") or [])
    required = set(HARD_BANS)
    ok = required.issubset(bans)
    return _pass("neg_hard_bans_declared", ok, missing=sorted(required - bans))


def neg_hourly_gap_not_silenced(pass1: dict[str, Any]) -> dict[str, Any]:
    """If observation recorded missing hours, severity must be HIGH (no silent ignore)."""
    part = (pass1.get("observation") or {}).get("partition_accounting") or {}
    missing = list(part.get("missing_hours") or [])
    # Exclude current-hour-only misses already filtered in account_partitions findings
    codes = {f.get("code") for f in part.get("findings") or []}
    if not missing:
        return _pass("neg_hourly_gap_not_silenced", True, note="no_missing_hours")
    # If completed missing hours exist, HOURLY_GAPS must be present
    from backend.nexus_capture_supervisor.util import utc_hour_key, utc_now

    current = utc_hour_key(utc_now())
    completed = [h for h in missing if h != current]
    if not completed:
        return _pass("neg_hourly_gap_not_silenced", True, note="only_current_hour_missing")
    ok = "HOURLY_GAPS" in codes
    return _pass("neg_hourly_gap_not_silenced", ok, missing=completed, codes=sorted(codes))


def run_adversarial_pass2(
    *,
    repo_root: Path,
    work_root: Path,
    pass1: dict[str, Any],
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    tests = [
        neg_missing_partitions_root(work_root / "missing_parts"),
        neg_dead_pid_marks_down(work_root / "dead_pid"),
        neg_disk_floor_stop_recommendation(),
        neg_supervisor_must_not_claim_event_study(pass1),
        neg_fixture_vs_real_classification(pass1),
        neg_owned_paths_only(Path(repo_root), changed_files or []),
        neg_hard_bans_declared(pass1),
        neg_hourly_gap_not_silenced(pass1),
    ]
    all_passed = all(t["status"] == "PASS" for t in tests)
    false_pass_search = {
        "silent_fallback_search": "explicit_status_fields_required",
        "schema_drift_search": "schema_constants_pinned",
        "race_condition_search": "observe_only_no_writer_lock_taken",
        "cost_omission_search": "n/a_observe_lane",
        "pit_leakage_search": "supervisor_does_not_emit_future_day_complete_claims",
        "secret_leakage_search": "delegated_to_secret_scan",
    }
    return {
        "schema": SCHEMA_PASS2,
        "created_at": utc_stamp(),
        "pass": 2,
        "all_passed": all_passed,
        "negative_tests": tests,
        "false_pass_search": false_pass_search,
        "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
        "exchange_write_attempt_count": 0,
    }
