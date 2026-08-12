"""Checkpoint safety — validate incomplete SoT checkpoint posture without resume ownership."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_provider_ops.constants import (
    SCHEMA_CHECKPOINT,
    SOT_GROQ_PENDING,
    SOT_GROQ_SUCCESS,
    SOT_SAMBANOVA_PENDING,
    SOT_SAMBANOVA_SUCCESS,
    SOT_TERMINAL_STATUS,
)
from backend.nexus_provider_ops.sot import assert_incomplete_truth, incomplete_sot_snapshot


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evaluate_checkpoint_safety(
    *,
    checkpoint: dict[str, Any] | None = None,
    checkpoint_path: Path | None = None,
    require_incomplete_sot: bool = True,
) -> dict[str, Any]:
    """Assess checkpoint safety for incomplete SoT; never executes real resume."""
    sot = incomplete_sot_snapshot()
    issues: list[str] = []
    source = "synthetic_incomplete_sot"
    raw: dict[str, Any] | None = checkpoint
    checksum: str | None = None

    if checkpoint_path is not None and checkpoint_path.is_file():
        text = checkpoint_path.read_text(encoding="utf-8")
        checksum = _sha_bytes(text.encode("utf-8"))
        try:
            raw = json.loads(text)
            source = "file"
        except json.JSONDecodeError:
            issues.append("checkpoint_json_invalid")
            raw = None
            source = "file_invalid"

    if raw is None:
        # Safe default: operate against known incomplete SoT truth (no file required).
        raw = {
            "stage": "PROVIDER_CAPACITY_BLOCKED",
            "exit_reason": "PROVIDER_RATE_LIMITED",
            "completed_case_ids": [f"case_{i:03d}" for i in range(SOT_GROQ_SUCCESS)],
            "pending_case_ids": [f"case_{i:03d}" for i in range(SOT_GROQ_SUCCESS, SOT_GROQ_SUCCESS + SOT_GROQ_PENDING)],
            "pending_critic_case_ids": [
                f"case_{i:03d}" for i in range(SOT_SAMBANOVA_SUCCESS, SOT_SAMBANOVA_SUCCESS + SOT_SAMBANOVA_PENDING)
            ],
            "transport": {
                "GROQ_REFLECTION_REASONER": {
                    "success_count": SOT_GROQ_SUCCESS,
                    "retry_after": 900,
                    "last_exit_reason": "PROVIDER_RATE_LIMITED",
                },
                "SAMBANOVA_INDEPENDENT_CRITIC": {
                    "success_count": SOT_SAMBANOVA_SUCCESS,
                    "retry_after": 900,
                    "last_exit_reason": "PROVIDER_RATE_LIMITED",
                },
            },
        }
        if source == "synthetic_incomplete_sot":
            checksum = _sha_bytes(json.dumps(raw, sort_keys=True).encode("utf-8"))

    completed = list(raw.get("completed_case_ids") or [])
    pending = list(raw.get("pending_case_ids") or [])
    critic_pending = list(
        raw.get("pending_critic_case_ids") or raw.get("critic_pending_ids") or []
    )
    completed_set = set(completed)
    pending_set = set(pending)

    if completed_set & pending_set:
        issues.append("completed_pending_overlap")
    if len(completed) != len(completed_set):
        issues.append("completed_case_duplicates")
    if len(pending) != len(pending_set):
        issues.append("pending_case_duplicates")

    groq_slot = (raw.get("transport") or {}).get("GROQ_REFLECTION_REASONER") or {}
    sn_slot = (raw.get("transport") or {}).get("SAMBANOVA_INDEPENDENT_CRITIC") or {}
    g_success = int(groq_slot.get("success_count") or len(completed))
    s_success = int(sn_slot.get("success_count") or 0)

    if require_incomplete_sot:
        if g_success >= 80 and len(critic_pending) == 0 and s_success >= g_success:
            issues.append("unexpected_complete_checkpoint_while_sot_incomplete")
        # Align with known SoT when using synthetic defaults
        if source == "synthetic_incomplete_sot":
            if g_success != SOT_GROQ_SUCCESS or len(pending) != SOT_GROQ_PENDING:
                issues.append("synthetic_sot_misaligned")
            if s_success != SOT_SAMBANOVA_SUCCESS or len(critic_pending) != SOT_SAMBANOVA_PENDING:
                issues.append("synthetic_critic_sot_misaligned")

    integrity = "OK" if not issues else "UNSAFE"
    report = {
        "schema": SCHEMA_CHECKPOINT,
        "created_at": _utc(),
        "source": source,
        "checkpoint_path": str(checkpoint_path) if checkpoint_path else None,
        "checksum_sha256": checksum,
        "integrity_status": integrity,
        "issues": issues,
        "completed_case_count": len(completed_set),
        "pending_case_count": len(pending_set),
        "critic_pending_count": len(set(critic_pending)),
        "groq_success_count": g_success,
        "sambanova_success_count": s_success,
        "V2_3_complete": False,
        "V2_3_terminal_status": SOT_TERMINAL_STATUS,
        "safe_to_observe": integrity == "OK",
        "safe_for_ops_control": integrity == "OK",
        "real_resume_executed": False,
        "ops_mutated_checkpoint": False,
        "sot": {
            "groq_success": sot["lanes"]["GROQ_REFLECTION_REASONER"]["success_count"],
            "groq_pending": sot["lanes"]["GROQ_REFLECTION_REASONER"]["pending_count"],
            "sambanova_success": sot["lanes"]["SAMBANOVA_INDEPENDENT_CRITIC"]["success_count"],
            "sambanova_pending": sot["lanes"]["SAMBANOVA_INDEPENDENT_CRITIC"]["pending_count"],
        },
    }
    assert_incomplete_truth(report)
    return report
