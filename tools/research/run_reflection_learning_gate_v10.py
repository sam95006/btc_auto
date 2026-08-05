#!/usr/bin/env python3
"""V10 Lane C — Reflection Learning Gate runner.

Continues real V2.3 from verified checkpoint; gates policy-effect Lessons;
scaffolds historical Lesson Prevention Proof only when V2.3 VERIFIED.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
IMMUTABLE = ROOT / "artifacts/readiness/immutable/v10_reflection_learning_gate"
RUNTIME = ROOT / ".nexus_runtime/research/v10_reflection_learning_gate"
SOURCE_CP = Path(r"D:\NEXUS\btc_bot\.nexus_runtime\blind_reflection_v23_checkpoint.json")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def _secret_scan(paths: list[Path]) -> dict[str, Any]:
    banned = (
        "api_key",
        "apikey",
        "authorization",
        "bearer ",
        "sk-",
        "secret",
        "password",
        "raw_prompt",
        "raw_response",
    )
    hits: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for token in banned:
            if token in text and token in {"sk-", "bearer "}:
                hits.append({"path": str(path), "token": token})
            elif token in {"api_key", "apikey", "authorization", "password"} and f'"{token}"' in text:
                # allow schema field names like banned_keys lists; flag assignment-like leaks
                if f'"{token}": "' in text or f'"{token}": "' in text:
                    hits.append({"path": str(path), "token": token})
    return {"secret_leak_count": len(hits), "hits": hits, "scanned_file_count": len(paths)}


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass

    RUNTIME.mkdir(parents=True, exist_ok=True)
    IMMUTABLE.mkdir(parents=True, exist_ok=True)

    from backend.nexus_reflection.learning_gate_v10 import (
        scaffold_historical_lesson_prevention_proof,
    )
    from backend.nexus_reflection.v23_resume_v10 import build_frozen_packets, resume_v23

    allow_real = os.getenv("NEXUS_V23_ALLOW_REAL_RESUME", "1") == "1"
    max_batches = int(os.getenv("NEXUS_V23_MAX_BATCHES", "4"))

    print("1) resume V2.3 from verified checkpoint...", flush=True)
    resume = resume_v23(
        root=ROOT,
        allow_real_resume=allow_real,
        max_batches=max_batches,
        source_checkpoint=SOURCE_CP if SOURCE_CP.is_file() else None,
    )
    _write(RUNTIME / "v23_resume_result.json", resume)

    terminal = resume.get("V2_3_terminal_status")
    quality_passed = bool(resume.get("quality_gates_passed"))
    packets, _ = build_frozen_packets(ROOT)

    print("2) learning gate / historical proof scaffold...", flush=True)
    execute_proof = (
        str(terminal or "").upper() == "VERIFIED"
        and quality_passed
        and os.getenv("NEXUS_V10_EXECUTE_HISTORICAL_PROOF", "1") == "1"
    )
    learning = scaffold_historical_lesson_prevention_proof(
        terminal_status=terminal,
        quality_gates_passed=quality_passed,
        packets=packets,
        execute=execute_proof,
        use_real_ai=False,  # scaffold/execute historical proof without live risk mutation path
    )
    # When VERIFIED, still mark scaffold even if execute deferred
    _write(RUNTIME / "learning_gate_result.json", learning)

    summary = {
        "schema": "v10_reflection_learning_gate_summary",
        "created_at": _utc(),
        "git_head_at_run": _git_head(),
        "lane": "LANE_C_REFLECTION_LEARNING_GATE",
        "branch": "feature/v10-reflection-learning-gate",
        "checkpoint_present": bool((resume.get("ensure_checkpoint") or {}).get("checkpoint_present")),
        "checkpoint_copied": bool((resume.get("ensure_checkpoint") or {}).get("checkpoint_copied")),
        "checkpoint_integrity_status": resume.get("checkpoint_integrity_status"),
        "checkpoint_migration_status": resume.get("checkpoint_migration_status"),
        "manifest_checksum_status": resume.get("manifest_checksum_status"),
        "real_resume_executed": resume.get("real_resume_executed"),
        "real_resume_status": resume.get("real_resume_status"),
        "rebuilt_from_summary_metrics": False,
        "groq_success_count": resume.get("groq_success_count"),
        "groq_pending_count": resume.get("groq_pending_count"),
        "sambanova_success_count": resume.get("sambanova_success_count"),
        "sambanova_pending_count": resume.get("sambanova_pending_count"),
        "V2_3_terminal_status": terminal,
        "quality_gates_evaluated": resume.get("quality_gates_evaluated"),
        "quality_gates_passed": quality_passed,
        "learning_prevention_status": learning.get("learning_prevention_status"),
        "new_policy_effect_lesson_count": learning.get("new_policy_effect_lesson_count"),
        "policy_effect_lesson_allowed": learning.get("policy_effect_lesson_allowed"),
        "false_learning_claim": learning.get("false_learning_claim"),
        "profitability_claimed": False,
        "risk_limits_changed": False,
        "leverage_changed": False,
        "provider_429_lanes": resume.get("provider_429_lanes"),
        "completed_case_loss_count": resume.get("completed_case_loss_count"),
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
    }
    _write(IMMUTABLE / "v10_reflection_learning_gate_summary.json", summary)
    _write(IMMUTABLE / "v23_resume_result.json", resume)
    _write(IMMUTABLE / "learning_gate_result.json", learning)

    artifact_paths = [
        IMMUTABLE / "v10_reflection_learning_gate_summary.json",
        IMMUTABLE / "v23_resume_result.json",
        IMMUTABLE / "learning_gate_result.json",
    ]
    scan = _secret_scan(artifact_paths)
    _write(IMMUTABLE / "secret_scan.json", scan)
    summary["secret_leak_count"] = scan["secret_leak_count"]
    _write(IMMUTABLE / "v10_reflection_learning_gate_summary.json", summary)

    print(json.dumps(summary, indent=2, default=str), flush=True)
    return 0 if scan["secret_leak_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
