"""Formal Walk-forward plan compiler — build plans, never execute them."""
from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_formal_wf_plan.constants import (
    HARD_BANS,
    LANE,
    PLAN_DIMENSIONS,
    PLAN_STATUS_READY_EXECUTION_BLOCKED,
    SCHEMA_ID,
    SCHEMA_VERSION,
)
from backend.nexus_formal_wf_plan.execution_gate import FormalWalkForwardExecutionGate
from backend.nexus_formal_wf_plan.fixtures import synthetic_candidate_bundle
from backend.nexus_formal_wf_plan.freezes import build_all_freeze_rules
from backend.nexus_formal_wf_plan.hard_bans import (
    assert_plan_not_executed,
    canonical_hard_ban_flags,
    env_hard_ban_guard,
)
from backend.nexus_formal_wf_plan.requirements import build_plan_requirements
from backend.nexus_formal_wf_plan.windows import build_fold_windows


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def resolve_code_version(root: Path | str | None = None) -> str:
    repo = Path(root) if root else Path(__file__).resolve().parents[2]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def compile_formal_wf_plan(
    candidate: dict[str, Any],
    *,
    code_version: str | None = None,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    """Compile one formal Walk-forward plan. Never executes folds."""
    if candidate.get("selected") or candidate.get("promoted"):
        raise ValueError("selected_or_promoted_candidate_forbidden_in_v15_f")

    interval = candidate.get("development_interval") or {}
    as_of = int(as_of_ms or 1_700_000_000_000)
    start = int(interval.get("start_ms") or (as_of - 365 * 86_400_000))
    end = int(interval.get("end_ms") or (as_of - 60 * 86_400_000))
    if interval.get("category") not in (None, "DEVELOPMENT", "VALIDATION_PLANNING"):
        raise ValueError(f"forbidden_interval_category:{interval.get('category')}")

    cv = code_version or resolve_code_version()
    windows = build_fold_windows(development_start_ms=start, development_end_ms=end)
    freezes = build_all_freeze_rules(candidate, code_version=cv)
    requirements = build_plan_requirements(candidate)

    plan_body = {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "lane": LANE,
        "plan_kind": "FORMAL_WALK_FORWARD",
        "candidate_id": candidate.get("candidate_id"),
        "discovery_label": candidate.get("discovery_label"),
        "as_of_ms": as_of,
        "created_at": _utc(),
        "status": PLAN_STATUS_READY_EXECUTION_BLOCKED,
        "executed": False,
        "formal_walk_forward_executed": False,
        "dimensions": list(PLAN_DIMENSIONS),
        "training_windows": windows["training_windows"],
        "validation_windows": windows["validation_windows"],
        "embargo": windows["embargo"],
        "purge_intervals": windows["purge_intervals"],
        "folds": windows["folds"],
        "fold_count": windows["fold_count"],
        "window_spec": {
            "training_days": windows["training_days"],
            "validation_days": windows["validation_days"],
            "step_days": windows["step_days"],
            "development_interval": windows["development_interval"],
        },
        **freezes,
        **requirements,
        "hard_bans": list(HARD_BANS),
        **canonical_hard_ban_flags(),
        "fixture_only": bool(candidate.get("fixture_only")),
        "note": (
            "Formal Walk-forward plan compiled only. "
            "Status PLAN_READY_EXECUTION_BLOCKED. "
            "formal_walk_forward_executed=false always."
        ),
    }
    plan_body["plan_id"] = f"WF_PLAN_{candidate.get('candidate_id')}_{_sha(plan_body)[:12]}"
    plan_body["plan_checksum"] = _sha(
        {k: v for k, v in plan_body.items() if k not in {"plan_checksum", "created_at"}}
    )
    assert_plan_not_executed(plan_body)
    return plan_body


def compile_formal_wf_plans(
    candidates: list[dict[str, Any]],
    *,
    code_version: str | None = None,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    cv = code_version or resolve_code_version()
    plans = [
        compile_formal_wf_plan(c, code_version=cv, as_of_ms=as_of_ms) for c in candidates
    ]
    gate = FormalWalkForwardExecutionGate()
    execute_attempts = {p["plan_id"]: gate.attempt_execute_plan(p) for p in plans}
    for p in plans:
        for fold in p.get("folds") or []:
            gate.attempt_execute_fold(p, fold["fold_id"])

    env_guard = env_hard_ban_guard()
    if not env_guard["ok"]:
        raise RuntimeError(f"env_hard_ban_violations:{env_guard['violations']}")

    report = {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "lane": LANE,
        "status": PLAN_STATUS_READY_EXECUTION_BLOCKED,
        "created_at": _utc(),
        "code_version": cv,
        "as_of_ms": as_of_ms,
        "plan_count": len(plans),
        "plans": plans,
        "plan_ids": [p["plan_id"] for p in plans],
        "dimensions_covered": list(PLAN_DIMENSIONS),
        "all_dimensions_present": all(
            all(dim in p for dim in PLAN_DIMENSIONS) for p in plans
        ),
        "all_plans_blocked": all(
            p["status"] == PLAN_STATUS_READY_EXECUTION_BLOCKED for p in plans
        ),
        "formal_walk_forward_executed": False,
        "any_plan_executed": False,
        "execute_attempts": execute_attempts,
        "execution_gate": gate.to_dict(),
        "env_hard_ban_guard": env_guard,
        "hard_bans": list(HARD_BANS),
        **canonical_hard_ban_flags(),
    }
    # Re-assert immutable ban flags after merge (caller must not mutate authority).
    report["formal_walk_forward_executed"] = False
    report["status"] = PLAN_STATUS_READY_EXECUTION_BLOCKED
    return report


class FormalWalkForwardPlanCompiler:
    """V15-F compiler facade: plans only, execution permanently blocked."""

    def __init__(self, *, code_version: str | None = None) -> None:
        self.code_version = code_version or resolve_code_version()
        self.gate = FormalWalkForwardExecutionGate()
        self.last_report: dict[str, Any] | None = None

    def compile_bundle(
        self,
        bundle: dict[str, Any] | None = None,
        *,
        as_of_ms: int | None = None,
    ) -> dict[str, Any]:
        if bundle is None:
            bundle = synthetic_candidate_bundle(as_of_ms=as_of_ms or 1_700_000_000_000)
        as_of = int(as_of_ms if as_of_ms is not None else bundle.get("as_of_ms") or 1_700_000_000_000)
        candidates = list(bundle.get("candidates") or [])
        report = compile_formal_wf_plans(
            candidates, code_version=self.code_version, as_of_ms=as_of
        )
        report["bundle_schema"] = bundle.get("schema")
        report["fixture_only"] = bool(bundle.get("fixture_only"))
        report["ingested_candidate_count"] = len(candidates)
        self.last_report = deepcopy(report)
        return report

    def attempt_execute(self, plan: dict[str, Any]) -> dict[str, Any]:
        return self.gate.attempt_execute_plan(plan)
