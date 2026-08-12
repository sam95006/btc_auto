#!/usr/bin/env python3
"""Run V12-A Founder-private closed-loop proof → immutable readiness package.

SIMULATED ONLY. No exchange writes, no Demo/Shadow/mainnet, no formal WF/OOS,
no profitability claims, no auto-integrate into PR27.

Usage:
  python tools/research/run_v12_closed_loop.py
  NEXUS_V12_CLOSED_LOOP_CANDIDATES=50 python tools/research/run_v12_closed_loop.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/readiness/immutable/v12_closed_loop"
RUNTIME_STATUS = Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME")) / "v12_a_closed_loop_status.json"

OWNED_SCAN_PATHS = (
    "backend/nexus_system/closed_loop_v12",
    "tools/research/run_v12_closed_loop.py",
    "tests/test_v12_closed_loop.py",
)

SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
        "schema": "v12_closed_loop_secret_scan",
        "secret_leak_count": len(hits),
        "hits": hits,
        "files_scanned": files_scanned,
        "owned_paths": list(OWNED_SCAN_PATHS),
        "created_at": _utc(),
    }


def write_artifacts(*, campaign: dict, secret_scan: dict) -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def dump(name: str, obj: object) -> Path:
        p = OUT / name
        _write(p, obj)
        paths[name] = p
        return p

    status_doc = {
        "schema": "v12_closed_loop_status",
        "status": campaign.get("status"),
        "pass": bool(campaign.get("pass")),
        "created_at": _utc(),
        "candidate_count": campaign.get("candidate_count"),
        "completed_lifecycle_count": campaign.get("completed_lifecycle_count"),
        "rejected_count": campaign.get("rejected_count"),
        "blocked_count": campaign.get("blocked_count"),
        "error_count": campaign.get("error_count"),
        "exchange_write_attempt_count": campaign.get("exchange_write_attempt_count"),
        "blockers": list(campaign.get("blockers") or []),
        "digest": campaign.get("digest"),
        "canonical_path": campaign.get("canonical_path"),
        "ontology": campaign.get("ontology"),
        "hard_bans": campaign.get("hard_bans"),
        "auto_integrate_pr27": False,
        "profitability_claimed": False,
    }
    dump("status.json", status_doc)
    dump("campaign_report.json", campaign)
    dump(
        "lifecycle_counts.json",
        {
            "schema": "v12_closed_loop_lifecycle_counts",
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
    dump(
        "blockers.json",
        {
            "schema": "v12_closed_loop_blockers",
            "blockers": list(campaign.get("blockers") or []),
            "pass": bool(campaign.get("pass")),
            "created_at": _utc(),
        },
    )
    dump("lesson_gate_summary.json", campaign.get("lesson_gate_summary") or {})
    dump("secret_scan.json", secret_scan)
    readme = """# V12-A Founder-private closed-loop proof

SIMULATED ONLY. CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING.

Canonical path: Candidate → Decision → Risk → Simulated Intent → Simulated Order → Fill → Position → Exit → Reflection → Lesson Gate → Closure

Ontology: MONITORING → EXITED → UNDER_REVIEW → CALIBRATED → CLOSED

No exchange writes. No profitability claims. No PR27 auto-integrate.
"""
    readme_path = OUT / "README.md"
    readme_path.write_text(readme, encoding="utf-8")
    paths["README.md"] = readme_path

    runtime_doc = {
        **status_doc,
        "lane": "V12-A",
        "branch": "feature/v12-founder-private-closed-loop",
        "worktree": str(ROOT),
        "artifact_dir": str(OUT),
        "base_head": "e4e96299840da2e5152cf2850135cebc67d66cd0",
    }
    _write(RUNTIME_STATUS, runtime_doc)
    paths["runtime_status"] = RUNTIME_STATUS
    return paths


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.nexus_system.closed_loop_v12 import (
        FROZEN_SEED,
        TARGET_CANDIDATES,
        run_v12_closed_loop_campaign,
    )

    candidate_count = int(os.environ.get("NEXUS_V12_CLOSED_LOOP_CANDIDATES", str(TARGET_CANDIDATES)))
    seed = int(os.environ.get("NEXUS_V12_CLOSED_LOOP_SEED", str(FROZEN_SEED)))
    keep = os.environ.get("NEXUS_V12_CLOSED_LOOP_KEEP_ROOT", "0") == "1"
    runtime_root = Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME"))
    work_root = runtime_root / "v12_a_closed_loop_work"
    if keep:
        work_root.mkdir(parents=True, exist_ok=True)

    campaign = run_v12_closed_loop_campaign(
        root=work_root if keep else None,
        candidate_count=candidate_count,
        seed=seed,
        keep_root=keep,
    )
    secret_scan = run_secret_scan()
    if secret_scan["secret_leak_count"] > 0:
        campaign["blockers"] = list(campaign.get("blockers") or []) + ["secret_leak"]
        campaign["pass"] = False
        campaign["status"] = f"NEXUS_V12_CLOSED_LOOP_INVALID:secret_leak"

    paths = write_artifacts(campaign=campaign, secret_scan=secret_scan)
    summary = {
        "status": campaign["status"],
        "pass": campaign["pass"],
        "candidate_count": campaign["candidate_count"],
        "completed_lifecycle_count": campaign["completed_lifecycle_count"],
        "exchange_write_attempt_count": campaign["exchange_write_attempt_count"],
        "blockers": campaign["blockers"],
        "artifacts": {k: str(v) for k, v in paths.items()},
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if campaign["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
