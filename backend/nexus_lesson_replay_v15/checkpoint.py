"""Read-only V2.3 checkpoint inspection — never mutates canonical SoT."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_lesson_replay_v15.constants import (
    CANONICAL_CHECKPOINT_PATH,
    SOT_CASE_COUNT,
    SOT_GROQ_PENDING,
    SOT_GROQ_SUCCESS,
    SOT_SAMBANOVA_PENDING,
    SOT_SAMBANOVA_SUCCESS,
    SOT_STAGE,
    SOT_TERMINAL_STATUS,
    SOT_V2_3_COMPLETE,
)


def load_checkpoint_readonly(path: str | Path | None = None) -> dict[str, Any]:
    """Load canonical checkpoint as read-only snapshot. Never writes."""
    p = Path(path or CANONICAL_CHECKPOINT_PATH)
    if not p.is_file():
        return {
            "checkpoint_found": False,
            "checkpoint_path": str(p),
            "read_only": True,
            "mutated": False,
            "V2_3_complete": False,
            "V2_3_terminal_status": "CHECKPOINT_MISSING",
            "stage": "MISSING",
            "error": "canonical_checkpoint_not_found",
        }
    data = json.loads(p.read_text(encoding="utf-8"))
    transport = data.get("transport") or {}
    groq = transport.get("GROQ_REFLECTION_REASONER") or {}
    samba = transport.get("SAMBANOVA_INDEPENDENT_CRITIC") or {}
    groq_success = int(groq.get("success_count") or 0)
    samba_success = int(samba.get("success_count") or 0)
    case_ids = list(data.get("case_ids") or [])
    completed = list(data.get("completed_case_ids") or [])
    pending = list(data.get("pending_case_ids") or [])
    stage = str(data.get("stage") or "")
    complete = stage == "VERIFIED" and len(pending) == 0 and groq_success >= SOT_CASE_COUNT
    return {
        "checkpoint_found": True,
        "checkpoint_path": str(p),
        "read_only": True,
        "mutated": False,
        "schema": data.get("schema"),
        "stage": stage,
        "groq_stage": data.get("groq_stage"),
        "sambanova_stage": data.get("sambanova_stage"),
        "case_count": len(case_ids),
        "completed_case_count": len(completed),
        "pending_case_count": len(pending),
        "groq_success_count": groq_success,
        "groq_pending_estimate": max(0, SOT_CASE_COUNT - groq_success) if not complete else 0,
        "sambanova_success_count": samba_success,
        "sambanova_pending_estimate": max(0, len(data.get("pending_critic_case_ids") or [])),
        "V2_3_complete": False if not complete else True,
        "V2_3_terminal_status": "VERIFIED" if complete else SOT_TERMINAL_STATUS,
        "integrity_checksum": data.get("integrity_checksum"),
        "trust": "canonical_checkpoint_counters_over_summaries",
        "expected_incomplete_sot": {
            "groq_success": SOT_GROQ_SUCCESS,
            "groq_pending": SOT_GROQ_PENDING,
            "sambanova_success": SOT_SAMBANOVA_SUCCESS,
            "sambanova_pending": SOT_SAMBANOVA_PENDING,
            "stage": SOT_STAGE,
            "V2_3_complete": SOT_V2_3_COMPLETE,
        },
    }
