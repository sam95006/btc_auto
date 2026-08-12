#!/usr/bin/env python3
"""Founder V15-F Formal Walk-Forward Plan Compiler harness.

Compiles formal WF plans (windows/embargo/purge/freezes/thresholds) but
NEVER executes them.

Status: PLAN_READY_EXECUTION_BLOCKED
formal_walk_forward_executed=false always

TWO PASSES. No *_status.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")
os.environ.setdefault("FORMAL_WALK_FORWARD", "false")
os.environ.setdefault("FORMAL_WALK_FORWARD_EXECUTE", "false")
os.environ.setdefault("OOS_EXECUTE", "false")
os.environ.setdefault("OOS_CONSUME", "false")
os.environ.setdefault("DEMO_ORDERS", "false")
os.environ.setdefault("SHADOW_ORDERS", "false")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_formal_wf_plan.campaign import run_campaign_and_write  # noqa: E402
from backend.nexus_formal_wf_plan.constants import (  # noqa: E402
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PLAN_STATUS_READY_EXECUTION_BLOCKED,
    SCHEMA_ID,
)

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)gsk_[A-Za-z0-9]{20,}"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def scan_secrets() -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_PATHS:
        target = ROOT / rel
        if target.is_dir():
            files = [
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in {".py", ".json", ".md"}
            ]
        elif target.is_file():
            files = [target]
        else:
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v15_f_formal_wf_plan_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": list(OWNED_PATHS),
    }


def assert_no_status_json(artifact_dir: Path) -> None:
    bad = list(artifact_dir.glob("*_status.json"))
    if bad:
        raise SystemExit(f"STATUS_JSON_FORBIDDEN:{[p.name for p in bad]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V15-F Formal WF Plan Compiler")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    result = run_campaign_and_write(root=args.root, lane_head=_git_head())
    secrets = scan_secrets()
    secret_path = args.root / ARTIFACT_REL / "secret_scan.json"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(
        json.dumps(secrets, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert_no_status_json(args.root / ARTIFACT_REL)

    two = result["two_pass"]
    ok = bool(
        result["status"] == PLAN_STATUS_READY_EXECUTION_BLOCKED
        and result["formal_walk_forward_executed"] is False
        and result["both_passes_ok"]
        and secrets["secret_leak_count"] == 0
    )

    payload = {
        "schema": SCHEMA_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "lane_head": _git_head(),
        "status": PLAN_STATUS_READY_EXECUTION_BLOCKED,
        "formal_walk_forward_executed": False,
        "both_passes_ok": result["both_passes_ok"],
        "plan_count": two.get("plan_count"),
        "secret_leak_count": secrets["secret_leak_count"],
        "artifacts": result["artifacts"],
        "hard_bans": list(HARD_BANS),
        "ok": ok,
        "created_at": _utc(),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
