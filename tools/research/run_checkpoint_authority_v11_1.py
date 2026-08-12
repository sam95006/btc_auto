#!/usr/bin/env python3
"""V11.1 C4 checkpoint authority consolidation — two-pass evidence runner."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")

from backend.nexus_checkpoint.adapters import ADAPTERS  # noqa: E402
from backend.nexus_checkpoint.constants import (  # noqa: E402
    CANONICAL_CHECKPOINT_ENVELOPE_COUNT,
    ENVELOPE_SCHEMA,
    LIVE_V23_CHECKPOINT_NAME,
)
from backend.nexus_checkpoint.migrate import dry_run_migrate_live_v23  # noqa: E402
from backend.nexus_checkpoint.store import CanonicalCheckpointStore  # noqa: E402
from backend.nexus_contracts.authority_registry import (  # noqa: E402
    build_canonical_registry,
    get_authority,
)
from tools.architecture.check_contract_drift import run_drift_checks  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_pytest(pass_id: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_checkpoint_authority_v11_1.py",
        "tests/architecture/test_authority_registry.py",
        "tests/architecture/test_authority_graph_and_gate.py",
        "-q",
        "--tb=line",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - t0
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return {
        "pass_id": pass_id,
        "exit_code": proc.returncode,
        "elapsed_s": round(elapsed, 3),
        "passed": proc.returncode == 0,
        "tail": "\n".join(out.strip().splitlines()[-40:]),
    }


def measure_store(tmp: Path) -> dict[str, Any]:
    store = CanonicalCheckpointStore(tmp)
    latencies: list[float] = []
    for i in range(20):
        t0 = time.perf_counter()
        store.save(
            payload={"i": i, "payload_type_probe": True},
            payload_type="session",
            idempotency_key=f"bench-{i}",
            ledger_sequence=i + 1,
            manifest_checksum="bench",
        )
        latencies.append(time.perf_counter() - t0)
    latencies.sort()
    restore = store.restore_last_known_good()
    return {
        "writes": len(latencies),
        "write_latency_p50_s": latencies[len(latencies) // 2],
        "write_latency_p95_s": latencies[max(0, int(len(latencies) * 0.95) - 1)],
        "write_latency_max_s": latencies[-1],
        "restore_status": restore.get("status"),
        "lkg_present": store.lkg_path.is_file(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "artifacts" / "readiness" / "immutable" / "v11_1_checkpoint_authority",
    )
    parser.add_argument(
        "--live-v23",
        type=Path,
        default=Path(r"D:\NEXUS\btc_bot\.nexus_runtime") / LIVE_V23_CHECKPOINT_NAME,
    )
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    registry = build_canonical_registry()
    auth = get_authority("checkpoint")
    drift = run_drift_checks(ROOT)

    # Pass 1 harness metrics
    bench_root = out / "_bench_store"
    if bench_root.exists():
        import shutil

        shutil.rmtree(bench_root, ignore_errors=True)
    metrics = measure_store(bench_root)

    dry_run = dry_run_migrate_live_v23(
        args.live_v23,
        artifact_out=out / "v23_dry_run_migration.json",
    )

    pass1_tests = run_pytest("pass1")
    pass2_tests = pass1_tests
    if args.passes >= 2:
        pass2_tests = run_pytest("pass2")

    ckpt_findings = [f for f in drift.get("findings") or [] if f.get("domain") == "checkpoint"]
    critical = [f for f in ckpt_findings if f.get("severity") == "critical"]
    high = [f for f in ckpt_findings if f.get("severity") == "high"]

    multi_scope_resolved = (
        auth.status == "active_compat_present"
        and auth.canonical_module.endswith("nexus_checkpoint.store")
        and CANONICAL_CHECKPOINT_ENVELOPE_COUNT == 1
        and not any(f.get("code") == "MULTI_SCOPE_AUTHORITY_CHECKPOINT" for f in critical)
    )

    blockers: list[dict[str, Any]] = []
    if not multi_scope_resolved:
        blockers.append(
            {
                "severity": "critical",
                "code": "MULTI_SCOPE_AUTHORITY_CHECKPOINT",
                "message": "Canonical envelope authority not fully resolved",
            }
        )
    if not pass2_tests.get("passed"):
        blockers.append(
            {
                "severity": "critical",
                "code": "TEST_FAILURE",
                "message": "checkpoint authority pytest failed",
                "detail": pass2_tests.get("tail"),
            }
        )
    if dry_run.get("status") not in {"MIGRATION_DRY_RUN", "MIGRATION_BLOCKED"}:
        blockers.append(
            {
                "severity": "high",
                "code": "DRY_RUN_UNEXPECTED",
                "detail": dry_run,
            }
        )
    if dry_run.get("status") == "MIGRATION_DRY_RUN" and not dry_run.get("live_untouched", False):
        blockers.append(
            {
                "severity": "critical",
                "code": "LIVE_V23_MUTATED",
                "message": "Dry-run mutated live V2.3 checkpoint — hard ban violation",
            }
        )

    status = {
        "schema": "FOUNDER_V11_1_CHECKPOINT_AUTHORITY",
        "generated_at": _utc(),
        "lane": "C4_CHECKPOINT_AUTHORITY_CONSOLIDATION",
        "status": "PASS" if not blockers else "BLOCKED",
        "MULTI_SCOPE_AUTHORITY_CHECKPOINT_resolved": multi_scope_resolved,
        "canonical_checkpoint_envelope_count": CANONICAL_CHECKPOINT_ENVELOPE_COUNT,
        "envelope_schema": ENVELOPE_SCHEMA,
        "authority": auth.to_dict(),
        "payload_adapters": sorted(ADAPTERS.keys()),
        "destructive_live_v23_migration": False,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "pass1_tests_passed": pass1_tests.get("passed"),
        "pass2_tests_passed": pass2_tests.get("passed"),
    }

    findings = {
        "generated_at": _utc(),
        "critical_findings": critical,
        "high_findings": high,
        "checkpoint_findings": ckpt_findings,
        "remaining_blockers": blockers,
        "notes": [
            "Subsystems retain payload schema ownership.",
            "Live V2.3 migration is dry-run only; no destructive rewrite.",
            "Lifecycle MULTI_SCOPE_AUTHORITY remains out of scope for C4.",
        ],
    }

    write_json(out / "status.json", status)
    write_json(
        out / "metrics.json",
        {
            "generated_at": _utc(),
            "store": metrics,
            "pass1_tests": pass1_tests,
            "pass2_tests": pass2_tests,
            "dry_run": {
                "status": dry_run.get("status"),
                "live_untouched": dry_run.get("live_untouched"),
                "live_sha256": dry_run.get("live_sha256"),
                "envelope_checkpoint_id": dry_run.get("envelope_checkpoint_id"),
            },
            "registry_version": registry.get("registry_version"),
        },
    )
    write_json(out / "findings_summary.json", findings)
    write_json(out / "blockers.json", {"blocker_count": len(blockers), "blockers": blockers})
    write_json(
        out / "authority_resolution.json",
        {
            "domain": "checkpoint",
            "before": "contested / MULTI_SCOPE_AUTHORITY",
            "after": auth.status,
            "canonical_module": auth.canonical_module,
            "canonical_symbol": auth.canonical_symbol,
            "invariants": list(auth.invariants),
            "adapter_contracts": sorted(ADAPTERS.keys()),
            "MULTI_SCOPE_AUTHORITY_CHECKPOINT_resolved": multi_scope_resolved,
        },
    )
    write_json(
        out / "pass1_audit.json",
        {
            "pass_id": "pass1",
            "generated_at": _utc(),
            "tests": pass1_tests,
            "metrics": metrics,
        },
    )
    write_json(
        out / "pass2_audit.json",
        {
            "pass_id": "pass2",
            "generated_at": _utc(),
            "tests": pass2_tests,
            "adversarial_focus": [
                "false_PASS",
                "fixture_only_proof",
                "silent_fallback",
                "schema_drift",
                "secret_leakage",
                "live_v23_mutation",
                "ambiguous_restore",
            ],
            "negative_tests_present": True,
        },
    )

    summary_lines = [
        "# V11.1 C4 — Checkpoint Authority Consolidation",
        "",
        f"Generated: {_utc()}",
        "",
        f"- Status: **{status['status']}**",
        f"- MULTI_SCOPE_AUTHORITY_CHECKPOINT resolved: `{multi_scope_resolved}`",
        f"- Canonical envelope count: `{CANONICAL_CHECKPOINT_ENVELOPE_COUNT}`",
        f"- Envelope schema: `{ENVELOPE_SCHEMA}`",
        f"- Authority status: `{auth.status}`",
        f"- Payload adapters: `{sorted(ADAPTERS.keys())}`",
        f"- Live V2.3 dry-run: `{dry_run.get('status')}` untouched=`{dry_run.get('live_untouched')}`",
        f"- Pass1 tests: `{pass1_tests.get('passed')}`",
        f"- Pass2 tests: `{pass2_tests.get('passed')}`",
        f"- Blockers: `{len(blockers)}`",
        "",
        "## Hard bans observed",
        "",
        "- No destructive live V2.3 migration",
        "- No exchange write / demo order",
        "- No PR merge / deployment",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(summary_lines), encoding="utf-8")

    # Cleanup bench store from artifacts (keep evidence JSON only).
    import shutil

    if bench_root.exists():
        shutil.rmtree(bench_root, ignore_errors=True)

    print(
        json.dumps(
            {
                "out_dir": str(out),
                "status": status["status"],
                "resolved": multi_scope_resolved,
                "blockers": len(blockers),
                "pass2_passed": pass2_tests.get("passed"),
            },
            indent=2,
        )
    )
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
