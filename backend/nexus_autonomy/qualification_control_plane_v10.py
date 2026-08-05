"""NEXUS_QUALIFICATION_CONTROL_PLANE_V10

Blocked-only control infrastructure for future qualification stages:

  Candidate Freeze → Replay → Walk-forward → Risk Review →
  OOS reservation → Demo eligibility

EVERY stage defaults to BLOCKED.
Founder_authorization_present = false
formal_walk_forward_executed = false
oos_reservation_created = false
oos_executed = false
strategy_selected = false
strategy_promoted = false
demo_order_count = 0

Does NOT execute any qualification stage. Does NOT consume September reserved OOS.
Does NOT place Demo / Shadow / exchange orders. Does NOT select or promote a strategy.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.qualification_blocked_stages_v10 import (
    BLOCKED_QUALIFICATION_STAGES_V10,
    STAGE_STATUS_BLOCKED,
    BlockedStageControllerV10,
    blocked_stage_matrix_document,
)

SCHEMA_ID = "NEXUS_QUALIFICATION_CONTROL_PLANE_V10"
QUALIFICATION_STATUS_BLOCKED = "BLOCKED"
CONTROL_PLANE_STATUS = "BLOCKED_READY"
ARTIFACT_REL = Path("artifacts/readiness/immutable/v10_qualification_control_plane")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_control_flags() -> dict[str, Any]:
    """Canonical false/zero control flags — never flipped by V10 dry-run."""
    return {
        "Founder_authorization_present": False,
        "founder_authorization_present": False,
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "strategy_selected": False,
        "strategy_promoted": False,
        "demo_order_count": 0,
        "demo_eligibility": False,
        "exchange_write_attempt_count": 0,
        "september_reserved_oos_consumed": False,
    }


class QualificationControlPlaneV10:
    """Blocked-only qualification control plane."""

    def __init__(self) -> None:
        self.schema = SCHEMA_ID
        self.qualification_status = QUALIFICATION_STATUS_BLOCKED
        self.control_plane_status = CONTROL_PLANE_STATUS
        self.stage_controller = BlockedStageControllerV10()
        self.flags = default_control_flags()
        self.proofs: dict[str, Any] = {}
        self.created_at = _utc()

    def bootstrap_blocked(self) -> dict[str, Any]:
        """Wire control plane; attempt every stage; all remain BLOCKED."""
        advance_results = self.stage_controller.attempt_all_stages()

        # Explicitly reaffirm hard bans after refusal attempts.
        self.flags = default_control_flags()
        self.qualification_status = QUALIFICATION_STATUS_BLOCKED
        self.control_plane_status = CONTROL_PLANE_STATUS

        self.proofs = {
            "stage_execute_attempts": advance_results,
            "all_attempts_refused": all(
                (not r.get("allowed")) and (not r.get("executed"))
                for r in advance_results.values()
            ),
            "all_stages_blocked_after_attempts": self.stage_controller.all_blocked(),
            "founder_authorization_present": False,
            "september_reserved_oos_consumed": False,
        }
        return self.summary()

    def summary(self) -> dict[str, Any]:
        stages = dict(self.stage_controller.stages)
        flags = deepcopy(self.flags)
        return {
            "schema": self.schema,
            "qualification_status": self.qualification_status,
            "control_plane_status": self.control_plane_status,
            "status": self.control_plane_status,
            "created_at": self.created_at,
            "updated_at": _utc(),
            "stage_order": list(BLOCKED_QUALIFICATION_STAGES_V10),
            "stages": stages,
            "all_stages_blocked": all(v == STAGE_STATUS_BLOCKED for v in stages.values()),
            "blocked_stage_controller": self.stage_controller.to_dict(),
            "proofs": deepcopy(self.proofs),
            **flags,
            "prohibitions": {
                "candidate_freeze": "BLOCKED_NOT_EXECUTED",
                "replay": "BLOCKED_NOT_EXECUTED",
                "walk_forward": "BLOCKED_NOT_EXECUTED",
                "risk_review": "BLOCKED_NOT_EXECUTED",
                "oos_reservation": "BLOCKED_NOT_CREATED",
                "oos_execution": "NOT_EXECUTED",
                "september_reserved_oos": "NOT_CONSUMED",
                "demo_eligibility": "BLOCKED_NOT_GRANTED",
                "demo_shadow_exchange_writes": "NOT_ATTEMPTED",
                "strategy_selection": "NOT_PERFORMED",
                "strategy_promotion": "BLOCKED",
                "merge_deploy": "NOT_PERFORMED",
            },
        }


def run_qualification_control_plane_dry_run() -> dict[str, Any]:
    plane = QualificationControlPlaneV10()
    return plane.bootstrap_blocked()


def write_immutable_artifacts(
    summary: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Path]:
    """Write immutable readiness JSON under owned artifact path."""
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    status_path = out_dir / "qualification_control_plane_status.json"
    stages_path = out_dir / "qualification_blocked_stage_matrix.json"
    flags_path = out_dir / "qualification_control_flags.json"
    proofs_path = out_dir / "qualification_block_proofs.json"
    summary_path = out_dir / "qualification_control_plane_summary.json"

    status_doc = {
        "schema": SCHEMA_ID,
        "qualification_status": summary.get("qualification_status"),
        "control_plane_status": summary.get("control_plane_status"),
        "all_stages_blocked": summary.get("all_stages_blocked"),
        "Founder_authorization_present": False,
        "founder_authorization_present": False,
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "strategy_selected": False,
        "strategy_promoted": False,
        "demo_order_count": 0,
        "demo_eligibility": False,
        "exchange_write_attempt_count": 0,
        "september_reserved_oos_consumed": False,
        "prohibitions": summary.get("prohibitions"),
        "created_at": summary.get("created_at"),
        "updated_at": summary.get("updated_at"),
    }
    stages_doc = blocked_stage_matrix_document()
    # Prefer live controller stages if present.
    if summary.get("stages"):
        stages_doc["stages"] = dict(summary["stages"])
        stages_doc["all_stages_blocked"] = all(
            v == STAGE_STATUS_BLOCKED for v in stages_doc["stages"].values()
        )
    flags_doc = {
        "schema": SCHEMA_ID,
        **default_control_flags(),
    }
    proofs_doc = {
        "schema": SCHEMA_ID,
        "proofs": summary.get("proofs") or {},
        "blocked_stage_controller": summary.get("blocked_stage_controller") or {},
    }

    def _dump(path: Path, doc: Any) -> None:
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _dump(status_path, status_doc)
    _dump(stages_path, stages_doc)
    _dump(flags_path, flags_doc)
    _dump(proofs_path, proofs_doc)
    _dump(summary_path, summary)

    return {
        "status": status_path,
        "stages": stages_path,
        "flags": flags_path,
        "proofs": proofs_path,
        "summary": summary_path,
    }


def main() -> int:
    summary = run_qualification_control_plane_dry_run()
    paths = write_immutable_artifacts(summary)
    print(
        json.dumps(
            {
                "qualification_status": summary["qualification_status"],
                "control_plane_status": summary["control_plane_status"],
                "all_stages_blocked": summary["all_stages_blocked"],
                "artifacts": {k: str(v) for k, v in paths.items()},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
