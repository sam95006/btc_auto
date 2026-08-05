#!/usr/bin/env python3
"""Run Founder-private Reflection V2.3 Completion Ops V13-B.

Emits artifacts under:
  artifacts/readiness/immutable/v13_reflection_v23_completion_ops/

Also writes lane status to:
  D:\\NEXUS_RUNTIME\\v13_b_reflection_completion_status.json

Hard bans: no real resume ownership theft, no secret logging, no policy-effect
Lessons while incomplete, no quality eval before complete denominators,
no Demo/exchange, no PR27 merge, do not claim V2.3 complete.
Background Agent uses sanitized fixtures only.
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

from backend.nexus_v23_completion_ops import (  # noqa: E402
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    V23CompletionOpsV13,
)
from backend.nexus_v23_completion_ops.constants import (  # noqa: E402
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    OWNED_PATHS,
    PROHIBITED_PATHS_UNTOUCHED,
    RUNTIME_STATUS_PATH,
    SCHEMA_SECRET_SCAN,
    SCHEMA_STATUS,
)
from backend.nexus_v23_completion_ops.sanitize import (  # noqa: E402
    assert_no_secret_keys,
    secret_patterns,
)

RUNTIME_STATUS = Path(RUNTIME_STATUS_PATH)


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


def write_artifacts(
    out_dir: Path,
    cycle: dict[str, Any],
    status: dict[str, Any],
    secret: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "completion_ops_status.json": status,
        "ops_cycle.json": cycle,
        "incomplete_sot.json": cycle.get("incomplete_sot"),
        "provider_preflight.json": cycle.get("provider_preflight"),
        "queue_health.json": cycle.get("queue_health"),
        "retry_quota_obs.json": cycle.get("retry_quota_obs"),
        "provider_windows.json": cycle.get("provider_windows"),
        "capacity_status.json": cycle.get("capacity_status"),
        "atomic_checkpoint.json": cycle.get("atomic_checkpoint"),
        "semantic_counters.json": cycle.get("semantic_counters"),
        "completed_case_dedupe.json": cycle.get("completed_case_dedupe"),
        "critic_ordering.json": cycle.get("critic_ordering"),
        "terminal_denominator_validation.json": cycle.get("terminal_denominator_validation"),
        "lesson_quality_gates.json": cycle.get("lesson_quality_gates"),
        "safe_pause_resume.json": cycle.get("safe_pause_resume"),
        "resume_boundary.json": cycle.get("resume_boundary"),
        "secret_scan.json": secret,
        "summary.json": {
            "schema": f"{SCHEMA_STATUS}_summary",
            "created_at": _utc(),
            "lane": LANE,
            "lane_name": LANE_NAME,
            "status": status.get("status"),
            "pass": status.get("pass"),
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
    pass_number: int,
) -> dict[str, Any]:
    return {
        "schema": "v13_b_reflection_completion_status",
        "created_at": _utc(),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "worktree": str(ROOT),
        "base_commit": BASE_COMMIT,
        "commit": commit,
        "pass": pass_number,
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
        "auto_integrate": False,
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
    parser.add_argument("--artifact-dir", default=str(ROOT / ARTIFACT_REL))
    parser.add_argument("--runtime-status", default=str(RUNTIME_STATUS))
    parser.add_argument("--pass", dest="pass_number", type=int, default=1)
    parser.add_argument(
        "--no-verify-checkpoint",
        action="store_true",
        help="Skip live checkpoint counter verification (tests/CI without local SoT).",
    )
    args = parser.parse_args(argv)

    ops = V23CompletionOpsV13(root=ROOT)
    cycle = ops.run_cycle(
        demonstrate_manual_controls=True,
        verify_checkpoint=not args.no_verify_checkpoint,
    )
    secret = scan_secrets(ROOT)
    status = ops.status_from_cycle(cycle, secret_leak_count=int(secret.get("secret_leak_count") or 0))
    status["pass"] = int(args.pass_number)

    out_dir = Path(args.artifact_dir)
    write_artifacts(out_dir, cycle, status, secret)

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
        pass_number=int(args.pass_number),
    )
    _write(Path(args.runtime_status), runtime)
    _write(out_dir / "runtime_status_mirror.json", runtime)

    print(
        json.dumps(
            {
                "status": status.get("status"),
                "pass": args.pass_number,
                "runtime_status": str(args.runtime_status),
                "V2_3_complete": False,
            },
            indent=2,
        )
    )
    return 0 if status.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
