from backend.analytics.setup_performance_tracker import SetupPerformanceTracker
from config.growth_mode_config import BOLD_MIN_QUALITY, BOLD_TESTNET_ENABLED
from backend.decision.entry_quality_filter import EntryQualityFilter
from backend.decision.fleet_score_engine import FleetScoreEngine
from backend.decision.setup_classifier import SetupClassifier
from backend.decision.signal_memory_engine import SignalMemoryEngine


class DecisionQualityValidationEngine:
    def __init__(
        self,
        setup_tracker=None,
        setup_classifier=None,
        entry_quality_filter=None,
        fleet_score_engine=None,
        signal_memory_engine=None,
    ):
        self.setup_tracker = setup_tracker or SetupPerformanceTracker()
        self.setup_classifier = setup_classifier or SetupClassifier()
        self.entry_quality_filter = entry_quality_filter or EntryQualityFilter()
        self.fleet_score_engine = fleet_score_engine or FleetScoreEngine()
        self.signal_memory_engine = signal_memory_engine or SignalMemoryEngine()

    def evaluate(self, proposal, market_context=None, growth_context=None):
        proposal = dict(proposal or {})
        market_context = market_context or {}
        growth_context = growth_context or {}
        growth_directives = dict(growth_context.get("growth_directives") or {})

        if growth_directives.get("block_new_entries"):
            return {
                "stage": "decision_quality",
                "approved": False,
                "score": 0.0,
                "reason": growth_directives.get("block_reason") or "growth_guard_block",
                "setup_type": "",
                "quality_score": 0.0,
                "fleet_score": 0.0,
            }

        signal = dict(growth_context.get("signal") or {})
        meeting_notes = dict(growth_context.get("meeting_notes") or {})
        news_items = list(growth_context.get("news_items") or [])
        whale_status = dict(growth_context.get("whale_status") or {})
        funding_status = dict(growth_context.get("funding_status") or {})
        trades = list(growth_context.get("trades") or [])
        capital_snapshot = dict(growth_context.get("capital_snapshot") or {})
        loan_snapshot = dict(growth_context.get("loan_snapshot") or {})
        audits = list(growth_context.get("audits") or [])

        fleet = str(proposal.get("fleet") or "").upper()
        side = str(proposal.get("side") or "BUY").upper()
        regime = str(market_context.get("market_regime") or "normal")
        adjusted_confidence = float(proposal.get("adjusted_confidence", proposal.get("raw_confidence", 0.0)) or 0.0)

        setup_type = self.setup_classifier.classify(
            fleet,
            signal,
            market_context,
            news_items,
            whale_status,
            funding_status,
        )
        memory_check = self.signal_memory_engine.inspect(
            fleet,
            side,
            proposal.get("strategy_key") or f"{fleet.lower()}_adaptive_strategy",
            regime,
            setup_type,
            market_context,
        )
        if memory_check.get("blocked"):
            return {
                "stage": "decision_quality",
                "approved": False,
                "score": 0.05,
                "reason": memory_check.get("reject_reason") or "signal_memory_block",
                "setup_type": setup_type,
                "quality_score": 0.0,
                "fleet_score": 0.0,
                "memory_check": memory_check,
            }

        fleet_metrics = self.fleet_score_engine.evaluate(
            fleet,
            trades,
            capital_snapshot,
            loan_snapshot,
            market_context,
            audits,
            meeting_notes=meeting_notes,
        )
        quality = self.entry_quality_filter.evaluate(
            fleet,
            side,
            market_context,
            signal,
            setup_type,
            adjusted_confidence * float(memory_check.get("penalty_factor", 1.0) or 1.0),
            fleet_metrics,
            memory_check,
            meeting_notes=meeting_notes,
        )
        setup_stats = self.setup_tracker.get_stats(fleet, setup_type, regime)

        min_quality = float(growth_directives.get("min_quality_score", 0.65) or 0.65)
        if BOLD_TESTNET_ENABLED:
            min_quality = min(min_quality, BOLD_MIN_QUALITY)
        approved = bool(quality.get("approved")) and fleet_metrics.get("state") not in {"PAUSED"}
        reason = quality.get("reject_reason") or "decision_quality_ok"
        score = round(
            (
                float(quality.get("quality_score", 0.0) or 0.0) * 0.55
                + float(fleet_metrics.get("fleet_score", 0.0) or 0.0) / 100.0 * 0.45
            ),
            4,
        )

        if float(quality.get("quality_score", 0.0) or 0.0) < min_quality:
            approved = False
            reason = "quality_below_growth_threshold"
        if setup_stats.get("blocked"):
            approved = False
            reason = "setup_expectancy_too_low"
        if fleet_metrics.get("state") == "PAUSED":
            approved = False
            reason = "fleet_score_paused"

        return {
            "stage": "decision_quality",
            "approved": approved,
            "score": round(max(0.0, min(1.0, score)), 4),
            "reason": reason,
            "setup_type": setup_type,
            "quality_score": quality.get("quality_score", 0.0),
            "fleet_score": fleet_metrics.get("fleet_score", 0.0),
            "fleet_state": fleet_metrics.get("state"),
            "position_mode": quality.get("position_mode"),
            "setup_stats": setup_stats,
            "memory_check": memory_check,
            "quality_reasons": quality.get("reasons", []),
        }
