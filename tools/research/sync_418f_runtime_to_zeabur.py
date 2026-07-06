#!/usr/bin/env python3
"""One-off helper: sync 418F Stage4 research files into Zeabur container via chunked base64."""
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

SERVICE_ID = "6a3b81652fdef84a45a2a553"
ENV_ID = "69d559b6474db8a99d6dd6bf"
CHUNK = 2800

ROOT = Path(__file__).resolve().parents[2]
SYNC_ROOT = ROOT / "deploy" / "zeabur_stage3_demo_learning"

FILES = [
    "tools/research/check_stage4_runtime_version.py",
    "tools/research/stage4_prompt_builder.py",
    "tools/research/stage4_paper_readiness.py",
    "tools/research/stage4_paper_event_logger.py",
    "tools/research/stage4_paper_guard_inputs.py",
    "tools/research/stage4_mae_calibration_analysis.py",
    "tools/research/stage4_mae_regression_compare.py",
    "tools/research/validate_stage4_ai_decision_outputs.py",
    "tools/research/run_stage4_ai_decision_dry_run.py",
    "tools/research/stage4_decision_schema.py",
    "tools/research/stage4_ai_decision_agent.py",
    "tools/research/stage4_schema_repair.py",
    "tools/research/stage4_watchlist_followup_simulator.py",
    "tools/research/stage4_paper_entry_failure_analyzer.py",
]


def zeabur_exec(shell_cmd: str) -> subprocess.CompletedProcess[str]:
    escaped = shell_cmd.replace('"', '\\"')
    cmd = (
        f'npx zeabur@latest -i=false service exec '
        f'--id {SERVICE_ID} --env-id {ENV_ID} -- sh -lc "{escaped}"'
    )
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def upload_file(rel: str) -> None:
    deploy_local = SYNC_ROOT / rel
    repo_local = ROOT / rel
    local = repo_local if repo_local.is_file() else deploy_local
    if not local.is_file():
        raise FileNotFoundError(local)
    remote = f"/app/{rel}"
    remote_b64 = f"/tmp/sync_{rel.replace('/', '_')}.b64"
    b64 = base64.b64encode(local.read_bytes()).decode("ascii")

    zeabur_exec(f"rm -f {remote_b64} {remote}")
    for i in range(0, len(b64), CHUNK):
        part = b64[i : i + CHUNK]
        esc = part.replace("'", "'\"'\"'")
        r = zeabur_exec(f"printf '%s' '{esc}' >> {remote_b64}")
        if r.returncode != 0:
            raise RuntimeError(f"chunk append failed for {rel}: {r.stderr or r.stdout}")

    r = zeabur_exec(f"base64 -d {remote_b64} > {remote} && rm -f {remote_b64} && wc -c {remote}")
    if r.returncode != 0:
        raise RuntimeError(f"decode failed for {rel}: {r.stderr or r.stdout}")
    print(f"synced {rel}: {r.stdout.strip()}")


def main() -> int:
    for rel in FILES:
        upload_file(rel)
    r = zeabur_exec(
        "mkdir -p /data/stage4_418f_runtime_patch && "
        "cp -f /app/tools/research/check_stage4_runtime_version.py "
        "/app/tools/research/stage4_prompt_builder.py "
        "/app/tools/research/stage4_paper_readiness.py "
        "/app/tools/research/stage4_paper_event_logger.py "
        "/app/tools/research/stage4_paper_guard_inputs.py "
        "/app/tools/research/stage4_mae_calibration_analysis.py "
        "/app/tools/research/stage4_mae_regression_compare.py "
        "/app/tools/research/validate_stage4_ai_decision_outputs.py "
        "/app/tools/research/run_stage4_ai_decision_dry_run.py "
        "/app/tools/research/stage4_decision_schema.py "
        "/app/tools/research/stage4_ai_decision_agent.py "
        "/app/tools/research/stage4_schema_repair.py "
        "/app/tools/research/stage4_watchlist_followup_simulator.py "
        "/data/stage4_418f_runtime_patch/ && "
        "ls /data/stage4_418f_runtime_patch/ | wc -l"
    )
    if r.returncode != 0:
        raise RuntimeError(f"patch dir copy failed: {r.stderr or r.stdout}")
    print(r.stdout.strip())
    print("all_files_synced=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
