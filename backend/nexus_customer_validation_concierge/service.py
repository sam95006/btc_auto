"""Concierge validation app service — orchestrates local/staging workflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_customer_validation_concierge.constants import (
    API_PREFIX,
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    SCHEMA_VERSION,
    WORKFLOW_STEPS,
)
from backend.nexus_customer_validation_concierge.hard_bans import (
    assert_no_forbidden_keys,
    require_local_staging,
)
from tools.customer_validation.consent import REQUIRED_CONSENT_FLAGS, record_consent
from tools.customer_validation.decision_object_concierge import (
    DECISION_OBJECT_REQUIRED,
    record_concierge_delivery,
)
from tools.customer_validation.evidence import (
    OBJECTION_TAXONOMY,
    record_conversion_evidence,
    record_objection,
    record_retention_evidence,
    record_wtp_evidence,
)
from tools.customer_validation.hard_bans import HardBanViolation
from tools.customer_validation.integrity import compute_counters, run_three_pass_integrity
from tools.customer_validation.interview import (
    INTERVIEW_BLOCKS,
    complete_interview,
    start_interview,
)
from tools.customer_validation.problem_ranking import (
    DEFAULT_PROBLEM_CATALOG,
    record_problem_ranking,
)
from tools.customer_validation.registry import enroll_participant
from tools.customer_validation.store import ensure_workspace
from tools.customer_validation.watchlist_onboarding import record_watchlist_onboarding
from tools.customer_validation.weekly_review import GATE_OPTIONS, record_weekly_review
from tools.customer_validation.workflow_spine import workflow_spine_status


class ConciergeAppService:
    """Usable local/staging Concierge workflow for real participants only."""

    def __init__(self, workspace: Path | str | None = None) -> None:
        self.workspace = ensure_workspace(workspace)

    def meta(self) -> dict[str, Any]:
        env = require_local_staging()
        body = {
            "ok": True,
            "schema": SCHEMA_VERSION,
            "lane": LANE,
            "lane_name": LANE_NAME,
            "branch": BRANCH,
            "base_commit": BASE_COMMIT,
            "api_prefix": API_PREFIX,
            "environment": env["environment"],
            "hard_bans": list(HARD_BANS),
            "workflow_steps": list(WORKFLOW_STEPS),
            "production_customer_database": False,
            "live_billing": False,
            "exchange_write": False,
            "status_json_emitted": False,
            "note": "Counts remain 0 until real people participate.",
        }
        assert_no_forbidden_keys(body)
        return body

    def counters(self) -> dict[str, Any]:
        require_local_staging()
        counters = compute_counters(self.workspace)
        body = {
            "ok": True,
            "lane": LANE,
            "counters": counters,
            "all_zero": all(v == 0 for v in counters.values()),
            "fabricated": False,
            "status_json_emitted": False,
        }
        assert_no_forbidden_keys(body)
        return body

    def spine(self) -> dict[str, Any]:
        require_local_staging()
        body = {"ok": True, **workflow_spine_status(self.workspace)}
        assert_no_forbidden_keys(body)
        return body

    def three_pass_proof(self) -> dict[str, Any]:
        require_local_staging()
        proof = run_three_pass_integrity(self.workspace)
        body = {"ok": proof["ok"], "proof": proof}
        assert_no_forbidden_keys(body)
        return body

    def catalogs(self) -> dict[str, Any]:
        require_local_staging()
        return {
            "ok": True,
            "consent_flags": list(REQUIRED_CONSENT_FLAGS),
            "interview_blocks": list(INTERVIEW_BLOCKS),
            "problem_catalog": list(DEFAULT_PROBLEM_CATALOG),
            "decision_object_fields": list(DECISION_OBJECT_REQUIRED),
            "objection_taxonomy": list(OBJECTION_TAXONOMY),
            "weekly_gate_options": sorted(GATE_OPTIONS),
            "workflow_steps": list(WORKFLOW_STEPS),
        }

    def enroll(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = enroll_participant(
            participant_id=str(payload.get("participant_id") or ""),
            enrollment_source=str(payload.get("enrollment_source") or ""),
            contact_handle=str(payload.get("contact_handle") or ""),
            founder_attestation=bool(payload.get("founder_attestation")),
            icp_screener_passed=bool(payload.get("icp_screener_passed")),
            notes=str(payload.get("notes") or ""),
            workspace=self.workspace,
        )
        return {"ok": True, "step": "enroll", "record": row, "counters": compute_counters(self.workspace)}

    def step_consent(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = record_consent(
            participant_id=str(payload.get("participant_id") or ""),
            flags=dict(payload.get("flags") or {}),
            workspace=self.workspace,
        )
        return {"ok": True, "step": "consent", "record": row, "counters": compute_counters(self.workspace)}

    def step_interview_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = start_interview(
            participant_id=str(payload.get("participant_id") or ""),
            workspace=self.workspace,
        )
        return {"ok": True, "step": "interview_start", "record": row, "counters": compute_counters(self.workspace)}

    def step_interview_complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = complete_interview(
            participant_id=str(payload.get("participant_id") or ""),
            block_notes=dict(payload.get("block_notes") or {}),
            auto_trading_mandatory=bool(payload.get("auto_trading_mandatory")),
            workspace=self.workspace,
        )
        return {"ok": True, "step": "interview", "record": row, "counters": compute_counters(self.workspace)}

    def step_problem_ranking(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = record_problem_ranking(
            participant_id=str(payload.get("participant_id") or ""),
            ranked_problems=list(payload.get("ranked_problems") or []),
            workspace=self.workspace,
        )
        return {"ok": True, "step": "problem_ranking", "record": row, "counters": compute_counters(self.workspace)}

    def step_watchlist_onboarding(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = record_watchlist_onboarding(
            participant_id=str(payload.get("participant_id") or ""),
            symbols=list(payload.get("symbols") or []),
            thesis_links=list(payload.get("thesis_links") or []),
            alert_preferences=dict(payload.get("alert_preferences") or {}),
            exchange_write_requested=bool(payload.get("exchange_write_requested")),
            workspace=self.workspace,
        )
        return {
            "ok": True,
            "step": "watchlist_onboarding",
            "record": row,
            "counters": compute_counters(self.workspace),
        }

    def step_decision_object_delivery(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = record_concierge_delivery(
            participant_id=str(payload.get("participant_id") or ""),
            decision_id=str(payload.get("decision_id") or ""),
            fields_present=dict(payload.get("fields_present") or {}),
            week=int(payload.get("week") or 0),
            exchange_order_placed=bool(payload.get("exchange_order_placed")),
            workspace=self.workspace,
        )
        return {
            "ok": True,
            "step": "decision_object_delivery",
            "record": row,
            "counters": compute_counters(self.workspace),
        }

    def step_weekly_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = record_weekly_review(
            week=int(payload.get("week") or 0),
            active_participants=int(payload.get("active_participants") or 0),
            closed_decision_loops=int(payload.get("closed_decision_loops") or 0),
            thesis_completions=int(payload.get("thesis_completions") or 0),
            outcome_reviews=int(payload.get("outcome_reviews") or 0),
            qualitative_notes=str(payload.get("qualitative_notes") or ""),
            gate_posture=str(payload.get("gate_posture") or "DEFER"),
            operator_actions=list(payload.get("operator_actions") or []),
            workspace=self.workspace,
        )
        return {"ok": True, "step": "weekly_review", "record": row, "counters": compute_counters(self.workspace)}

    def step_retention(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = record_retention_evidence(
            participant_id=str(payload.get("participant_id") or ""),
            day_marker=int(payload.get("day_marker") or 0),
            retained=bool(payload.get("retained")),
            notes=str(payload.get("notes") or ""),
            workspace=self.workspace,
        )
        return {"ok": True, "step": "retention", "record": row, "counters": compute_counters(self.workspace)}

    def step_willingness_to_pay(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = record_wtp_evidence(
            participant_id=str(payload.get("participant_id") or ""),
            stated_willingness=str(payload.get("stated_willingness") or ""),
            package_preference=str(payload.get("package_preference") or ""),
            hard_no_buy_threshold=str(payload.get("hard_no_buy_threshold") or ""),
            prices_validated=bool(payload.get("prices_validated")),
            live_charge_attempted=bool(payload.get("live_charge_attempted")),
            workspace=self.workspace,
        )
        return {
            "ok": True,
            "step": "willingness_to_pay",
            "record": row,
            "counters": compute_counters(self.workspace),
        }

    def step_objections(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = record_objection(
            participant_id=str(payload.get("participant_id") or ""),
            objection_code=str(payload.get("objection_code") or ""),
            detail=str(payload.get("detail") or ""),
            workspace=self.workspace,
        )
        return {"ok": True, "step": "objections", "record": row, "counters": compute_counters(self.workspace)}

    def step_pilot_conversion(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_local_staging()
        row = record_conversion_evidence(
            participant_id=str(payload.get("participant_id") or ""),
            conversion_type=str(payload.get("conversion_type") or "paid_pilot"),
            status=str(payload.get("status") or "intent_only"),
            amount_claimed=payload.get("amount_claimed"),
            live_payment_processed=bool(payload.get("live_payment_processed")),
            workspace=self.workspace,
        )
        return {
            "ok": True,
            "step": "pilot_conversion",
            "record": row,
            "counters": compute_counters(self.workspace),
        }


def error_body(exc: Exception) -> tuple[dict[str, Any], int]:
    if isinstance(exc, HardBanViolation):
        return (
            {
                "ok": False,
                "error": "hard_ban_violation",
                "detail": str(exc),
                "lane": LANE,
            },
            403,
        )
    return {"ok": False, "error": "request_failed", "detail": str(exc), "lane": LANE}, 400
