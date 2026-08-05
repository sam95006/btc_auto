#!/usr/bin/env python3
"""
PUB2-J three-pass runner: a11y / i18n / performance hard bans + parity.

Prints results to stdout. Does NOT write *_status.json or report files.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.nexus_public_a11y_i18n_perf.hard_bans import run_three_passes  # noqa: E402
from backend.nexus_public_a11y_i18n_perf.i18n_parity import check_catalog_parity  # noqa: E402


def _run(cmd: list[str], cwd: Path) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
        "ok": proc.returncode == 0,
    }


def main() -> int:
    print("=== PUB2-J PASS 1-3 hard bans ===")
    bans = run_three_passes()
    print(json.dumps({"hard_bans": bans}, indent=2))
    if not bans["ok"]:
        return 1

    print("=== i18n catalog parity ===")
    parity = check_catalog_parity()
    print(json.dumps(parity, indent=2))
    if not parity["ok"]:
        return 1

    frontend = REPO / "frontend"
    results = []
    for pass_id in (1, 2, 3):
        print(f"=== frontend check_a11y_i18n_perf pass {pass_id} ===")
        r = _run(["node", "scripts/check_a11y_i18n_perf.mjs", str(pass_id)], frontend)
        results.append(r)
        print(r["stdout_tail"] or r["stderr_tail"])
        if not r["ok"]:
            return 1

    print("PUB2-J THREE PASSES: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
