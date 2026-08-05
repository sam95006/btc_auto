#!/usr/bin/env python3
"""Founder V15-G OOS Reservation and Seal Control harness.

Builds interval planning + cryptographic lineage seal control plane.
Does NOT execute real OOS reservation/download/execution/consumption.

TWO PASSES. Writes immutable evidence artifacts (no *_status.json).
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
os.environ.setdefault("OOS_EXECUTE", "false")
os.environ.setdefault("OOS_CONSUME", "false")

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_oos_seal_control.constants import (  # noqa: E402
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    FORBIDDEN_STATUS_BASENAMES,
    FORBIDDEN_STATUS_JSON_SUFFIX,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    SCHEMA_ID,
)
from backend.nexus_oos_seal_control.controller import (  # noqa: E402
    run_two_pass,
    write_immutable_artifacts,
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
        if not target.exists():
            continue
        files = (
            [
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in {".py", ".json", ".md"}
            ]
            if target.is_dir()
            else [target]
        )
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append({"path": str(path.relative_to(ROOT)).replace("\\", "/"), "pattern": pat.pattern})
    return {"ok": len(hits) == 0, "hit_count": len(hits), "hits": hits}


def assert_no_status_json() -> dict[str, Any]:
    out_dir = ROOT / ARTIFACT_REL
    offenders: list[str] = []
    if out_dir.exists():
        for path in out_dir.rglob("*.json"):
            name = path.name.lower()
            if name in FORBIDDEN_STATUS_BASENAMES or name.endswith(FORBIDDEN_STATUS_JSON_SUFFIX):
                offenders.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return {"ok": len(offenders) == 0, "offenders": offenders}


def main() -> int:
    parser = argparse.ArgumentParser(description="V15-G OOS Reservation Seal Control")
    parser.add_argument("--as-of-ms", type=int, default=1_700_000_000_000)
    args = parser.parse_args()

    two_pass = run_two_pass(as_of_ms=args.as_of_ms, root=ROOT)
    paths = write_immutable_artifacts(two_pass, root=ROOT)
    secrets = scan_secrets()
    no_status = assert_no_status_json()

    result = {
        "schema": SCHEMA_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "git_head": _git_head(),
        "generated_at": _utc(),
        "both_passes_ok": two_pass.get("both_passes_ok"),
        "oos_reserved": False,
        "oos_downloaded": False,
        "oos_executed": False,
        "oos_consumed": False,
        "hard_bans": list(HARD_BANS),
        "artifact_paths": {k: str(v.relative_to(ROOT)).replace("\\", "/") for k, v in paths.items()},
        "secret_scan": secrets,
        "no_status_json": no_status,
        "ok": bool(
            two_pass.get("both_passes_ok") and secrets["ok"] and no_status["ok"]
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
