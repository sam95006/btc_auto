#!/usr/bin/env python3
"""Ensure dedicated P2 migration 0007 Zeabur service exists; print service_id only."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tools.ci.p2_migration_service_identity import (
    MIGRATION_SERVICE_NAME,
    assert_distinct_migration_service,
    safe_service_id_prefix,
)

ROOT = Path(__file__).resolve().parents[2]
BASE_SCRIPT = ROOT / "tools" / "ci" / "ensure_demo_validation_zeabur_service.py"


def _forbidden_ids() -> set[str]:
    forbidden = {
        item.strip()
        for item in os.environ.get("FORBIDDEN_SERVICE_IDS", "").split(",")
        if item.strip()
    }
    learning_validation_id = (
        os.environ.get("LEARNING_VALIDATION_SERVICE_ID")
        or os.environ.get("ZEABUR_DEMO_VALIDATION_SERVICE_ID")
        or ""
    ).strip()
    if learning_validation_id:
        forbidden.add(learning_validation_id)
    preset = os.environ.get("PRESET_SERVICE_ID", "").strip()
    if preset:
        forbidden.add(preset)
    return forbidden


def main() -> int:
    if not os.environ.get("ZEABUR_TOKEN") or not os.environ.get("ZEABUR_PROJECT_ID"):
        print("missing_ZEABUR_TOKEN_or_PROJECT_ID", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env["SERVICE_NAME"] = MIGRATION_SERVICE_NAME
    env.pop("PRESET_SERVICE_ID", None)
    forbidden = _forbidden_ids()
    if forbidden:
        env["FORBIDDEN_SERVICE_IDS"] = ",".join(sorted(forbidden))
    proc = subprocess.run(
        [sys.executable, str(BASE_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        timeout=900,
    )
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        return proc.returncode
    service_id = (proc.stdout or "").strip()
    if not service_id:
        print("BLOCKER_migration_service_id_unresolved", file=sys.stderr)
        return 1
    learning_validation_id = (
        env.get("LEARNING_VALIDATION_SERVICE_ID")
        or env.get("ZEABUR_DEMO_VALIDATION_SERVICE_ID")
        or ""
    ).strip()
    try:
        identity = assert_distinct_migration_service(
            service_id,
            learning_validation_service_id=learning_validation_id,
            forbidden_service_ids=forbidden,
        )
    except ValueError as exc:
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 3
    print(
        f"migration_service_resolved=true id_prefix={identity['migration_service_id_prefix']}",
        file=sys.stderr,
    )
    print(
        f"learning_validation_not_reused=true id_prefix={identity['learning_validation_service_id_prefix']}",
        file=sys.stderr,
    )
    print(service_id, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
