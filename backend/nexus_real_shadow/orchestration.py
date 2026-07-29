"""End-to-end real public shadow runtime orchestration."""
from __future__ import annotations

from typing import Any

from backend.nexus_adaptive_policy.adaptive_controller import AdaptivePolicyController
from backend.nexus_adaptive_policy.champion_challenger import PromotionGate
from backend.nexus_adaptive_policy.constitution import LeverageConstitution
from backend.nexus_adaptive_policy.mistake_memory import MistakeMemoryStore
from backend.nexus_adaptive_policy.reflection import DeepReflectionEngine
from backend.nexus_adaptive_policy.similarity import GuardAction, PreTradeMistakeGuard
from backend.nexus_global_shadow.candidates import GlobalCandidateRanker
from backend.nexus_global_shadow.contracts import MarketObservation, new_id
from backend.nexus_global_shadow.intelligence import GlobalMarketIntelligenceComposer
from backend.nexus_global_shadow.lifecycle import ShadowLifecycleManager
from backend.nexus_global_shadow.portfolio import ShadowPortfolioPolicy
from backend.nexus_global_shadow.regime import RegimeRouter
from backend.nexus_global_shadow.six_role import SixRoleDecisionAggregator
from backend.nexus_global_shadow.strategy import StrategyRouter
from backend.nexus_real_shadow import FIXED_LEVERAGE, MAX_OPEN, PUBLIC_MARKET_DATA_ONLY, SHADOW_LABELS
from backend.nexus_real_shadow.instruments import DynamicInstrumentDiscoveryWorker
from backend.nexus_real_shadow.market_pipeline import PublicMarketPipeline
from backend.nexus_real_shadow.quality import RealMarketQualityEvaluator
from backend.nexus_real_shadow.real_price_shadow import RealPriceShadowExecutionSimulator
from backend.nexus_real_shadow.reconciliation import ShadowReconciliationService
from backend.nexus_real_shadow.tiered_scan import TieredMarketScanner
from backend.nexus_real_shadow.workers import Wave5WorkerHealthRegistry


class NexusRealPublicShadowRuntime:
    """Discover → tier scan → quality → regime → strategy → rank → six-role → portfolio → shadow."""

    def __init__(self) -> None:
        self.correlation_id = new_id("corr")
        self.discovery = DynamicInstrumentDiscoveryWorker()
        self.market_data = PublicMarketPipeline(use_fixtures=True)
        self.tier_scanner = TieredMarketScanner()
        self.quality = RealMarketQualityEvaluator()
        self.regime_router = RegimeRouter()
        self.strategy_router = StrategyRouter()
        self.intelligence = GlobalMarketIntelligenceComposer()
        self.ranker = GlobalCandidateRanker()
        self.six_role = SixRoleDecisionAggregator()
        self.portfolio = ShadowPortfolioPolicy()
        self.lifecycle = ShadowLifecycleManager()
        self.simulator = RealPriceShadowExecutionSimulator()
        self.reconciliation = ShadowReconciliationService()
        self.workers = Wave5WorkerHealthRegistry()
        self.workers.ensure_all_types_registered()
        self.leverage_constitution = LeverageConstitution()
        self.mistake_store = MistakeMemoryStore()
        self.mistake_guard = PreTradeMistakeGuard(self.mistake_store, fixed_leverage=FIXED_LEVERAGE)
        self.adaptive = AdaptivePolicyController(guard=self.mistake_guard)
        self.reflection = DeepReflectionEngine()
        self.champion = PromotionGate()
        self.last_cycle: dict[str, Any] | None = None
        self.block_new_entries = False

    def run_cycle(self) -> dict[str, Any]:
        if self.workers.block_new_entries():
            return self._blocked_cycle("worker_stalled")

        uni_worker = "instrument_discovery_worker"
        self.workers.heartbeat(uni_worker, stage="discover")
        universe = self.discovery.discover()
        if universe.provider_status in {"UNIVERSE_UNAVAILABLE", "UNIVERSE_DEGRADED"} and not universe.instruments:
            self.workers.mark_stalled(uni_worker, universe.provider_status)
            return self._blocked_cycle(universe.provider_status)

        symbols = [str(i.get("symbol")) for i in universe.instruments if i.get("symbol")]
        self.workers.heartbeat("market_data_worker", stage="fetch")
        market_by_symbol = self.market_data.fetch_many(symbols)

        self.workers.heartbeat("tier_scan_worker", stage="scan")
        tier = self.tier_scanner.scan(universe.instruments, market_by_symbol)

        candidates = []
        reviews = {}
        quality_rows = []
        for sym in tier.tier3_symbols:
            raw = market_by_symbol.get(sym) or {}
            qv = self.quality.evaluate(sym, raw)
            quality_rows.append(qv.to_dict())
            if not qv.eligible:
                continue
            obs = MarketObservation(
                symbol=sym,
                last_price=raw.get("last_price"),
                momentum=raw.get("momentum"),
                volatility=raw.get("volatility"),
                spread_bps=raw.get("spread_bps"),
                volume_24h=raw.get("volume_24h"),
                funding_rate=raw.get("funding_rate"),
                open_interest=raw.get("open_interest"),
                liquidity_score=qv.liquidity_score,
                freshness=raw.get("freshness") or "MISSING",
            )
            regime = self.regime_router.classify(obs)
            from backend.nexus_global_shadow.universe import MarketQualityEvaluator

            inner_q = MarketQualityEvaluator().evaluate(sym, raw)
            strat = self.strategy_router.route("trend_following", obs, inner_q, regime)
            intel = self.intelligence.compose(sym, obs, inner_q, regime)
            cand = self.ranker.build_candidate(
                sym,
                universe.universe_snapshot_id,
                "LONG" if (raw.get("momentum") or 0) >= 0 else "SHORT",
                strat,
                intel,
                regime,
            )
            cand.correlation_id = self.correlation_id
            guard = self.mistake_guard.evaluate(symbol=sym, strategy_id="trend_following")
            if guard.action == GuardAction.BLOCK:
                continue
            rs = self.six_role.review_candidate(cand, intel)
            reviews[cand.candidate_id] = rs
            candidates.append(cand)

        ranked = self.ranker.rank(candidates)
        verdicts = self.portfolio.evaluate(ranked, reviews)
        selected = [v for v in verdicts if v.selected][:MAX_OPEN]

        policy = {
            "candidate_count": len(ranked),
            "portfolio_selected": len(selected),
            "fixed_leverage": FIXED_LEVERAGE,
            "adaptive_mode": "SHADOW_ONLY",
        }

        shadow_intents = []
        if not self.block_new_entries:
            for v in selected:
                cand = next(c for c in ranked if c.candidate_id == v.candidate_id)
                raw = market_by_symbol.get(cand.symbol) or {}
                intent = self.simulator.create_intent(
                    symbol=cand.symbol,
                    direction=cand.direction,
                    margin_usdt=50.0,
                    correlation_id=self.correlation_id,
                )
                if hasattr(intent, "intent_id"):
                    fill = self.simulator.simulate_fill(
                        intent,
                        entry_price=raw.get("last_price"),
                        funding_rate=raw.get("funding_rate"),
                    )
                    if hasattr(fill, "position_id"):
                        shadow_intents.append(intent.to_dict())
                        self.lifecycle.register_position(fill)

        cycle = {
            "correlation_id": self.correlation_id,
            "labels": list(SHADOW_LABELS),
            "public_market_data_only": PUBLIC_MARKET_DATA_ONLY,
            "fixed_leverage": FIXED_LEVERAGE,
            "universe": universe.to_dict(),
            "tier_scan": tier.to_dict(),
            "quality_count": len(quality_rows),
            "candidate_count": len(ranked),
            "six_role_reviewed": len(reviews),
            "portfolio_selected": len(selected),
            "shadow_intents": shadow_intents,
            "open_positions": len(self.simulator.open_positions),
            "policy": policy,
            "provider_status": universe.provider_status,
            "markets_scanned": tier.tier1_count,
            "markets_eligible": tier.tier3_count,
        }
        self.last_cycle = cycle
        self.workers.heartbeat("shadow_lifecycle_worker", stage="complete")
        return cycle

    def _blocked_cycle(self, reason: str) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "blocked": True,
            "reason": reason,
            "labels": list(SHADOW_LABELS),
            "public_market_data_only": PUBLIC_MARKET_DATA_ONLY,
            "fixed_leverage": FIXED_LEVERAGE,
            "markets_scanned": 0,
            "markets_eligible": 0,
            "candidate_count": 0,
            "portfolio_selected": 0,
            "open_positions": len(self.simulator.open_positions),
        }

    def restart_reconcile(self, persisted: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        runtime = [p.to_dict() for p in self.simulator.open_positions.values()]
        result = self.reconciliation.reconcile(
            persisted_positions=persisted,
            runtime_positions=runtime,
        )
        self.block_new_entries = result.block_new_entries
        return result.to_dict()
