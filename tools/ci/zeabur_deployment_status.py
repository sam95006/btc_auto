#!/usr/bin/env python3
"""Normalized status of a specific Zeabur deployment id from a
`zeabur deployment list --json` output file.

Uses the repo's proven structural deployment-record parser
(``zeabur_readonly_diagnostic._deployment_records`` + ``_dep_id`` + ``_dep_status``)
so status is read from the SAME exact deployment record that the id-resolver
selected — not from arbitrary JSON. Prints exactly one token:

    RUNNING   -> healthy / activated terminal state
    FAILED    -> failed / error / cancelled terminal state
    PENDING   -> still building / queued / deploying (non-terminal)
    UNKNOWN   -> deployment id not found, or status not parseable / recognised

Never raises for a missing/garbled file — prints UNKNOWN and returns 0 so the
workflow's own bounded loop owns the fail-closed timeout decision.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zeabur_readonly_diagnostic import _deployment_records, _dep_id, _dep_status  # noqa: E402

_RUNNING = {"RUNNING", "SUCCESS", "SUCCEEDED", "HEALTHY", "ACTIVE", "DEPLOYED", "READY", "LIVE"}
_FAILED = {"FAILED", "FAILURE", "ERROR", "ERRORED", "CANCELLED", "CANCELED", "CRASHED", "ABORTED"}
_PENDING = {"PENDING", "QUEUED", "BUILDING", "DEPLOYING", "CREATED", "CREATING", "INITIALIZING",
            "IN_PROGRESS", "PROGRESS", "STARTING", "UPLOADING", "WAITING", "RUNNING_BUILD"}


def _normalize(raw: str) -> str:
    token = (raw or "").strip().upper()
    if not token:
        return "UNKNOWN"
    if token in _RUNNING:
        return "RUNNING"
    if token in _FAILED:
        return "FAILED"
    if token in _PENDING:
        return "PENDING"
    return "UNKNOWN"


def main() -> int:
    if len(sys.argv) != 3:
        print("UNKNOWN"); return 0
    path, target_id = sys.argv[1], (sys.argv[2] or "").strip().lower()
    if not target_id:
        print("UNKNOWN"); return 0
    try:
        parsed = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        print("UNKNOWN"); return 0
    for rec in _deployment_records(parsed):
        if isinstance(rec, dict) and _dep_id(rec).lower() == target_id:
            print(_normalize(_dep_status(rec)))
            return 0
    print("UNKNOWN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
