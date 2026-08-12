#!/usr/bin/env python3
"""Run Founder-private Provider Completion Ops V12-C.

Emits artifacts under:
  artifacts/readiness/immutable/v12_provider_completion_ops/

Also writes lane status to:
  D:\\NEXUS_RUNTIME\\v12_c_provider_ops_status.json

Hard bans: no real resume ownership theft, no secret logging, no Demo/exchange,
no PR27 merge, do not claim V2.3 complete.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_provider_ops import (  # noqa: E402
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    ProviderCompletionOpsV12,
)
from backend.nexus_provider_ops.constants import (  # noqa: E402
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    OWNED_PATHS,
    PROHIBITED_PATHS_UNTOUCHED,
    SCHEMA_SECRET_SCAN,
    SCHEMA_STATUS,
)
from backend.nexus_provider_ops.sanitize import (  # noqa: E402
    assert_no_secret_keys,
    secret_patterns,
)

RUNTIME_STATUS = Path(r"D:\NEXUS_RUNTIME\v12_c_provider_ops_status.json")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    if isinstance(obj, dict):
        assert_no_secret_keys(obj)


def scan_secrets(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    patterns = secret_patterns()
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_dir():
            files = [
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in {".py", ".json", ".md", ".yml", ".yaml"}
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
            for pat in patterns:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": SCHEMA_SECRET_SCAN,
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": list(OWNED_PATHS),
    }


def write_artifacts(out_dir: Path, cycle: dict[str, Any], status: dict[str, Any], secret: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "provider_ops_status.json": status,
        "ops_cycle.json": cycle,
        "incomplete_sot.json": cycle.get("incomplete_sot"),
        "queue_health.json": cycle.get("queue_health"),
        "retry_after_obs.json": cycle.get("retry_after_obs"),
        "capacity_windows.json": cycle.get("capacity_windows"),
        "checkpoint_safety.json": cycle.get("checkpoint_safety"),
        "completed_case_dedupe.json": cycle.get("completed_case_dedupe"),
        "manual_control.json": cycle.get("manual_control"),
        "resume_boundary.json": cycle.get("resume_boundary"),
        "secret_scan.json": secret,
        "summary.json": {
            "schema": f"{SCHEMA_STATUS}_summary",
            "created_at": _utc(),
            "lane": LANE,
            "lane_name": LANE_NAME,
            "status": status.get("status"),
            "V2_3_complete": False,
            "V2_3_terminal_status": status.get("V2_3_terminal_status"),
            "groq_success_count": status.get("groq_success_count"),
            "groq_pending_count": status.get("groq_pending_count"),
            "sambanova_success_count": status.get("sambanova_success_count"),
            "sambanova_pending_count": status.get("sambanova_pending_count"),
            "real_resume_owner": status.get("real_resume_owner"),
            "ops_owns_real_resume": False,
            "secret_leak_count": secret.get("secret_leak_count"),
            "hard_bans": list(HARD_BANS),
        },
    }
    for name, payload in payloads.items():
        _write(out_dir / name, payload)


def build_runtime_status(
    *,
    status: dict[str, Any],
    secret: dict[str, Any],
    commit: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    return {
        "schema": "v12_c_provider_ops_status",
        "created_at": _utc(),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "worktree": str(ROOT),
        "base_commit": BASE_COMMIT,
        "commit": commit,
        "status": status.get("status"),
        "all_controls_ok": status.get("all_controls_ok"),
        "checks": status.get("checks"),
        "V2_3_complete": False,
        "V2_3_terminal_status": status.get("V2_3_terminal_status"),
        "incomplete_sot": {
            "groq_success_count": status.get("groq_success_count"),
            "groq_pending_count": status.get("groq_pending_count"),
            "sambanova_success_count": status.get("sambanova_success_count"),
            "sambanova_pending_count": status.get("sambanova_pending_count"),
        },
        "real_resume_owner": status.get("real_resume_owner"),
        "ops_owns_real_resume": False,
        "real_resume_executed_by_ops": False,
        "secret_leak_count": secret.get("secret_leak_count"),
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mainnet": False,
        "real_money": False,
        "pr27_merged": False,
        "hard_bans": list(HARD_BANS),
        "owned_paths": list(OWNED_PATHS),
        "prohibited_paths_untouched": list(PROHIBITED_PATHS_UNTOUCHED),
        "artifact_dir": str(artifact_dir).replace("\\", "/"),
    }


def main(argv: list[str] | None = None) -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        default=str(ROOT / ARTIFACT_REL),
    )
    parser.add_argument(
        "--runtime-status",
        default=str(RUNTIME_STATUS),
    )
    args = parser.parse_args(argv)

    ops = ProviderCompletionOpsV12(root=ROOT)
    cycle = ops.run_cycle(demonstrate_manual_controls=True)
    secret = scan_secrets(ROOT)
    status = ops.status_from_cycle(cycle, secret_leak_count=int(secret.get("secret_leak_count") or 0))

    out_dir = Path(args.artifact_dir)
    write_artifacts(out_dir, cycle, status, secret)

    # Commit may not exist yet when runner executes pre-commit; placeholder filled by post-commit refresh.
    try:
        import subprocess

        commit = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
        )
    except Exception:
        commit = BASE_COMMIT

    runtime = build_runtime_status(
        status=status,
        secret=secret,
        commit=commit,
        artifact_dir=out_dir,
    )
    _write(Path(args.runtime_status), runtime)
    _write(out_dir / "runtime_status_mirror.json", runtime)

    print(json.dumps({"status": status.get("status"), "runtime_status": str(args.runtime_status)}, indent=2))
    return 0 if status.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
