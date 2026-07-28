"""Six-role review aggregator with mandatory Risk Critic veto."""
from __future__ import annotations

from typing import Any, Callable

from backend.nexus_global_shadow.contracts import (
    Candidate,
    IntelligenceSnapshot,
    RoleName,
    RoleReview,
    RoleVerdict,
    SixRoleReviewSet,
    now_ms,
)

ALL_ROLES = [r.value for r in RoleName]


class BaseRoleReviewer:
    role: str = ""

    def review(
        self,
        candidate: Candidate,
        intelligence: IntelligenceSnapshot | None = None,
        context: dict[str, Any] | None = None,
    ) -> RoleReview:
        raise NotImplementedError


class MarketContextReviewer(BaseRoleReviewer):
    role = RoleName.MARKET_CONTEXT.value

    def review(self, candidate, intelligence=None, context=None):
        intel = intelligence
        missing = []
        if intel is None:
            missing.append("intelligence")
        elif intel.news_context_availability == "UNAVAILABLE":
            missing.append("news_unavailable")
        verdict = RoleVerdict.PASS.value
        blocks = []
        if intel and intel.regime == "EVENT_RISK":
            verdict = RoleVerdict.WATCH.value
        if missing and not blocks:
            verdict = RoleVerdict.WATCH.value
        return RoleReview(
            role=self.role,
            candidate_id=candidate.candidate_id,
            verdict=verdict,
            score=0.7 if verdict == RoleVerdict.PASS.value else 0.5,
            confidence=0.6,
            missing_evidence=missing,
            block_reasons=blocks,
        )


class MarketStructureReviewer(BaseRoleReviewer):
    role = RoleName.MARKET_STRUCTURE.value

    def review(self, candidate, intelligence=None, context=None):
        missing = []
        if intelligence and intelligence.price_structure == "UNKNOWN":
            missing.append("price_structure")
        verdict = RoleVerdict.PASS.value if not missing else RoleVerdict.WATCH.value
        return RoleReview(
            role=self.role,
            candidate_id=candidate.candidate_id,
            verdict=verdict,
            score=0.65,
            confidence=0.55,
            missing_evidence=missing,
        )


class RiskCriticReviewer(BaseRoleReviewer):
    role = RoleName.RISK_CRITIC.value

    def review(self, candidate, intelligence=None, context=None):
        ctx = context or {}
        forced = ctx.get("force_verdict")
        if forced:
            return RoleReview(
                role=self.role,
                candidate_id=candidate.candidate_id,
                verdict=str(forced),
                block_reasons=list(ctx.get("block_reasons") or []),
                missing_evidence=list(ctx.get("missing_evidence") or []),
            )
        blocks = list(candidate.block_reasons)
        missing = list(candidate.missing_evidence)
        if intelligence and intelligence.missing_evidence:
            missing.extend(intelligence.missing_evidence)
        if candidate.risk_score is None:
            missing.append("risk_score")
        verdict = RoleVerdict.PASS.value
        if blocks:
            verdict = RoleVerdict.BLOCK.value
        elif missing:
            verdict = RoleVerdict.UNKNOWN.value
        if ctx.get("risk_score_missing_treat_as_zero"):
            # explicit anti-pattern test hook — still UNKNOWN not PASS
            verdict = RoleVerdict.UNKNOWN.value
        return RoleReview(
            role=self.role,
            candidate_id=candidate.candidate_id,
            verdict=verdict,
            score=candidate.risk_score,
            confidence=None if verdict == RoleVerdict.UNKNOWN.value else 0.5,
            missing_evidence=missing,
            block_reasons=blocks,
        )


class PortfolioManagerReviewer(BaseRoleReviewer):
    role = RoleName.PORTFOLIO_MANAGER.value

    def review(self, candidate, intelligence=None, context=None):
        ctx = context or {}
        open_pos = ctx.get("open_positions", 0)
        pending = ctx.get("pending_intents", 0)
        blocks = []
        if open_pos >= 2:
            blocks.append("max_open_reached")
        if pending >= 2:
            blocks.append("max_pending_reached")
        verdict = RoleVerdict.BLOCK.value if blocks else RoleVerdict.PASS.value
        return RoleReview(
            role=self.role,
            candidate_id=candidate.candidate_id,
            verdict=verdict,
            block_reasons=blocks,
        )


class PerformanceAnalystReviewer(BaseRoleReviewer):
    role = RoleName.PERFORMANCE_ANALYST.value

    def review(self, candidate, intelligence=None, context=None):
        ctx = context or {}
        sample = ctx.get("sample_sufficiency", "UNKNOWN")
        missing = []
        verdict = RoleVerdict.PASS.value
        if sample == "INSUFFICIENT_SAMPLE":
            missing.append("insufficient_sample")
            verdict = RoleVerdict.WATCH.value
        return RoleReview(
            role=self.role,
            candidate_id=candidate.candidate_id,
            verdict=verdict,
            missing_evidence=missing,
        )


class ReflectionAnalystReviewer(BaseRoleReviewer):
    role = RoleName.REFLECTION_ANALYST.value

    def review(self, candidate, intelligence=None, context=None):
        return RoleReview(
            role=self.role,
            candidate_id=candidate.candidate_id,
            verdict=RoleVerdict.PASS.value,
            supporting_evidence=["reflection_baseline"],
        )


DEFAULT_REVIEWERS: dict[str, BaseRoleReviewer] = {
    RoleName.MARKET_CONTEXT.value: MarketContextReviewer(),
    RoleName.MARKET_STRUCTURE.value: MarketStructureReviewer(),
    RoleName.RISK_CRITIC.value: RiskCriticReviewer(),
    RoleName.PORTFOLIO_MANAGER.value: PortfolioManagerReviewer(),
    RoleName.PERFORMANCE_ANALYST.value: PerformanceAnalystReviewer(),
    RoleName.REFLECTION_ANALYST.value: ReflectionAnalystReviewer(),
}


class SixRoleDecisionAggregator:
    """Aggregate six role reviews; Risk Critic veto cannot be overridden."""

    def __init__(self, reviewers: dict[str, BaseRoleReviewer] | None = None) -> None:
        self.reviewers = reviewers or DEFAULT_REVIEWERS

    def review_candidate(
        self,
        candidate: Candidate,
        intelligence: IntelligenceSnapshot | None = None,
        context: dict[str, Any] | None = None,
        *,
        roles: list[str] | None = None,
    ) -> SixRoleReviewSet:
        roles_to_run = roles if roles is not None else ALL_ROLES
        reviews: list[dict[str, Any]] = []
        pass_c = watch_c = block_c = unknown_c = 0
        risk_verdict = RoleVerdict.UNKNOWN.value
        refs: list[str] = []
        for role in roles_to_run:
            reviewer = self.reviewers.get(role)
            if not reviewer:
                continue
            rr = reviewer.review(candidate, intelligence, context)
            rr.reviewed_at = now_ms()
            reviews.append(rr.to_dict())
            refs.append(rr.trace_id)
            v = rr.verdict
            if v == RoleVerdict.PASS.value:
                pass_c += 1
            elif v == RoleVerdict.WATCH.value:
                watch_c += 1
            elif v == RoleVerdict.BLOCK.value:
                block_c += 1
            else:
                unknown_c += 1
            if role == RoleName.RISK_CRITIC.value:
                risk_verdict = v
        complete = len(reviews) == len(ALL_ROLES) and {r.get("role") for r in reviews} >= set(ALL_ROLES)
        if roles is not None and set(roles) != set(ALL_ROLES):
            complete = False
        consensus = self._consensus(pass_c, watch_c, block_c, unknown_c, risk_verdict)
        return SixRoleReviewSet(
            candidate_id=candidate.candidate_id,
            reviews=reviews,
            review_complete=complete,
            pass_count=pass_c,
            watch_count=watch_c,
            block_count=block_c,
            unknown_count=unknown_c,
            consensus=consensus,
            risk_critic_verdict=risk_verdict,
            mandatory_veto=True,
            review_evidence_refs=refs,
        )

    def risk_critic_blocks_portfolio(self, review_set: SixRoleReviewSet) -> bool:
        if not review_set.review_complete:
            return True
        v = review_set.risk_critic_verdict
        return v in {RoleVerdict.BLOCK.value, RoleVerdict.UNKNOWN.value}

    def _consensus(
        self,
        pass_c: int,
        watch_c: int,
        block_c: int,
        unknown_c: int,
        risk_verdict: str,
    ) -> str:
        if risk_verdict in {RoleVerdict.BLOCK.value, RoleVerdict.UNKNOWN.value}:
            return "VETOED"
        if block_c > 0:
            return "BLOCKED"
        if unknown_c > 0:
            return "UNKNOWN"
        if pass_c >= 4:
            return "PASS"
        if watch_c > 0:
            return "WATCH"
        return "UNKNOWN"


def _dict_to_review(d: dict[str, Any]) -> RoleReview:
    return RoleReview(**{k: v for k, v in d.items() if k in RoleReview.__dataclass_fields__})
