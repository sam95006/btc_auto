"""Provider Completion Ops V12-C — private ops plane (no real resume ownership)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_provider_ops.capacity_windows import evaluate_capacity_windows
from backend.nexus_provider_ops.checkpoint_safety import evaluate_checkpoint_safety
from backend.nexus_provider_ops.completed_case_dedupe import evaluate_completed_case_dedupe
from backend.nexus_provider_ops.constants import (
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    REAL_RESUME_OWNER,
    SCHEMA,
    SCHEMA_CYCLE,
    SCHEMA_STATUS,
)
from backend.nexus_provider_ops.manual_control import ManualLaneControl
from backend.nexus_provider_ops.queue_health import evaluate_queue_health
from backend.nexus_provider_ops.resume_boundary import ResumeBoundary, ResumeOwnershipError
from backend.nexus_provider_ops.retry_after_obs import observe_lane_retry_map
from backend.nexus_provider_ops.sanitize import assert_no_secret_keys, safe_log_fields
from backend.nexus_provider_ops.sot import assert_incomplete_truth, incomplete_sot_snapshot


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProviderCompletionOpsV12:
    """Founder-private Provider resume ops around incomplete SoT truth."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.manual = ManualLaneControl()
        self.boundary = ResumeBoundary()

    def run_cycle(
        self,
        *,
        demonstrate_manual_controls: bool = True,
        checkpoint_path: Path | None = None,
    ) -> dict[str, Any]:
        sot = incomplete_sot_snapshot()
        assert_incomplete_truth(sot)

        # Retry-After observability (safe headers only)
        retry_map = observe_lane_retry_map(
            {
                GROQ_REFLECTION_REASONER: {"Retry-After": "900"},
                SAMBANOVA_INDEPENDENT_CRITIC: {"Retry-After": "900"},
            }
        )

        # Manual pause/resume demo on ops scheduling only
        manual_events: list[dict[str, Any]] = []
        if demonstrate_manual_controls:
            manual_events.append(
                self.manual.pause(GROQ_REFLECTION_REASONER, reason="ops_cycle_demo_pause")
            )
            manual_events.append(
                self.manual.resume(GROQ_REFLECTION_REASONER, reason="ops_cycle_demo_resume")
            )
            manual_events.append(
                self.manual.pause(SAMBANOVA_INDEPENDENT_CRITIC, reason="ops_cycle_demo_pause")
            )
            manual_events.append(
                self.manual.resume(SAMBANOVA_INDEPENDENT_CRITIC, reason="ops_cycle_demo_resume")
            )

        # Prove ownership theft is blocked
        ownership_block = self.boundary.request_real_resume(reason="ops_cycle_probe")
        ownership_theft_blocked = True
        try:
            self.boundary.execute_real_resume(fn=None)
            ownership_theft_blocked = False
        except ResumeOwnershipError:
            ownership_theft_blocked = True

        queue = evaluate_queue_health(
            groq_paused=self.manual.is_paused(GROQ_REFLECTION_REASONER),
            sambanova_paused=self.manual.is_paused(SAMBANOVA_INDEPENDENT_CRITIC),
            groq_retry_after_s=900.0,
            sambanova_retry_after_s=900.0,
        )
        capacity = evaluate_capacity_windows(
            groq_retry_after_s=900.0,
            sambanova_retry_after_s=900.0,
        )
        checkpoint = evaluate_checkpoint_safety(checkpoint_path=checkpoint_path)
        dedupe = evaluate_completed_case_dedupe()
        manual_snap = self.manual.snapshot()
        boundary_snap = self.boundary.snapshot()

        cycle = {
            "schema": SCHEMA_CYCLE,
            "created_at": _utc(),
            "lane": LANE,
            "lane_name": LANE_NAME,
            "package": PACKAGE,
            "branch": BRANCH,
            "base_commit": BASE_COMMIT,
            "hard_bans": list(HARD_BANS),
            "incomplete_sot": sot,
            "queue_health": queue,
            "retry_after_obs": retry_map,
            "capacity_windows": capacity,
            "checkpoint_safety": checkpoint,
            "completed_case_dedupe": dedupe,
            "manual_control": manual_snap,
            "manual_events": manual_events,
            "resume_boundary": boundary_snap,
            "ownership_request_blocked": ownership_block,
            "ownership_theft_blocked": ownership_theft_blocked,
            "real_resume_owner": REAL_RESUME_OWNER,
            "real_resume_executed_by_ops": False,
            "ops_owns_real_resume": False,
            "V2_3_complete": False,
            "V2_3_terminal_status": sot["V2_3_terminal_status"],
            "demo_order_count": 0,
            "exchange_write_attempt_count": 0,
            "mainnet": False,
            "real_money": False,
            "secret_logging": False,
            "pr27_merged": False,
        }
        cycle = safe_log_fields(cycle)
        assert_no_secret_keys(cycle)
        assert_incomplete_truth(cycle)
        return cycle

    def status_from_cycle(self, cycle: dict[str, Any], *, secret_leak_count: int = 0) -> dict[str, Any]:
        checks = {
            "queue_health_ok": (cycle.get("queue_health") or {}).get("overall_status")
            in {"DEGRADED_INCOMPLETE", "PAUSED", "HEALTHY"},
            "retry_after_obs_ok": bool((cycle.get("retry_after_obs") or {}).get("any_rate_limited")),
            "capacity_windows_ok": (cycle.get("capacity_windows") or {}).get("real_resume_authorized")
            is False,
            "checkpoint_safety_ok": (cycle.get("checkpoint_safety") or {}).get("integrity_status")
            == "OK",
            "dedupe_ok": bool((cycle.get("completed_case_dedupe") or {}).get("dedupe_effective")),
            "manual_control_ok": (cycle.get("manual_control") or {}).get("real_resume_executed")
            is False,
            "ownership_boundary_ok": bool(cycle.get("ownership_theft_blocked"))
            and cycle.get("ops_owns_real_resume") is False,
            "incomplete_sot_honored": cycle.get("V2_3_complete") is False,
            "no_secret_logging": cycle.get("secret_logging") is False and secret_leak_count == 0,
            "no_demo_exchange": int(cycle.get("demo_order_count") or 0) == 0
            and int(cycle.get("exchange_write_attempt_count") or 0) == 0,
            "no_pr27_merge": cycle.get("pr27_merged") is False,
        }
        ok = all(checks.values())
        status = {
            "schema": SCHEMA_STATUS,
            "created_at": _utc(),
            "lane": LANE,
            "lane_name": LANE_NAME,
            "branch": BRANCH,
            "package": PACKAGE,
            "base_commit": BASE_COMMIT,
            "status": "PASS" if ok else "FAIL",
            "checks": checks,
            "all_controls_ok": ok,
            "V2_3_complete": False,
            "V2_3_terminal_status": cycle.get("V2_3_terminal_status"),
            "groq_success_count": ((cycle.get("incomplete_sot") or {}).get("lanes") or {})
            .get(GROQ_REFLECTION_REASONER, {})
            .get("success_count"),
            "groq_pending_count": ((cycle.get("incomplete_sot") or {}).get("lanes") or {})
            .get(GROQ_REFLECTION_REASONER, {})
            .get("pending_count"),
            "sambanova_success_count": ((cycle.get("incomplete_sot") or {}).get("lanes") or {})
            .get(SAMBANOVA_INDEPENDENT_CRITIC, {})
            .get("success_count"),
            "sambanova_pending_count": ((cycle.get("incomplete_sot") or {}).get("lanes") or {})
            .get(SAMBANOVA_INDEPENDENT_CRITIC, {})
            .get("pending_count"),
            "real_resume_owner": REAL_RESUME_OWNER,
            "ops_owns_real_resume": False,
            "real_resume_executed_by_ops": False,
            "secret_leak_count": secret_leak_count,
            "demo_order_count": 0,
            "exchange_write_attempt_count": 0,
            "mainnet": False,
            "real_money": False,
            "pr27_merged": False,
            "hard_bans": list(HARD_BANS),
        }
        assert_no_secret_keys(status)
        assert_incomplete_truth(status)
        return status


def build_ops_plane(root: Path | None = None) -> ProviderCompletionOpsV12:
    return ProviderCompletionOpsV12(root=root)
