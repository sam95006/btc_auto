#!/usr/bin/env python3
"""Run V15-K End-to-End Autonomy Campaign V4.

SIMULATED ONLY. No profitability calc, no Demo/exchange, no auto-integrate.

TWO PASSES by default to confirm deterministic digests + zero invariants.

Hard ban: do NOT write *_status.json. Emit final stdout summary only for the
Coordinator; campaign evidence JSON (non-status) may land under immutable
artifacts as application contracts.

Usage:
  python tools/research/e2e_autonomy_campaign_v4/run_v15_e2e_autonomy_campaign.py
  NEXUS_V15_K_E2E_CANDIDATES=48 python tools/research/e2e_autonomy_campaign_v4/run_v15_e2e_autonomy_campaign.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts/readiness/immutable/v15_e2e_autonomy_campaign_v4"

OWNED_SCAN_PATHS = (
    "backend/nexus_e2e_autonomy_v4",
    "tools/research/e2e_autonomy_campaign_v4",
    "tests/e2e_autonomy_campaign_v4",
)

SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)

BASE_HEAD = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"
BRANCH = "feature/v15-end-to-end-autonomy-campaign-v4"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: object) -> None:
    if path.name.endswith("_status.json") or path.name == "status.json":
        raise RuntimeError(f"HARD BAN: status JSON forbidden: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(ROOT),
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def run_secret_scan() -> dict:
    hits: list[str] = []
    files_scanned = 0
    for rel in OWNED_SCAN_PATHS:
        path = ROOT / rel
        if path.is_dir():
            targets = sorted(
                p for p in path.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"}
            )
        elif path.is_file():
            targets = [path]
        else:
            continue
        for fp in targets:
            files_scanned += 1
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(str(fp.relative_to(ROOT)).replace("\\", "/"))
                    break
    return {
        "schema": "v15_k_e2e_autonomy_campaign_v4_secret_scan",
        "secret_leak_count": len(hits),
        "hits": hits,
        "files_scanned": files_scanned,
        "owned_paths": list(OWNED_SCAN_PATHS),
        "created_at": _utc(),
    }


def write_artifacts(
    *,
    campaign: dict,
    pass_reports: list[dict],
    secret_scan: dict,
    pytest_result: dict | None = None,
) -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def dump(name: str, obj: object) -> Path:
        if name.endswith("_status.json") or name == "status.json":
            raise RuntimeError(f"HARD BAN: status JSON forbidden: {name}")
        p = OUT / name
        _write(p, obj)
        paths[name] = p
        return p

    dump("campaign_report.json", campaign)
    dump(
        "lifecycle_counts.json",
        {
            "schema": "v15_k_e2e_autonomy_campaign_v4_lifecycle_counts",
            "candidate_count": campaign.get("candidate_count"),
            "completed_lifecycle_count": campaign.get("completed_lifecycle_count"),
            "rejected_count": campaign.get("rejected_count"),
            "blocked_count": campaign.get("blocked_count"),
            "error_count": campaign.get("error_count"),
            "targets": campaign.get("targets"),
            "created_at": _utc(),
        },
    )
    dump("invariants.json", campaign.get("invariants") or {})
    dump("fault_coverage.json", campaign.get("fault_coverage") or {})
    dump("injection_matrix.json", campaign.get("injection_matrix") or {})
    dump("focused_probes.json", campaign.get("focused_probes") or {})
    dump("universe.json", campaign.get("universe") or {})
    dump(
        "blockers.json",
        {
            "schema": "v15_k_e2e_autonomy_campaign_v4_blockers",
            "blockers": list(campaign.get("blockers") or []),
            "pass": bool(campaign.get("pass")),
            "created_at": _utc(),
        },
    )
    dump("secret_scan.json", secret_scan)
    dump(
        "two_pass.json",
        {
            "schema": "v15_k_e2e_autonomy_campaign_v4_two_pass",
            "pass_count": len(pass_reports),
            "digests": [p.get("digest") for p in pass_reports],
            "passes_match": len({p.get("digest") for p in pass_reports}) == 1
            if pass_reports
            else False,
            "all_pass": all(bool(p.get("pass")) for p in pass_reports),
            "created_at": _utc(),
        },
    )
    if pytest_result is not None:
        dump("pytest_result.json", pytest_result)

    readme = """# V15-K End-to-End Autonomy Campaign V4

SIMULATED ONLY. CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING.

Targets: candidate_count>=100000, completed_lifecycle_count>=50000

100+ fixture symbols through validated InstrumentSpec universe.
Canonical path: Candidate → Decision → Risk → Simulated Intent → Simulated Order → Fill → Position → Exit → Reflection → Lesson Gate → Closure

Fault coverage: multi-symbol/regime, provider outage, capture degradation, partial fills, cancel-replace, clock anomaly, disk pressure, ledger interrupt, snapshot corruption, checkpoint rollback, Reflection/Lesson interrupt, kill switch, restart, qualification blocks.

No profitability calculation. No exchange writes. No auto-integrate.
No *_status.json (Coordinator final message only).
"""
    readme_path = OUT / "README.md"
    readme_path.write_text(readme, encoding="utf-8")
    paths["README.md"] = readme_path
    return paths


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.nexus_e2e_autonomy_v4 import (
        FROZEN_SEED,
        TARGET_CANDIDATES,
        run_v15_e2e_autonomy_campaign,
    )

    candidate_count = int(
        os.environ.get("NEXUS_V15_K_E2E_CANDIDATES", str(TARGET_CANDIDATES))
    )
    if candidate_count < TARGET_CANDIDATES:
        print(
            json.dumps(
                {
                    "warning": "SMOKE_ONLY_REDUCED_CANDIDATES",
                    "candidate_count_requested": candidate_count,
                    "founder_floor": TARGET_CANDIDATES,
                    "note": "Reduced runs cannot emit lane PASS; unset NEXUS_V15_K_E2E_CANDIDATES for full scale.",
                },
                indent=2,
                sort_keys=True,
            )
        )
    seed = int(os.environ.get("NEXUS_V15_K_E2E_SEED", str(FROZEN_SEED)))
    passes = int(os.environ.get("NEXUS_V15_K_E2E_PASSES", "2"))
    session_cands = int(os.environ.get("NEXUS_V15_K_FAULT_SESSION_CANDIDATES", "64"))
    keep = os.environ.get("NEXUS_V15_K_E2E_KEEP_ROOT", "0") == "1"
    runtime_root = Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME"))
    work_root = runtime_root / "v15_k_e2e_autonomy_work"
    lock_path = runtime_root / "v15_k_e2e_campaign.lock"
    if lock_path.exists():
        try:
            old_pid = int((lock_path.read_text(encoding="utf-8") or "0").strip().split()[0])
        except Exception:  # noqa: BLE001
            old_pid = 0
        still_alive = False
        if old_pid > 0 and old_pid != os.getpid():
            try:
                import ctypes

                handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, old_pid)
                if handle:
                    still_alive = True
                    ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:  # noqa: BLE001
                still_alive = False
        if still_alive:
            print(
                json.dumps(
                    {"error": "another_v15k_campaign_running", "existing_pid": old_pid},
                    indent=2,
                ),
                flush=True,
            )
            return 4
    lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    try:
        return _execute_passes(
            candidate_count=candidate_count,
            seed=seed,
            passes=passes,
            session_cands=session_cands,
            keep=keep,
            work_root=work_root,
            run_v15_e2e_autonomy_campaign=run_v15_e2e_autonomy_campaign,
            target_candidates=TARGET_CANDIDATES,
        )
    finally:
        try:
            if lock_path.exists() and lock_path.read_text(encoding="utf-8").strip().startswith(
                str(os.getpid())
            ):
                lock_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def _execute_passes(
    *,
    candidate_count: int,
    seed: int,
    passes: int,
    session_cands: int,
    keep: bool,
    work_root: Path,
    run_v15_e2e_autonomy_campaign,
    target_candidates: int,
) -> int:
    pass_reports: list[dict] = []
    for pidx in range(1, max(1, passes) + 1):
        root = work_root / f"pass{pidx}" if keep else None
        if root is not None:
            root.mkdir(parents=True, exist_ok=True)
        report = run_v15_e2e_autonomy_campaign(
            root=root,
            candidate_count=candidate_count,
            seed=seed,
            keep_root=keep,
            session_candidate_count=session_cands,
        )
        # Belt-and-suspenders: never promote below-floor counts to PASS in artifacts.
        if int(report.get("candidate_count") or 0) < target_candidates or int(
            report.get("completed_lifecycle_count") or 0
        ) < 50_000:
            report = dict(report)
            report["pass"] = False
            if report.get("status") == "NEXUS_V15_K_E2E_AUTONOMY_CAMPAIGN_V4_PASS":
                report["status"] = (
                    "NEXUS_V15_K_E2E_AUTONOMY_CAMPAIGN_V4_SMOKE_ONLY:runner_floor_guard"
                )
            blockers = list(report.get("blockers") or [])
            if not any("smoke_only_below_founder_targets" in b for b in blockers):
                blockers.append(
                    "smoke_only_below_founder_targets:runner_floor_guard"
                )
            report["blockers"] = blockers
        pass_reports.append(report)
        print(
            json.dumps(
                {
                    "pass_index": pidx,
                    "status": report["status"],
                    "pass": report["pass"],
                    "smoke_only": report.get("smoke_only"),
                    "candidate_count": report["candidate_count"],
                    "completed_lifecycle_count": report["completed_lifecycle_count"],
                    "digest": report["digest"],
                    "blockers": report["blockers"],
                },
                indent=2,
                sort_keys=True,
            )
        )

    campaign = pass_reports[-1]
    if len(pass_reports) >= 2:
        digests = {p["digest"] for p in pass_reports}
        if len(digests) != 1:
            campaign = dict(campaign)
            campaign["blockers"] = list(campaign.get("blockers") or []) + [
                f"two_pass_digest_mismatch:{sorted(digests)}"
            ]
            campaign["pass"] = False
            campaign["status"] = (
                "NEXUS_V15_K_E2E_AUTONOMY_CAMPAIGN_V4_INVALID:two_pass_digest_mismatch"
            )

    secret_scan = run_secret_scan()
    if secret_scan["secret_leak_count"] > 0:
        campaign = dict(campaign)
        campaign["blockers"] = list(campaign.get("blockers") or []) + ["secret_leak"]
        campaign["pass"] = False
        campaign["status"] = "NEXUS_V15_K_E2E_AUTONOMY_CAMPAIGN_V4_INVALID:secret_leak"

    paths = write_artifacts(
        campaign=campaign,
        pass_reports=pass_reports,
        secret_scan=secret_scan,
    )
    summary = {
        "lane": "V15-K",
        "lane_name": "E2E_AUTONOMY_CAMPAIGN_V4",
        "branch": BRANCH,
        "base_head": BASE_HEAD,
        "head_commit": _git_head(),
        "status": campaign["status"],
        "pass": campaign["pass"],
        "candidate_count": campaign["candidate_count"],
        "completed_lifecycle_count": campaign["completed_lifecycle_count"],
        "exchange_write_attempt_count": campaign["exchange_write_attempt_count"],
        "invariants": campaign["invariants"],
        "fault_coverage": campaign["fault_coverage"],
        "blockers": campaign["blockers"],
        "digests": [p.get("digest") for p in pass_reports],
        "two_pass_match": len({p.get("digest") for p in pass_reports}) == 1,
        "secret_leak_count": secret_scan.get("secret_leak_count", 0),
        "profitability_measured": False,
        "auto_integrate": False,
        "status_json_written": False,
        "artifacts": {k: str(v) for k, v in paths.items()},
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    # Completion sentinel for detached/long runs (not a status JSON).
    try:
        done_path = Path(os.environ.get("NEXUS_V15_K_E2E_DONE_PATH", str(OUT / "run_complete.json")))
        if not str(done_path.name).endswith("_status.json") and done_path.name != "status.json":
            _write(
                done_path,
                {
                    "schema": "v15_k_e2e_autonomy_campaign_v4_run_complete",
                    "pass": bool(campaign.get("pass")),
                    "status": campaign.get("status"),
                    "candidate_count": campaign.get("candidate_count"),
                    "completed_lifecycle_count": campaign.get("completed_lifecycle_count"),
                    "exit_code": 0 if campaign.get("pass") else 2,
                    "created_at": _utc(),
                },
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[v15k-e2e] done_sentinel_failed:{type(exc).__name__}:{exc}", flush=True)
    return 0 if campaign["pass"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — ensure detached runs leave a crash marker
        import traceback

        crash = {
            "schema": "v15_k_e2e_autonomy_campaign_v4_crash",
            "error": f"{type(exc).__name__}:{exc}",
            "traceback": traceback.format_exc(),
            "created_at": _utc(),
        }
        try:
            crash_path = ROOT / "artifacts/readiness/immutable/v15_e2e_autonomy_campaign_v4/run_crash.json"
            crash_path.parent.mkdir(parents=True, exist_ok=True)
            crash_path.write_text(json.dumps(crash, indent=2) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        print(json.dumps(crash, indent=2), flush=True)
        raise
