"""Immutable readiness artifacts for V18-F."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_shadow_decision_ledger.constants import (
    ARTIFACT_REL,
    HARD_BANS,
    LIFECYCLE_STATES,
    NON_CLAIMS,
    OWNED_PATHS,
    SCHEMA,
)


def artifact_root(repo_root: Path) -> Path:
    return repo_root / ARTIFACT_REL


def build_summary_payload(
    *,
    tip_sha: str,
    counts: dict[str, Any],
    tests: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "lane": "V18-F",
        "tip_sha": tip_sha,
        "lifecycle_states": list(LIFECYCLE_STATES),
        "hard_bans": list(HARD_BANS),
        "non_claims": list(NON_CLAIMS),
        "owned_paths": list(OWNED_PATHS),
        "counts": counts,
        "tests": tests,
        "active_lesson_count": int(counts.get("active_lesson_count", 0)),
        "actual_ordered_count": int(counts.get("actual_ordered_count", 0)),
        "actual_filled_count": int(counts.get("actual_filled_count", 0)),
        "exchange_write_attempt_count": int(counts.get("exchange_write_attempt_count", 0)),
        "shadow_opened_means": "internal_virtual_research_position_only",
        "public_invariants": {
            "actual_ordered": False,
            "actual_filled": False,
            "exchange_order_id": None,
        },
    }


def write_immutable_artifacts(repo_root: Path, payload: dict[str, Any]) -> Path:
    root = artifact_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    out = root / "summary.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "hard_bans.json").write_text(
        json.dumps({"hard_bans": list(HARD_BANS)}, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "lifecycle_states.json").write_text(
        json.dumps({"lifecycle_states": list(LIFECYCLE_STATES)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return out
