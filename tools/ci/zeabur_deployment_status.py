#!/usr/bin/env python3
"""Extract the normalized status of a specific Zeabur deployment id from a
`zeabur deployment list --json` output file.

Used by the api-staging release workflow to gate HTTP verification on the NEW
deployment actually reaching a terminal activated state (rather than blindly
sleeping). Prints exactly one normalized token to stdout:

    RUNNING   -> healthy / activated terminal state
    FAILED    -> failed / error / cancelled terminal state
    PENDING   -> still building / queued / deploying (non-terminal)
    UNKNOWN   -> deployment id not found or status not parseable

Never raises for a missing/garbled file — prints UNKNOWN and returns 0 so the
workflow's own bounded loop owns the fail-closed timeout decision.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RUNNING = {"RUNNING", "SUCCESS", "SUCCEEDED", "HEALTHY", "ACTIVE", "DEPLOYED", "READY", "LIVE"}
_FAILED = {"FAILED", "FAILURE", "ERROR", "ERRORED", "CANCELLED", "CANCELED", "CRASHED", "ABORTED"}
_PENDING = {"PENDING", "QUEUED", "BUILDING", "DEPLOYING", "CREATED", "CREATING", "INITIALIZING",
            "IN_PROGRESS", "PROGRESS", "STARTING", "UPLOADING", "WAITING"}

_STATUS_KEYS = ("status", "state", "phase", "deploymentStatus", "deployment_status")
_ID_KEYS = ("id", "deploymentID", "deploymentId", "_id")


def _find_deployment(node, target_id: str):
    if isinstance(node, dict):
        for key in _ID_KEYS:
            val = node.get(key)
            if isinstance(val, str) and val == target_id:
                return node
        for item in node.values():
            found = _find_deployment(item, target_id)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_deployment(item, target_id)
            if found is not None:
                return found
    return None


def _status_of(deployment: dict) -> str:
    for key in _STATUS_KEYS:
        raw = deployment.get(key)
        if isinstance(raw, str) and raw.strip():
            token = raw.strip().upper()
            if token in _RUNNING:
                return "RUNNING"
            if token in _FAILED:
                return "FAILED"
            if token in _PENDING:
                return "PENDING"
            return "UNKNOWN"
    return "UNKNOWN"


def main() -> int:
    if len(sys.argv) != 3:
        print("UNKNOWN")
        return 0
    path, target_id = sys.argv[1], (sys.argv[2] or "").strip()
    if not target_id:
        print("UNKNOWN")
        return 0
    try:
        parsed = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        print("UNKNOWN")
        return 0
    deployment = _find_deployment(parsed, target_id)
    print(_status_of(deployment) if isinstance(deployment, dict) else "UNKNOWN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
