#!/usr/bin/env python3
"""Founder V11 Lane E — Reflection V2.3 adjudication runner.

Fixture results are controls, not real trading learning. Real checkpoint progress
is reported separately from the read-only source or worktree-local copy.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IMMUTABLE = ROOT / "artifacts/readiness/immutable/v11_reflection_v23_adjudication"
WORKTREE_RUNTIME = ROOT / ".nexus_runtime"
CHECKPOINT_NAME = "blind_reflection_v23_checkpoint.json"
REAL_CHECKPOINT = Path(r"D:\NEXUS\btc_bot\.nexus_runtime\blind_reflection_v23_checkpoint.json")


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


def _read_checkpoint_progress(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "checkpoint_available": False,
            "checkpoint_path": str(path),
            "progress_source": "CHECKPOINT_FILE",
            "rebuilt_from_summary_metrics": False,
        }
    try:
        state = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {
            "checkpoint_available": True,
            "checkpoint_path": str(path),
            "progress_source": "CHECKPOINT_FILE",
            "checkpoint_read_status": f"ERROR:{type(exc).__name__}",
            "rebuilt_from_summary_metrics": False,
        }
    transport = state.get("transport") or {}
    groq = transport.get("GROQ_REFLECTION_REASONER") or {}
    sn = transport.get("SAMBANOVA_INDEPENDENT_CRITIC") or {}
    return {
        "checkpoint_available": True,
        "checkpoint_path": str(path),
        "progress_source": "CHECKPOINT_FILE",
        "checkpoint_read_status": "OK",
        "rebuilt_from_summary_metrics": False,
        "schema": state.get("schema"),
        "schema_version": state.get("schema_version"),
        "case_id_count": len(state.get("case_ids") or []),
        "completed_case_count": len(state.get("completed_case_ids") or []),
        "pending_case_count": len(state.get("pending_case_ids") or []),
        "critic_case_count": len(state.get("critic_case_ids") or []),
        "critic_pending_count": len(state.get("critic_pending_ids") or state.get("pending_critic_case_ids") or []),
        "critic_resolved_count": len(state.get("critic_resolved_ids") or []),
        "groq_success_count": int(groq.get("success_count") or 0),
        "groq_429_count": int(groq.get("HTTP_429_count") or 0),
        "groq_next_resume_not_before": groq.get("next_resume_not_before"),
        "sambanova_success_count": int(sn.get("success_count") or 0),
        "sambanova_429_count": int(sn.get("HTTP_429_count") or 0),
        "sambanova_next_resume_not_before": sn.get("next_resume_not_before"),
    }


def _maybe_copy_checkpoint() -> dict[str, Any]:
    dest = WORKTREE_RUNTIME / CHECKPOINT_NAME
    if os.getenv("NEXUS_V11_COPY_REAL_CHECKPOINT", "0") != "1":
        return {
            "copy_executed": False,
            "reason": "READ_ONLY_REFERENCE_MODE",
            "worktree_checkpoint_path": str(dest),
        }
    if not REAL_CHECKPOINT.is_file():
        return {
            "copy_executed": False,
            "reason": "SOURCE_CHECKPOINT_MISSING",
            "source_checkpoint_path": str(REAL_CHECKPOINT),
            "worktree_checkpoint_path": str(dest),
        }
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_CHECKPOINT, dest)
    return {
        "copy_executed": True,
        "reason": "COPIED_TO_WORKTREE_LOCAL_RUNTIME",
        "source_checkpoint_path": str(REAL_CHECKPOINT),
        "worktree_checkpoint_path": str(dest),
    }


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    os.environ["NEXUS_AI_MOCK"] = "1"

    from backend.nexus_reflection.adjudication_v11 import (
        CONTROL_FIXTURE_LABEL,
        build_fixture_adjudication_result,
    )
    from backend.nexus_reflection.lesson_gate_v11 import apply_lesson_gate_v11

    IMMUTABLE.mkdir(parents=True, exist_ok=True)
    copy_result = _maybe_copy_checkpoint()
    real_progress = _read_checkpoint_progress(
        Path(copy_result["worktree_checkpoint_path"])
        if copy_result.get("copy_executed")
        else REAL_CHECKPOINT
    )
    fixture = build_fixture_adjudication_result()
    lesson = apply_lesson_gate_v11(
        terminal_status=fixture["V2_3_TERMINAL_STATUS"],
        quality_gates_passed=fixture["quality_gates_passed"],
        proposed_policy_effect_lesson_count=1,
        fixture_label=CONTROL_FIXTURE_LABEL,
    )
    summary = {
        "schema": "v11_reflection_v23_adjudication_summary",
        "created_at": _utc(),
        "git_head_at_run": _git_head(),
        "branch": "feature/v11-reflection-v23-adjudication",
        "fixture_result_label": CONTROL_FIXTURE_LABEL,
        "fixture_only": True,
        "real_ai_quality_claimed": False,
        "real_checkpoint_progress": real_progress,
        "checkpoint_copy": copy_result,
        "fixture_quality_gates_evaluated": fixture["quality_gates_evaluated"],
        "fixture_quality_gates_passed": fixture["quality_gates_passed"],
        "fixture_terminal_denominator_validation": fixture["terminal_denominator_validation"],
        "fixture_disagreement_count": len(fixture["disagreement_taxonomy"]),
        "new_policy_effect_lesson_count": lesson["new_policy_effect_lesson_count"],
        "policy_effect_lesson_allowed": lesson["policy_effect_lesson_allowed"],
        "rebuilt_from_summary_metrics": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
    }
    _write(IMMUTABLE / "v11_reflection_v23_adjudication_fixture_result.json", fixture)
    _write(IMMUTABLE / "v11_reflection_v23_adjudication_lesson_gate.json", lesson)
    _write(IMMUTABLE / "v11_reflection_v23_adjudication_summary.json", summary)
    print(json.dumps(summary, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
