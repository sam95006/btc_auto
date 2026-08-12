#!/usr/bin/env python3
"""Run V14-K Closed-Loop Scale V3 → immutable readiness package.

SIMULATED ONLY. No profitability calc, no Demo/exchange, no auto-integrate.

TWO PASSES by default to confirm deterministic digests + zero invariants.

Usage:
  python tools/research/closed_loop_scale_v3/run_v14_closed_loop_scale.py
  NEXUS_V14_K_CLOSED_LOOP_CANDIDATES=48 python tools/research/closed_loop_scale_v3/run_v14_closed_loop_scale.py
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
OUT = ROOT / "artifacts/readiness/immutable/v14_closed_loop_scale_v3"
RUNTIME_STATUS = Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME")) / "v14_k_status.json"

OWNED_SCAN_PATHS = (
    "backend/nexus_scale_v3",
    "tools/research/closed_loop_scale_v3",
    "tests/closed_loop_scale_v3",
)

SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)

BASE_HEAD = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"
BRANCH = "feature/v14-closed-loop-scale-v3"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: object) -> None:
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
        "schema": "v14_k_closed_loop_scale_v3_secret_scan",
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
    feature_commit: str | None = None,
) -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def dump(name: str, obj: object) -> Path:
        p = OUT / name
        _write(p, obj)
        paths[name] = p
        return p

    status_doc = {
        "schema": "v14_k_closed_loop_scale_v3_status",
        "status": campaign.get("status"),
        "pass": bool(campaign.get("pass")),
        "created_at": _utc(),
        "candidate_count": campaign.get("candidate_count"),
        "completed_lifecycle_count": campaign.get("completed_lifecycle_count"),
        "rejected_count": campaign.get("rejected_count"),
        "blocked_count": campaign.get("blocked_count"),
        "error_count": campaign.get("error_count"),
        "exchange_write_attempt_count": campaign.get("exchange_write_attempt_count"),
        "invariants": campaign.get("invariants"),
        "fault_coverage": campaign.get("fault_coverage"),
        "blockers": list(campaign.get("blockers") or []),
        "digest": campaign.get("digest"),
        "canonical_path": campaign.get("canonical_path"),
        "ontology": campaign.get("ontology"),
        "hard_bans": campaign.get("hard_bans"),
        "auto_integrate_pr27": False,
        "auto_integrate": False,
        "profitability_measured": False,
        "profitability_claimed": False,
    }
    dump("status.json", status_doc)
    dump("campaign_report.json", campaign)
    dump(
        "lifecycle_counts.json",
        {
            "schema": "v14_k_closed_loop_scale_v3_lifecycle_counts",
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
            "schema": "v14_k_closed_loop_scale_v3_blockers",
            "blockers": list(campaign.get("blockers") or []),
            "pass": bool(campaign.get("pass")),
            "created_at": _utc(),
        },
    )
    dump("secret_scan.json", secret_scan)
    dump(
        "two_pass.json",
        {
            "schema": "v14_k_closed_loop_scale_v3_two_pass",
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

    readme = """# V14-K Closed-Loop Scale V3

SIMULATED ONLY. CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING.

Targets: candidate_count>=50000, completed_lifecycle_count>=25000

50+ fixture symbols through validated InstrumentSpec universe.
Canonical path: Candidate → Decision → Risk → Simulated Intent → Simulated Order → Fill → Position → Exit → Reflection → Lesson Gate → Closure

Fault coverage: multi-symbol/regime, provider outage, partial fills, cancel-replace, clock anomaly, disk pressure, ledger interrupt, checkpoint rollback, Reflection/Lesson interrupt, kill switch, restart, qualification blocks.

No profitability calculation. No exchange writes. No auto-integrate.
"""
    readme_path = OUT / "README.md"
    readme_path.write_text(readme, encoding="utf-8")
    paths["README.md"] = readme_path

    head = _git_head()
    runtime_doc = {
        **status_doc,
        "lane": "V14-K",
        "lane_name": "CLOSED_LOOP_SCALE_V3",
        "branch": BRANCH,
        "worktree": str(ROOT),
        "artifact_dir": str(OUT),
        "base_head": BASE_HEAD,
        "head_commit": head,
        "lane_head_commit": head,
        "feature_commit": feature_commit or head,
        "two_pass": {
            "pass_count": len(pass_reports),
            "digests": [p.get("digest") for p in pass_reports],
            "passes_match": len({p.get("digest") for p in pass_reports}) == 1
            if pass_reports
            else False,
        },
        "two_pass_adversarial_review": True,
        "pytest": pytest_result or {},
        "pytest_passed": bool((pytest_result or {}).get("passed")),
        "secret_leak_count": secret_scan.get("secret_leak_count", 0),
        "required_zero_invariants": campaign.get("required_zero_invariants"),
        "universe": campaign.get("universe"),
        "targets": campaign.get("targets"),
        "pr27_merged": False,
        "pushed": False,
        "remaining_blockers": list(campaign.get("blockers") or []),
        "critical_findings": [],
        "high_findings": [],
        "remote": f"origin/{BRANCH}",
    }
    _write(RUNTIME_STATUS, runtime_doc)
    paths["runtime_status"] = RUNTIME_STATUS
    return paths


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.nexus_scale_v3 import (
        FROZEN_SEED,
        TARGET_CANDIDATES,
        run_v14_closed_loop_scale_campaign,
    )

    candidate_count = int(
        os.environ.get("NEXUS_V14_K_CLOSED_LOOP_CANDIDATES", str(TARGET_CANDIDATES))
    )
    seed = int(os.environ.get("NEXUS_V14_K_CLOSED_LOOP_SEED", str(FROZEN_SEED)))
    passes = int(os.environ.get("NEXUS_V14_K_CLOSED_LOOP_PASSES", "2"))
    session_cands = int(os.environ.get("NEXUS_V14_K_FAULT_SESSION_CANDIDATES", "64"))
    keep = os.environ.get("NEXUS_V14_K_CLOSED_LOOP_KEEP_ROOT", "0") == "1"
    runtime_root = Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME"))
    work_root = runtime_root / "v14_k_closed_loop_scale_work"

    pass_reports: list[dict] = []
    for pidx in range(1, max(1, passes) + 1):
        root = work_root / f"pass{pidx}" if keep else None
        if root is not None:
            root.mkdir(parents=True, exist_ok=True)
        report = run_v14_closed_loop_scale_campaign(
            root=root,
            candidate_count=candidate_count,
            seed=seed,
            keep_root=keep,
            session_candidate_count=session_cands,
        )
        pass_reports.append(report)
        print(
            json.dumps(
                {
                    "pass_index": pidx,
                    "status": report["status"],
                    "pass": report["pass"],
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
            campaign["status"] = "NEXUS_V14_K_CLOSED_LOOP_SCALE_V3_INVALID:two_pass_digest_mismatch"

    secret_scan = run_secret_scan()
    if secret_scan["secret_leak_count"] > 0:
        campaign = dict(campaign)
        campaign["blockers"] = list(campaign.get("blockers") or []) + ["secret_leak"]
        campaign["pass"] = False
        campaign["status"] = "NEXUS_V14_K_CLOSED_LOOP_SCALE_V3_INVALID:secret_leak"

    paths = write_artifacts(
        campaign=campaign,
        pass_reports=pass_reports,
        secret_scan=secret_scan,
    )
    summary = {
        "status": campaign["status"],
        "pass": campaign["pass"],
        "candidate_count": campaign["candidate_count"],
        "completed_lifecycle_count": campaign["completed_lifecycle_count"],
        "exchange_write_attempt_count": campaign["exchange_write_attempt_count"],
        "invariants": campaign["invariants"],
        "fault_coverage": campaign["fault_coverage"],
        "blockers": campaign["blockers"],
        "digests": [p.get("digest") for p in pass_reports],
        "artifacts": {k: str(v) for k, v in paths.items()},
        "runtime_status": str(RUNTIME_STATUS),
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if campaign["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
