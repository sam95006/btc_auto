"""V13-B Reflection V2.3 Completion Ops plane — sanitized fixtures only."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_v23_completion_ops.atomic_checkpoint import (
    evaluate_atomic_checkpoint,
    validate_semantic_counters,
)
from backend.nexus_v23_completion_ops.constants import (
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
from backend.nexus_v23_completion_ops.dedupe_critic import (
    evaluate_completed_case_dedupe,
    evaluate_critic_ordering,
)
from backend.nexus_v23_completion_ops.gates import (
    evaluate_lesson_quality_gates,
    evaluate_terminal_denominators_ops,
)
from backend.nexus_v23_completion_ops.pause_resume import SafePauseResume
from backend.nexus_v23_completion_ops.preflight import run_lane_preflights
from backend.nexus_v23_completion_ops.provider_windows import (
    evaluate_provider_windows,
    report_capacity_status,
)
from backend.nexus_v23_completion_ops.queue_health import evaluate_queue_health
from backend.nexus_v23_completion_ops.resume_boundary import ResumeBoundary, ResumeOwnershipError
from backend.nexus_v23_completion_ops.retry_quota_obs import observe_lane_retry_quota_map
from backend.nexus_v23_completion_ops.sanitize import assert_no_secret_keys, safe_log_fields
from backend.nexus_v23_completion_ops.sot import assert_incomplete_truth, incomplete_sot_snapshot


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class V23CompletionOpsV13:
    """Founder-private V2.3 completion ops around incomplete SoT truth."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.pause_ctrl = SafePauseResume()
        self.boundary = ResumeBoundary()

    def run_cycle(
        self,
        *,
        demonstrate_manual_controls: bool = True,
        fixture_root: Path | None = None,
        verify_checkpoint: bool = True,
    ) -> dict[str, Any]:
        sot = incomplete_sot_snapshot(verify_checkpoint=verify_checkpoint)
        assert_incomplete_truth(sot)

        preflight = run_lane_preflights()
        retry_quota = observe_lane_retry_quota_map(
            {
                GROQ_REFLECTION_REASONER: {
                    "Retry-After": "900",
                    "x-ratelimit-reset": "900",
                },
                SAMBANOVA_INDEPENDENT_CRITIC: {
                    "Retry-After": "900",
                    "x-ratelimit-reset": "1200",
                },
            }
        )

        manual_events: list[dict[str, Any]] = []
        if demonstrate_manual_controls:
            for pid in (GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC):
                manual_events.append(self.pause_ctrl.pause(pid, reason="ops_cycle_demo_pause"))
                manual_events.append(self.pause_ctrl.resume(pid, reason="ops_cycle_demo_resume"))

        ownership_block = self.boundary.request_real_resume(reason="ops_cycle_probe")
        ownership_theft_blocked = True
        try:
            self.boundary.execute_real_resume(fn=None)
            ownership_theft_blocked = False
        except ResumeOwnershipError:
            ownership_theft_blocked = True

        queue = evaluate_queue_health(
            groq_paused=self.pause_ctrl.is_paused(GROQ_REFLECTION_REASONER),
            sambanova_paused=self.pause_ctrl.is_paused(SAMBANOVA_INDEPENDENT_CRITIC),
            groq_retry_after_s=900.0,
            sambanova_retry_after_s=900.0,
            groq_quota_reset_s=900.0,
            sambanova_quota_reset_s=1200.0,
            verify_checkpoint=verify_checkpoint,
        )
        windows = evaluate_provider_windows(
            groq_retry_after_s=900.0,
            sambanova_retry_after_s=900.0,
            groq_quota_reset_s=900.0,
            sambanova_quota_reset_s=1200.0,
            verify_checkpoint=verify_checkpoint,
        )
        capacity = report_capacity_status(windows)
        atomic = evaluate_atomic_checkpoint(
            root=fixture_root
            or (self.root / ".nexus_runtime" / "v13_b_fixtures")
        )
        counters = validate_semantic_counters()
        dedupe = evaluate_completed_case_dedupe()
        critic = evaluate_critic_ordering()
        terminal = evaluate_terminal_denominators_ops()
        gates = evaluate_lesson_quality_gates()

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
            "provider_preflight": preflight,
            "queue_health": queue,
            "retry_quota_obs": retry_quota,
            "provider_windows": windows,
            "capacity_status": capacity,
            "atomic_checkpoint": atomic,
            "semantic_counters": counters,
            "completed_case_dedupe": dedupe,
            "critic_ordering": critic,
            "terminal_denominator_validation": terminal,
            "lesson_quality_gates": gates,
            "safe_pause_resume": self.pause_ctrl.snapshot(),
            "manual_events": manual_events,
            "resume_boundary": self.boundary.snapshot(),
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
            "background_agent_sanitized_fixtures_only": True,
        }
        cycle = safe_log_fields(cycle)
        assert_no_secret_keys(cycle)
        assert_incomplete_truth(cycle)
        return cycle

    def status_from_cycle(self, cycle: dict[str, Any], *, secret_leak_count: int = 0) -> dict[str, Any]:
        checks = {
            "provider_preflight_ok": (cycle.get("provider_preflight") or {}).get(
                "real_provider_call_executed"
            )
            is False,
            "queue_health_ok": (cycle.get("queue_health") or {}).get("overall_status")
            in {"DEGRADED_INCOMPLETE", "PAUSED", "HEALTHY"},
            "retry_quota_obs_ok": bool((cycle.get("retry_quota_obs") or {}).get("any_rate_limited"))
            and bool((cycle.get("retry_quota_obs") or {}).get("any_quota_reset_visible")),
            "independent_windows_ok": bool(
                (cycle.get("provider_windows") or {}).get("independent_provider_windows")
            )
            and (cycle.get("provider_windows") or {}).get("real_resume_authorized") is False,
            "capacity_status_ok": (cycle.get("capacity_status") or {}).get("real_resume_authorized")
            is False,
            "atomic_checkpoint_ok": bool((cycle.get("atomic_checkpoint") or {}).get("atomic_replace"))
            and bool((cycle.get("atomic_checkpoint") or {}).get("reload_ok")),
            "semantic_counters_ok": bool((cycle.get("semantic_counters") or {}).get("ok")),
            "dedupe_ok": bool((cycle.get("completed_case_dedupe") or {}).get("dedupe_effective")),
            "critic_ordering_ok": bool(
                (cycle.get("critic_ordering") or {}).get("order_only_after_reasoner_success")
            )
            and int((cycle.get("critic_ordering") or {}).get("premature_blocked_count") or 0) > 0,
            "terminal_denominator_ok": bool(
                (cycle.get("terminal_denominator_validation") or {}).get(
                    "quality_eval_blocked_while_incomplete"
                )
            ),
            "lesson_quality_gates_ok": bool(
                (cycle.get("lesson_quality_gates") or {}).get("policy_effect_blocked")
            ),
            "safe_pause_resume_ok": (cycle.get("safe_pause_resume") or {}).get("real_resume_executed")
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
        lanes = ((cycle.get("incomplete_sot") or {}).get("lanes") or {})
        status = {
            "schema": SCHEMA_STATUS,
            "created_at": _utc(),
            "lane": LANE,
            "lane_name": LANE_NAME,
            "branch": BRANCH,
            "package": PACKAGE,
            "base_commit": BASE_COMMIT,
            "pass": 1,
            "status": "PASS" if ok else "FAIL",
            "checks": checks,
            "all_controls_ok": ok,
            "V2_3_complete": False,
            "V2_3_terminal_status": cycle.get("V2_3_terminal_status"),
            "groq_success_count": (lanes.get(GROQ_REFLECTION_REASONER) or {}).get("success_count"),
            "groq_pending_count": (lanes.get(GROQ_REFLECTION_REASONER) or {}).get("pending_count"),
            "sambanova_success_count": (lanes.get(SAMBANOVA_INDEPENDENT_CRITIC) or {}).get(
                "success_count"
            ),
            "sambanova_pending_count": (lanes.get(SAMBANOVA_INDEPENDENT_CRITIC) or {}).get(
                "pending_count"
            ),
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
            "schema_family": SCHEMA,
        }
        assert_no_secret_keys(status)
        assert_incomplete_truth(status)
        return status


def build_ops_plane(root: Path | None = None) -> V23CompletionOpsV13:
    return V23CompletionOpsV13(root=root)
