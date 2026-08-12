"""Campaign runner and immutable artifact writer for V15-F.

Never writes *_status.json (founder directive).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_formal_wf_plan.adversarial import run_two_pass_campaign
from backend.nexus_formal_wf_plan.constants import (
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PLAN_DIMENSIONS,
    PLAN_STATUS_READY_EXECUTION_BLOCKED,
    SCHEMA_ID,
)
from backend.nexus_formal_wf_plan.hard_bans import (
    canonical_hard_ban_flags,
    scan_owned_paths_for_banned_claims,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dump(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_immutable_artifacts(
    two_pass: dict[str, Any],
    *,
    root: Path | None = None,
    lane_head: str | None = None,
) -> dict[str, str]:
    """Write immutable readiness artifacts. No *_status.json files."""
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    # Guard: never emit *_status.json under this lane.
    for stale in out_dir.glob("*_status.json"):
        stale.unlink()

    pass1 = two_pass["pass1"]
    pass2 = two_pass["pass2"]
    claim_scan = scan_owned_paths_for_banned_claims(base)

    summary = {
        "schema": SCHEMA_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "lane_head": lane_head,
        "created_at": _utc(),
        "status": PLAN_STATUS_READY_EXECUTION_BLOCKED,
        "formal_walk_forward_executed": False,
        "both_passes_ok": two_pass.get("both_passes_ok"),
        "plan_count": two_pass.get("plan_count"),
        "dimensions": list(PLAN_DIMENSIONS),
        "hard_bans": list(HARD_BANS),
        **canonical_hard_ban_flags(),
        "banned_claim_scan_ok": claim_scan["ok"],
        "banned_claim_count": claim_scan["banned_claim_count"],
        "note": "Plans compiled only. Formal WF execution blocked. No *_status.json emitted.",
    }

    paths = {
        "summary": out_dir / "campaign_summary.json",
        "plans": out_dir / "formal_wf_plans.json",
        "pass1": out_dir / "pass1_compile_report.json",
        "pass2": out_dir / "pass2_adversarial.json",
        "two_pass": out_dir / "two_pass_report.json",
        "dimensions": out_dir / "plan_dimensions.json",
        "hard_bans": out_dir / "hard_bans.json",
        "execution_gate": out_dir / "execution_gate.json",
        "claim_scan": out_dir / "banned_claim_scan.json",
        "readme": out_dir / "README.md",
    }

    _dump(paths["summary"], summary)
    _dump(
        paths["plans"],
        {
            "schema": SCHEMA_ID,
            "status": PLAN_STATUS_READY_EXECUTION_BLOCKED,
            "formal_walk_forward_executed": False,
            "plan_count": pass1.get("plan_count"),
            "plans": pass1.get("plans"),
        },
    )
    _dump(paths["pass1"], pass1)
    _dump(paths["pass2"], pass2)
    _dump(paths["two_pass"], two_pass)
    _dump(
        paths["dimensions"],
        {
            "schema": SCHEMA_ID,
            "dimensions": list(PLAN_DIMENSIONS),
            "all_dimensions_present": pass1.get("all_dimensions_present"),
        },
    )
    _dump(
        paths["hard_bans"],
        {
            "schema": SCHEMA_ID,
            "hard_bans": list(HARD_BANS),
            "flags": canonical_hard_ban_flags(),
        },
    )
    _dump(paths["execution_gate"], pass1.get("execution_gate") or {})
    _dump(paths["claim_scan"], claim_scan)

    paths["readme"].write_text(
        "\n".join(
            [
                "# V15-F Formal Walk-Forward Plan Compiler",
                "",
                f"Status: `{PLAN_STATUS_READY_EXECUTION_BLOCKED}`",
                "",
                "`formal_walk_forward_executed=false` always.",
                "",
                "Plans are compiled only. Formal Walk-forward is never executed.",
                "",
                "No `*_status.json` artifacts are emitted by this lane.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Final guard after writes.
    status_files = list(out_dir.glob("*_status.json"))
    if status_files:
        raise RuntimeError(f"status_json_forbidden:{[p.name for p in status_files]}")

    return {k: str(v.relative_to(base)).replace("\\", "/") for k, v in paths.items()}


def run_campaign_and_write(
    *,
    root: Path | None = None,
    lane_head: str | None = None,
) -> dict[str, Any]:
    two_pass = run_two_pass_campaign()
    written = write_immutable_artifacts(two_pass, root=root, lane_head=lane_head)
    return {
        "two_pass": two_pass,
        "artifacts": written,
        "status": PLAN_STATUS_READY_EXECUTION_BLOCKED,
        "formal_walk_forward_executed": False,
        "both_passes_ok": two_pass.get("both_passes_ok"),
    }
