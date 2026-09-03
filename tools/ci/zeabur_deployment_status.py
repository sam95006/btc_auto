#!/usr/bin/env python3
"""Normalized status of a specific Zeabur deployment id from a
`zeabur deployment list --json` output file.

Uses the SAME strict, schema-explicit deployment-record container as the release
resolver (``zeabur_deployment_resolve._records_container``) and the proven field
helpers (``_dep_id`` / ``_dep_status``), so status is read from the SAME exact
record the id-resolver selected — never arbitrary JSON. Prints one token:

    RUNNING   -> healthy / activated terminal state
    FAILED    -> failed / error / cancelled terminal state
    PENDING   -> still building / queued / deploying (non-terminal)
    UNKNOWN   -> id not found, unrecognized container, or status not recognised

Never raises; the workflow's bounded loop owns the fail-closed timeout decision.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zeabur_deployment_resolve import _records_container  # noqa: E402
from zeabur_readonly_diagnostic import _dep_id, _dep_status  # noqa: E402

_RUNNING = {"RUNNING", "SUCCESS", "SUCCEEDED", "HEALTHY", "ACTIVE", "DEPLOYED", "READY", "LIVE"}
_FAILED = {"FAILED", "FAILURE", "ERROR", "ERRORED", "CANCELLED", "CANCELED", "CRASHED", "ABORTED"}
_PENDING = {"PENDING", "QUEUED", "BUILDING", "DEPLOYING", "CREATED", "CREATING", "INITIALIZING",
            "IN_PROGRESS", "PROGRESS", "STARTING", "UPLOADING", "WAITING"}


def _normalize(raw: str) -> str:
    token = (raw or "").strip().upper()
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
    container = _records_container(parsed)
    if container is None:
        print("UNKNOWN"); return 0
    for rec in container:
        if _dep_id(rec).lower() == target_id:
            print(_normalize(_dep_status(rec)))
            return 0
    print("UNKNOWN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
