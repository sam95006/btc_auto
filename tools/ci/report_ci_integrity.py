#!/usr/bin/env python3
"""CI integrity truth reporter — records what CI actually executed locally/CI."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str], *, cwd: Path | None = None) -> dict:
    p = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True)
    return {
        "cmd": cmd,
        "returncode": p.returncode,
        "stdout_tail": (p.stdout or "")[-2000:],
        "stderr_tail": (p.stderr or "")[-2000:],
        "ok": p.returncode == 0,
    }


def main() -> int:
    out: dict = {
        "schema": "ci_integrity_truth",
        "created_at": _utc(),
        "CI_python_full_suite_executed": False,
        "CI_python_full_suite_status": "NOT_RUN",
        "CI_frontend_typecheck_executed": False,
        "CI_frontend_typecheck_status": "NOT_RUN",
        "CI_frontend_build_executed": False,
        "CI_frontend_build_status": "NOT_RUN",
        "runtime_startup_status": "NOT_RUN",
        "health_status": "NOT_RUN",
        "route_contract_difference_count": None,
        "schema_contract_difference_count": None,
        "cli_contract_difference_count": None,
        "secret_leak_count": None,
    }
    # Secret scan (lightweight)
    import re

    bad = []
    for p in ROOT.rglob("*"):
        if p.suffix.lower() not in {".py", ".md", ".json", ".yml", ".ts", ".tsx"}:
            continue
        if "node_modules" in p.parts or ".git" in p.parts:
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if re.search(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY", t):
            bad.append(str(p.relative_to(ROOT)))
    out["secret_leak_count"] = len(bad)
    out["secret_leak_paths"] = bad

    if os.getenv("NEXUS_CI_RUN_PYTHON", "1") == "1":
        r = _run([sys.executable, "-m", "pytest", "tests", "-q", "--tb=line"])
        out["CI_python_full_suite_executed"] = True
        out["CI_python_full_suite_status"] = "PASS" if r["ok"] else "FAIL"
        out["python_detail"] = r

    fe = ROOT / "frontend"
    if fe.is_dir() and os.getenv("NEXUS_CI_RUN_FRONTEND", "1") == "1":
        tc = _run(["npx", "tsc", "-b", "--pretty", "false"], cwd=fe)
        out["CI_frontend_typecheck_executed"] = True
        out["CI_frontend_typecheck_status"] = "PASS" if tc["ok"] else "FAIL"
        out["frontend_typecheck_detail"] = tc
        bd = _run(["npm", "run", "build"], cwd=fe)
        out["CI_frontend_build_executed"] = True
        out["CI_frontend_build_status"] = "PASS" if bd["ok"] else "FAIL"
        out["frontend_build_detail"] = bd

    dest = ROOT / "artifacts/readiness/immutable/ci_integrity_v1"
    if os.getenv("NEXUS_CI_WRITE_PACKAGE", "0") == "1":
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "ci_integrity_status.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("secret_leak_count", 1) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
