"""End-to-end shadow pipeline orchestrator for tests."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow.candidates import GlobalCandidateRanker
from backend.nexus_global_shadow.contracts import (
    Candidate,
    LifecycleState,
    MarketObservation,
    ShadowPosition,
    SixRoleReviewSet,
)
from backend.nexus_global_shadow.intelligence import GlobalMarketIntelligenceComposer
from backend.nexus_global_shadow.lifecycle import ShadowLifecycleManager
from backend.nexus_global_shadow.portfolio import ShadowPortfolioPolicy
from backend.nexus_global_shadow.regime import RegimeRouter
from backend.nexus_global_shadow.six_role import SixRoleDecisionAggregator
from backend.nexus_global_shadow.strategy import StrategyRouter
from backend.nexus_global_shadow.universe import (
    DynamicMarketUniverseProvider,
    MarketUniverseBuilder,
    UniverseSnapshotStore,
)


class GlobalShadowPipeline:
    """Universe → Regime → Strategy → Intelligence → Candidate → Six-role → Portfolio → Lifecycle."""

    def __init__(
        self,
        instrument_source: list[dict[str, Any]] | Any,
        quality_by_symbol: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        provider = DynamicMarketUniverseProvider(instrument_source)
        self.builder = MarketUniverseBuilder(provider)
        self.universe_store = UniverseSnapshotStore()
        self.regime_router = RegimeRouter()
        self.strategy_router = StrategyRouter()
        self.intelligence = GlobalMarketIntelligenceComposer()
        self.ranker = GlobalCandidateRanker()
        self.six_role = SixRoleDecisionAggregator()
        self.portfolio = ShadowPortfolioPolicy()
        self.lifecycle = ShadowLifecycleManager()
        self.quality_by_symbol = quality_by_symbol or {}

    def run_cycle(
        self,
        *,
        directions: dict[str, str] | None = None,
        strategy_ids: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        snap = self.builder.build(self.quality_by_symbol)
        self.universe_store.save(snap)
        candidates: list[Candidate] = []
        review_sets: dict[str, SixRoleReviewSet] = {}
        for item in snap.instruments:
            inst = item.get("instrument") or {}
            sym = str(inst.get("symbol") or "")
            elig = item.get("eligibility") or {}
            if not elig.get("eligible"):
                continue
            obs_raw = self.quality_by_symbol.get(sym, {})
            obs = MarketObservation(
                symbol=sym,
                last_price=obs_raw.get("last_price"),
                momentum=obs_raw.get("momentum"),
                volatility=obs_raw.get("volatility"),
                spread_bps=obs_raw.get("spread_bps"),
                volume_24h=obs_raw.get("volume_24h"),
                funding_rate=obs_raw.get("funding_rate"),
                open_interest=obs_raw.get("open_interest"),
                liquidity_score=obs_raw.get("liquidity_score"),
                freshness=obs_raw.get("freshness", "FRESH"),
            )
            from backend.nexus_global_shadow.universe import MarketQualityEvaluator

            qev = MarketQualityEvaluator()
            quality = qev.evaluate(sym, obs_raw)
            regime = self.regime_router.classify(obs)
            sid = (strategy_ids or {}).get(sym, "trend_following")
            strat = self.strategy_router.route(sid, obs, quality, regime)
            intel = self.intelligence.compose(sym, obs, quality, regime)
            direction = (directions or {}).get(sym, "LONG")
            cand = self.ranker.build_candidate(
                sym,
                snap.universe_snapshot_id,
                direction,
                strat,
                intel,
                regime,
            )
            candidates.append(cand)
            rs = self.six_role.review_candidate(cand, intel)
            review_sets[cand.candidate_id] = rs
        ranked = self.ranker.rank(candidates)
        verdicts = self.portfolio.evaluate(ranked, review_sets)
        selected = [v for v in verdicts if v.selected]
        positions: list[ShadowPosition] = []
        for v in selected[:2]:
            cand = next(c for c in ranked if c.candidate_id == v.candidate_id)
            pos = ShadowPosition(
                candidate_id=cand.candidate_id,
                symbol=cand.symbol,
                direction=cand.direction,
                strategy_id=cand.strategy_id,
                regime=cand.regime,
                state=LifecycleState.CANDIDATE.value,
                position_size=1.0,
                risk_budget=0.25,
            )
            positions.append(pos)
        return {
            "universe_snapshot_id": snap.universe_snapshot_id,
            "universe_count": snap.total_markets,
            "eligible_count": snap.eligible_markets,
            "candidate_count": len(candidates),
            "six_role_reviewed_count": len(review_sets),
            "risk_pass_count": sum(
                1 for rs in review_sets.values() if rs.risk_critic_verdict == "PASS"
            ),
            "risk_block_count": sum(
                1 for rs in review_sets.values() if rs.risk_critic_verdict in {"BLOCK", "UNKNOWN"}
            ),
            "portfolio_selected_count": len(selected),
            "outcome_count": 0,
            "candidates": [c.to_dict() for c in ranked],
            "verdicts": [v.to_dict() for v in verdicts],
            "positions": [p.to_dict() for p in positions],
            "provider_status": snap.provider_status,
        }
