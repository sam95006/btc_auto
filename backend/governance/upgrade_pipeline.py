from __future__ import annotations

from backend.autonomy import ShadowModeService, StrategyVersionRegistry
from backend.decision.decision_trace_store import DecisionTraceStore
from backend.governance.execution_governor import ExecutionGovernor
from backend.governance.trade_proposal_service import TradeProposalService
from backend.learning.learning_review_queue import LearningReviewQueue
from backend.market.universe_filter_service import UniverseFilterService
from backend.monitoring.execution_quality_monitor import ExecutionQualityMonitor
from config.autonomy_config import NEXUS_AUTONOMY_LEVEL, NEXUS_LEARNING_AUTO_APPLY, NEXUS_SHADOW_MODE


class UpgradePipeline:
    """Bundles P0-P3 upgrade services for runtime integration."""

    def __init__(self, runtime_store, learning_feedback=None):
        self.runtime_store = runtime_store
        self.learning_feedback = learning_feedback
        self.event_registry = EventRegistry()
        self.universe_filter = UniverseFilterService()
        self.decision_trace = DecisionTraceStore(runtime_store)
        self.learning_reviews = LearningReviewQueue(runtime_store)
        self.execution_governor = ExecutionGovernor()
        self.trade_proposals = TradeProposalService(runtime_store)
        self.shadow_mode = ShadowModeService(runtime_store)
        self.strategy_versions = StrategyVersionRegistry(runtime_store)
        self.execution_quality = ExecutionQualityMonitor(runtime_store)
        self._event_registry_snapshot = {}

    def on_news(self, normalized_events):
        self._event_registry_snapshot = self.event_registry.register_batch(normalized_events)
        return self._event_registry_snapshot

    def resolve_radar_symbols(self, futures_client):
        return self.universe_filter.resolve_scan_symbols(futures_client)

    def begin_tick(self):
        self.trade_proposals.begin_tick()

    def govern_validation(self, proposal, validation, portfolio_status=None, learning_guidance=None):
        governed = self.execution_governor.evaluate(
            proposal,
            validation,
            portfolio_status=portfolio_status,
            learning_guidance=learning_guidance,
        )
        self.trade_proposals.create_from_request(proposal, proposer=proposal.get("proposer", "fleet_engine"))
        trace = self.decision_trace.record(
            proposal,
            governed,
            market_context={"market_regime": proposal.get("market_regime")},
            proposer=proposal.get("proposer", "fleet_engine"),
            trace_id=governed.get("trace_id"),
        )
        if self.shadow_mode.should_shadow():
            self.shadow_mode.record_shadow_trade(proposal, governed)
        return governed, trace

    def on_trade_result(self, result, recommendation=None):
        if recommendation:
            self.learning_reviews.enqueue_from_recommendation(recommendation, source="trade_loss")
        self.learning_reviews.process_pending()

    def on_llm_reflection(self, llm_reflection):
        if isinstance(llm_reflection, dict):
            self.learning_reviews.enqueue_from_llm_reflection(llm_reflection)

    def build_status(self, walk_forward_status=None, learning_status=None, recent_trades=None):
        learning_status = learning_status or {}
        return {
            "event_registry": self._event_registry_snapshot or self.event_registry.snapshot(),
            "learning_reviews": self.learning_reviews.status_snapshot(recent_trades=recent_trades),
            "trade_proposals": self.trade_proposals.recent(limit=15),
            "decision_traces": self.runtime_store.recent_decision_traces(limit=20),
            "shadow_mode": self.shadow_mode.snapshot(),
            "strategy_versions": self.strategy_versions.snapshot(),
            "execution_quality": self.execution_quality.evaluate(
                recent_trades=recent_trades,
            ),
            "walk_forward": walk_forward_status or {},
            "rotation": self.strategy_versions.suggest_rotation(walk_forward_status, learning_status),
            "radar_universe_size": len(self.universe_filter.resolve_scan_symbols()),
        }
