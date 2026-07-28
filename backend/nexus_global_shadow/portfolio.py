"""Shadow portfolio policy — max 2 open, max 2 pending."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow import (
    CORRELATION_GROUP_RISK_MAX,
    HIGH_RISK_SMALL_MARKET_MAX_POSITIONS,
    MAX_OPEN_POSITIONS,
    MAX_PENDING_ORDERS,
    PORTFOLIO_OPEN_RISK_MAX,
    RISK_PER_POSITION_MAX,
    RISK_PER_POSITION_MIN,
)
from backend.nexus_global_shadow.contracts import (
    Candidate,
    PortfolioVerdict,
    RoleVerdict,
    ShadowPosition,
    SixRoleReviewSet,
    now_ms,
)


class ShadowPortfolioPolicy:
    """Portfolio selection with correlation/direction/strategy gates."""

    POLICY_VERSION = "v1"

    def __init__(self) -> None:
        self.max_open = MAX_OPEN_POSITIONS
        self.max_pending = MAX_PENDING_ORDERS

    def evaluate(
        self,
        candidates: list[Candidate],
        review_sets: dict[str, SixRoleReviewSet],
        *,
        open_positions: list[ShadowPosition] | None = None,
        pending_intents: list[dict[str, Any]] | None = None,
        correlation_groups: dict[str, str] | None = None,
    ) -> list[PortfolioVerdict]:
        open_positions = open_positions or []
        pending_intents = pending_intents or []
        correlation_groups = correlation_groups or {}
        open_symbols = {p.symbol for p in open_positions}
        open_dirs: dict[str, int] = {}
        strat_exp: dict[str, int] = {}
        cluster_exp: dict[str, int] = {}
        portfolio_risk = sum(p.risk_budget or 0 for p in open_positions)
        pending_risk = sum(p.get("risk_budget") or 0 for p in pending_intents)
        seen_candidates: set[str] = set()
        verdicts: list[PortfolioVerdict] = []
        selected_ids: list[str] = []
        rank = 0

        sorted_cands = sorted(
            candidates,
            key=lambda c: (c.rank if c.rank is not None else 999, c.candidate_id),
        )

        for cand in sorted_cands:
            blocks: list[str] = []
            rs = review_sets.get(cand.candidate_id)
            if not rs or not rs.review_complete:
                blocks.append("six_role_incomplete")
            elif rs.risk_critic_verdict in {RoleVerdict.BLOCK.value, RoleVerdict.UNKNOWN.value}:
                blocks.append(f"risk_critic:{rs.risk_critic_verdict}")
            if cand.candidate_id in seen_candidates:
                blocks.append("duplicate_candidate")
            seen_candidates.add(cand.candidate_id)
            if cand.symbol in open_symbols:
                blocks.append("same_symbol_conflict")
            dir_key = cand.direction
            open_dirs[dir_key] = open_dirs.get(dir_key, 0)
            if open_dirs.get("LONG", 0) + open_dirs.get("SHORT", 0) >= 2 and dir_key in {"LONG", "SHORT"}:
                if sum(1 for p in open_positions if p.direction == dir_key) >= 2:
                    blocks.append("direction_concentration")
            grp = correlation_groups.get(cand.symbol, cand.symbol[:3])
            cluster_exp[grp] = cluster_exp.get(grp, 0) + sum(
                1 for p in open_positions if correlation_groups.get(p.symbol, p.symbol[:3]) == grp
            )
            if cluster_exp.get(grp, 0) >= 2:
                blocks.append("cluster_exposure")
            strat_exp[cand.strategy_id] = strat_exp.get(cand.strategy_id, 0) + sum(
                1 for p in open_positions if p.strategy_id == cand.strategy_id
            )
            if strat_exp.get(cand.strategy_id, 0) >= 2:
                blocks.append("strategy_concentration")
            risk_tier = cand.score_components.get("risk_tier") if cand.score_components else None
            if risk_tier == "HIGH" and sum(
                1 for p in open_positions if correlation_groups.get(p.symbol) == grp
            ) >= HIGH_RISK_SMALL_MARKET_MAX_POSITIONS:
                blocks.append("high_risk_small_market_limit")
            marginal = RISK_PER_POSITION_MIN
            risk_after = portfolio_risk + pending_risk + marginal
            if risk_after > PORTFOLIO_OPEN_RISK_MAX:
                blocks.append("portfolio_risk_max")
            if len(open_positions) + len(selected_ids) >= self.max_open:
                blocks.append("max_open_positions")
            if len(pending_intents) >= self.max_pending:
                blocks.append("max_pending_orders")
            selected = not blocks and cand.status not in {"REJECTED", "EXPIRED", "RISK_BLOCKED"}
            if selected:
                rank += 1
                selected_ids.append(cand.candidate_id)
                portfolio_risk += marginal
                open_dirs[dir_key] = open_dirs.get(dir_key, 0) + 1
            verdicts.append(
                PortfolioVerdict(
                    candidate_id=cand.candidate_id,
                    selected=selected,
                    portfolio_rank=rank if selected else None,
                    risk_before=portfolio_risk - (marginal if selected else 0),
                    risk_after=portfolio_risk if selected else portfolio_risk,
                    marginal_contribution=marginal if selected else None,
                    correlation_group=grp,
                    direction_exposure=dict(open_dirs),
                    strategy_exposure=dict(strat_exp),
                    cluster_exposure=dict(cluster_exp),
                    block_reasons=blocks,
                    policy_version=self.POLICY_VERSION,
                    evaluated_at=now_ms(),
                    open_positions=len(open_positions) + len(selected_ids),
                    pending_intents=len(pending_intents),
                    selected_ids=list(selected_ids),
                )
            )
            if len(selected_ids) >= self.max_open:
                break
        return verdicts

    def risk_per_position_bounds(self) -> tuple[float, float]:
        return RISK_PER_POSITION_MIN, RISK_PER_POSITION_MAX

    def correlation_cap(self) -> float:
        return CORRELATION_GROUP_RISK_MAX
