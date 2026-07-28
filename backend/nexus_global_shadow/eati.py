"""EATI shadow learning pipeline — no LIVE_APPLIED."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow.contracts import LearningPatch, Outcome, Reflection, now_ms

FAILURE_CLASSES = frozenset(
    {
        "DATA_FAILURE",
        "REGIME_FAILURE",
        "STRATEGY_FAILURE",
        "ENTRY_FAILURE",
        "EXIT_FAILURE",
        "RISK_FAILURE",
        "PORTFOLIO_FAILURE",
        "EXECUTION_SIMULATION_FAILURE",
        "PROVIDER_FAILURE",
        "INSUFFICIENT_EVIDENCE",
        "UNKNOWN",
    }
)

PATCH_STATUSES = frozenset(
    {
        "PROPOSED",
        "REPLAY_VALIDATED",
        "WALK_FORWARD_VALIDATED",
        "OOS_VALIDATED",
        "RISK_REVIEWED",
        "REJECTED",
        "SHADOW_APPLIED",
    }
)

FORBIDDEN_PATCH_STATUSES = frozenset({"LIVE_APPLIED", "AUTO_PROMOTED", "PRODUCTION_PROMOTED"})


class EATIShadowLearningPipeline:
    """Outcome → Reflection → Patch proposal → validation chain."""

    def classify_failure(self, outcome: Outcome, reflection_context: dict[str, Any] | None = None) -> str:
        ctx = reflection_context or {}
        if outcome.incomplete:
            return "INSUFFICIENT_EVIDENCE"
        if ctx.get("data_quality_issue"):
            return "DATA_FAILURE"
        if ctx.get("regime_mismatch"):
            return "REGIME_FAILURE"
        if ctx.get("strategy_mismatch"):
            return "STRATEGY_FAILURE"
        if ctx.get("entry_issue"):
            return "ENTRY_FAILURE"
        if ctx.get("exit_issue"):
            return "EXIT_FAILURE"
        if ctx.get("risk_issue"):
            return "RISK_FAILURE"
        if ctx.get("portfolio_issue"):
            return "PORTFOLIO_FAILURE"
        if ctx.get("execution_simulation_issue"):
            return "EXECUTION_SIMULATION_FAILURE"
        if ctx.get("provider_failure"):
            return "PROVIDER_FAILURE"
        if outcome.net_pnl is not None and outcome.net_pnl < 0:
            return "STRATEGY_FAILURE"
        return "UNKNOWN"

    def create_reflection(
        self,
        outcome: Outcome,
        *,
        expected: str = "",
        context: dict[str, Any] | None = None,
    ) -> Reflection:
        ctx = context or {}
        failure = self.classify_failure(outcome, ctx)
        return Reflection(
            outcome_id=outcome.record_id,
            symbol=outcome.symbol,
            what_happened=f"exit:{outcome.exit_reason} pnl:{outcome.net_pnl}",
            what_was_expected=expected or "positive_expectancy",
            what_differed=ctx.get("what_differed") or "",
            data_quality_issue=ctx.get("data_quality_issue"),
            regime_mismatch=ctx.get("regime_mismatch"),
            strategy_mismatch=ctx.get("strategy_mismatch"),
            entry_issue=ctx.get("entry_issue"),
            exit_issue=ctx.get("exit_issue"),
            risk_issue=ctx.get("risk_issue"),
            portfolio_issue=ctx.get("portfolio_issue"),
            execution_simulation_issue=ctx.get("execution_simulation_issue"),
            proposed_change=ctx.get("proposed_change"),
            expected_effect=ctx.get("expected_effect"),
            risk_of_change=ctx.get("risk_of_change"),
            failure_class=failure,
        )

    def propose_patch(self, reflection: Reflection, *, strategy: str = "", regime: str = "") -> LearningPatch:
        return LearningPatch(
            source_reflection_ids=[reflection.record_id],
            change_scope="shadow_only",
            affected_strategy=strategy or "global",
            affected_regime=regime or "any",
            before_behavior="baseline",
            after_behavior=reflection.proposed_change or "tune_thresholds",
            status="PROPOSED",
            sample_sufficiency="UNKNOWN",
        )

    def validate_replay(self, patch: LearningPatch, result: str) -> LearningPatch:
        patch.replay_result = result
        if result == "PASS":
            patch.status = "REPLAY_VALIDATED"
        else:
            patch.status = "REJECTED"
        return patch

    def validate_walk_forward(self, patch: LearningPatch, result: str, folds: int) -> LearningPatch:
        patch.walk_forward_result = result
        if folds < 3:
            patch.sample_sufficiency = "INSUFFICIENT_SAMPLE"
            patch.status = "REJECTED"
        elif result == "PASS":
            patch.status = "WALK_FORWARD_VALIDATED"
        else:
            patch.status = "REJECTED"
        return patch

    def validate_oos(self, patch: LearningPatch, result: str, *, isolated: bool) -> LearningPatch:
        patch.oos_result = result
        if not isolated:
            patch.status = "REJECTED"
            patch.sample_sufficiency = "INSUFFICIENT_SAMPLE"
        elif result == "PASS":
            patch.status = "OOS_VALIDATED"
        else:
            patch.status = "REJECTED"
        return patch

    def apply_shadow(self, patch: LearningPatch) -> LearningPatch:
        if patch.status != "OOS_VALIDATED":
            raise ValueError("patch_not_oos_validated")
        patch.status = "SHADOW_APPLIED"
        patch.applied_at = now_ms()
        return patch

    def assert_no_live_apply(self, status: str) -> None:
        if status in FORBIDDEN_PATCH_STATUSES:
            raise ValueError(f"forbidden_patch_status:{status}")
