import os
import threading
import time
import hashlib
import re
from datetime import datetime, timedelta
from uuid import uuid4
from pathlib import Path

from backend.core.env_loader import load_env_file
from backend.core.time_utils import nexus_now
from backend.core.event_bus import EventBus
from backend.core.system_state_manager import SystemStateManager
from backend.agents import AdvisoryServices
from backend.llm import LLMGateway
from backend.config.capital_config import (
    FLEET_ACTIVE_CAPITAL,
    FLEET_ALLOCATION_WEIGHTS,
    FUTURES_RESERVE_RATIO,
    HQ_SPOT_SYMBOLS,
    RADAR_ALLOCATION_WEIGHT,
)
from backend.fleets.base_strategy_engine import BaseFleetStrategyEngine
from backend.fleets.signal_fusion_engine import SignalFusionEngine
from backend.monitoring.trading_health_service import TradingHealthService
from backend.monitoring.execution_quality_monitor import ExecutionQualityMonitor
from backend.monitoring.maturity_radar_service import MaturityRadarService
from backend.monitoring.ops_health_service import OpsHealthService
from backend.governance.ai_trade_proposer import AiTradeProposer
from backend.governance.ai_position_manager import AiPositionManager
from backend.learning.strategy_evolution_service import StrategyEvolutionService
from backend.analytics.monthly_revenue_tracker import MonthlyRevenueTracker
from backend.analytics.revenue_plan_service import RevenuePlanService
from backend.monitoring.decision_funnel_service import DecisionFunnelService
from backend.monitoring.kill_switch_service import KillSwitchService
from backend.autonomy.rule_signal_bridge import RuleSignalBridge
from backend.autonomy.strategy_proposal_hub import StrategyProposalHub
from backend.risk.monthly_drawdown_guard import MonthlyDrawdownGuard
from backend.trading.radar_dispatch_service import RadarDispatchService
from config.revenue_target_config import (
    EXPLORATION_MIN_QUALITY,
    FUTURES_DEPLOY_FRACTION,
    FUTURES_ONLY_TRADING,
    REVENUE_GROWTH_MODE,
)
from backend.market.market_price_feed_service import MarketPriceFeedService
from backend.market.market_context_service import MarketContextService
from backend.market.market_intel_cache import MarketIntelCache
from backend.market.regime_classifier_service import RegimeClassifierService
from backend.learning.dynamic_blocklist import DynamicBlocklist
from backend.learning.post_trade_postmortem_engine import PostTradePostMortemEngine
from backend.risk.confidence_sizing_pipeline import ConfidenceSizingPipeline
from backend.trading.market_neutral_funding_engine import MarketNeutralFundingEngine
from config.regime_config import REGIME_REFRESH_SECONDS
from backend.market.radar_market_scan_service import RadarMarketScanService
from backend.market.spot_truth_service import SpotTruthService
from backend.market.truth_layer_guard import TruthLayerGuard
from backend.news.news_analysis_engine import NewsAnalysisEngine
from backend.news.event_normalization_service import EventNormalizationService
from backend.news.news_ingestion_service import NewsIngestionService
from backend.learning.feedback_loop import LearningFeedbackLoop
from backend.learning.liquidation_tracker import LiquidationTracker
from backend.governance.upgrade_pipeline import UpgradePipeline
from backend.governance.radar_llm_proposal_bridge import RadarLlmProposalBridge
from backend.analytics.daily_ops_reporter import should_broadcast, format_report as format_daily_ops_report
from config.daily_report_config import DAILY_REPORT_ENABLED
from config.live_sync_config import (
    EXCHANGE_REFRESH_MIN_SECONDS,
    GLOBAL_INDEX_REFRESH_SECONDS,
    LIVE_REFRESH_RADAR,
    NEWS_REFRESH_SECONDS,
)
from backend.risk.risk_control_engine import RiskControlEngine
from backend.portfolio import PortfolioGovernor
from backend.services.runtime_store import runtime_store
from backend.trading.binance_account_sync_service import BinanceAccountSyncService
from backend.trading.binance_execution_router import BinanceExecutionRouter
from backend.trading.binance_futures_testnet_client import BinanceFuturesTestnetClient
from backend.trading.binance_order_sync_service import BinanceOrderSyncService
from backend.trading.binance_position_sync_service import BinancePositionSyncService
from backend.trading.binance_spot_testnet_client import BinanceSpotTestnetClient
from backend.trading.paper_order_execution_engine import PaperOrderExecutionEngine
from backend.trading.paper_position_manager import PaperPositionManager
from backend.trading.pnl_tracker import PnlTracker
from backend.trading.trade_validation_pipeline import TradeValidationPipeline
from backend.trading.exchange_capital_view import (
    build_account_binding_status,
    build_ui_capital,
    futures_equity_from_account,
    resolve_futures_display_unrealized,
)
from backend.trading.decision_quality_engine import DecisionQualityValidationEngine
from backend.risk.capital_growth_guard import CapitalGrowthGuard
from backend.wallet.compound_capital_service import CompoundCapitalService
from backend.decision.meeting_notes_resolver import resolve_meeting_notes
from backend.analytics.setup_performance_tracker import SetupPerformanceTracker
from backend.trading.fee_churn_guard import get_fee_churn_guard
from backend.analytics.research_gate_service import ResearchGateService
from backend.analytics.walk_forward_evaluator import WalkForwardEvaluator
from config.fleet_routing_config import fleet_for_exchange_position
from config.ai_trading_config import AI_LED_PRIMARY_MODE, AI_LED_TRADING_ENABLED
from config.runtime_config import always_on_trading_enabled, tick_seconds
from backend.trading.trading_mode import get_trading_mode
from backend.coordination.station_chat_log import StationChatLog
from backend.coordination.station_dialogue_service import StationDialogueService
from backend.fleets.meeting_memory_broadcaster import MeetingMemoryBroadcaster
from backend.wallet.internal_capital_ledger import InternalCapitalLedger
from backend.wallet.loan_manager import LoanManager
from config.truth_layer_config import (
    HQ_SPOT_ALLOWED_ASSETS,
    HQ_SPOT_TRUTH_MODE,
    HQ_SPOT_TRUTH_STABLE_ASSETS,
    HQ_SPOT_VISIBLE_HOLDINGS,
)

load_env_file(Path(__file__).resolve().parents[2] / ".env")

FLEETS = ["BTC", "ETH", "SOL", "PEPE"]
RADAR_ALT_TARGETS = ("SOL", "PEPE")
STABLE_ASSETS = {"USDT", "USDC", "FDUSD", "TUSD", "USDP", "DAI", "USD1", "RLUSD", "USDE", "BFUSD", "XUSD"}


def _now():
    return nexus_now().strftime("%Y-%m-%d %H:%M:%S")


def _short_fingerprint(parts):
    payload = "|".join(str(part) for part in parts if part is not None)
    if not payload:
        return ""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _safe_float(value):
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _clean_display_text(text, fallback=""):
    value = str(text or "").strip()
    if not value:
        return fallback
    value = value.replace("\ufffd", "")
    if re.fullmatch(r"[?？\s]+", value):
        return fallback
    value = re.sub(r"[?？]{3,}", fallback or "", value)
    return value.strip() or fallback


def _sanitize_for_display(value):
    if isinstance(value, dict):
        return {key: _sanitize_for_display(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_display(item) for item in value]
    if isinstance(value, str):
        return _clean_display_text(value, value.replace("?", "").replace("？", "").strip())
    return value


def _meeting_focus_defaults(kind):
    if kind == "scheduled":
        return [
            "觀察主流幣是否維持既有方向與成交量結構。",
            "留意風險事件是否開始擴散到其他資產。",
            "若資料互相衝突，優先等待下一輪確認訊號。",
        ]
    return [
        "先確認事件是否已被市場快速定價。",
        "檢查主流幣與高波動標的是否出現衝突訊號。",
        "在結論更新前避免擴大風險曝險。",
    ]


FIXED_MEETING_SLOTS = ("00:00", "06:00", "12:00", "18:00")


class NexusRuntime:
    def __init__(self):
        self.event_bus = EventBus()
        self.state_manager = SystemStateManager()
        self.trading_mode = get_trading_mode()
        self.ledger = InternalCapitalLedger()
        self.loan_manager = LoanManager(self.ledger)
        self.position_manager = PaperPositionManager()
        self.execution_engine = PaperOrderExecutionEngine(self.ledger, self.position_manager, self.event_bus)
        self.pnl_tracker = PnlTracker(self.ledger, self.position_manager)
        self.risk_engine = RiskControlEngine(self.ledger, self.pnl_tracker)
        self.learning_feedback = LearningFeedbackLoop(runtime_store)
        self.liquidation_tracker = LiquidationTracker()
        for item in runtime_store.recent_trade_results(limit=80):
            symbol = str(item.get("symbol") or "").upper()
            if symbol:
                self.liquidation_tracker._watch_symbol(symbol)
        self.signal_fusion = SignalFusionEngine()
        self.price_feed = MarketPriceFeedService()
        self.trading_health = TradingHealthService()
        # Execution-quality metrics are computed from recent trades + validation events.
        # Keep it as a lightweight monitor so tick() can always proceed.
        self.execution_quality_monitor = ExecutionQualityMonitor(runtime_store)
        self.maturity_radar = MaturityRadarService()
        self.ops_health = OpsHealthService()
        self.strategy_evolution = StrategyEvolutionService()
        self.monthly_revenue = MonthlyRevenueTracker()
        self.revenue_plan = RevenuePlanService()
        self.decision_funnel = DecisionFunnelService()
        self.kill_switch = KillSwitchService()
        self.rule_signal_bridge = RuleSignalBridge()
        self.strategy_proposal_hub = StrategyProposalHub()
        self.monthly_drawdown_guard = MonthlyDrawdownGuard()
        self.ai_position_manager = AiPositionManager()
        self._force_immediate_tick = False
        self._last_tick_error = None
        self._startup_exit_check = {}
        self._sandbox_startup_done = False
        self._last_ops_status = None
        self.news_ingestion = NewsIngestionService(refresh_seconds=NEWS_REFRESH_SECONDS)
        self.news_analysis = NewsAnalysisEngine()
        self.meeting_broadcaster = MeetingMemoryBroadcaster()
        self.llm_gateway = LLMGateway()
        self.advisory_services = AdvisoryServices()
        self.station_chat_log = StationChatLog(runtime_store)
        self.station_dialogue = StationDialogueService(self.station_chat_log, llm_gateway=self.llm_gateway)
        self.spot_client = BinanceSpotTestnetClient()
        self.futures_client = BinanceFuturesTestnetClient()
        self.market_context_service = MarketContextService(self.spot_client, self.futures_client)
        self.external_market_intel = MarketIntelCache()
        self.dynamic_blocklist = DynamicBlocklist()
        self.regime_classifier = RegimeClassifierService(llm_gateway=self.llm_gateway)
        self.post_trade_postmortem = PostTradePostMortemEngine(
            llm_gateway=self.llm_gateway,
            blocklist=self.dynamic_blocklist,
        )
        self.confidence_sizing_pipeline = ConfidenceSizingPipeline(blocklist=self.dynamic_blocklist)
        self.market_neutral_engine = MarketNeutralFundingEngine()
        self._last_regime_refresh_at = 0.0
        self.radar_market_scan_service = RadarMarketScanService(self.futures_client, self.market_context_service)
        self.spot_truth_service = SpotTruthService(
            truth_mode=HQ_SPOT_TRUTH_MODE,
            truth_stable_assets=HQ_SPOT_TRUTH_STABLE_ASSETS,
            visible_holdings=HQ_SPOT_VISIBLE_HOLDINGS,
            allowed_assets=HQ_SPOT_ALLOWED_ASSETS,
        )
        self.truth_layer_guard = TruthLayerGuard()
        self.portfolio_governor = PortfolioGovernor()
        self.account_sync = BinanceAccountSyncService(self.spot_client, self.futures_client)
        self.order_sync = BinanceOrderSyncService(self.spot_client, self.futures_client)
        self.position_sync = BinancePositionSyncService(self.futures_client)
        self.setup_performance_tracker = SetupPerformanceTracker()
        decision_quality_engine = DecisionQualityValidationEngine(setup_tracker=self.setup_performance_tracker)
        self.validation_pipeline = TradeValidationPipeline(
            runtime_store,
            self.learning_feedback,
            decision_quality_engine=decision_quality_engine,
            futures_client=self.futures_client,
        )
        self.capital_growth_guard = CapitalGrowthGuard()
        self.compound_capital = CompoundCapitalService()
        self.walk_forward_evaluator = WalkForwardEvaluator()
        self.research_gate_service = ResearchGateService(
            futures_client=self.futures_client,
            walk_forward_evaluator=self.walk_forward_evaluator,
        )
        self._research_gate_status = {}
        self.radar_dispatch = RadarDispatchService()
        self.fee_churn_guard = get_fee_churn_guard()
        self.radar_llm_bridge = RadarLlmProposalBridge(self.radar_dispatch, self.llm_gateway)
        self._radar_llm_proposals = []
        self._last_daily_report_key = None
        self.growth_status = {}
        self.signal_memory_engine = decision_quality_engine.signal_memory_engine
        self.event_normalizer = EventNormalizationService()
        self.upgrade_pipeline = UpgradePipeline(runtime_store, learning_feedback=self.learning_feedback)
        self.ai_trade_proposer = AiTradeProposer(
            llm_gateway=self.llm_gateway,
            trade_proposal_service=self.upgrade_pipeline.trade_proposals,
        )
        self._meeting_execution_directives = {"blocked_fleets": [], "forbidden_actions": []}
        self.strategy_engines = {
            fleet: BaseFleetStrategyEngine(
                fleet,
                self.execution_engine,
                self.position_manager,
                self.risk_engine,
                self.event_bus,
                learning_feedback=self.learning_feedback,
            )
            for fleet in FLEETS
        }
        spot_engine = getattr(self.execution_engine, "spot", None)
        futures_engine = getattr(self.execution_engine, "futures", None)
        self.execution_router = None
        if spot_engine and futures_engine:
            self.execution_router = BinanceExecutionRouter(
                spot_engine=spot_engine,
                futures_engine=futures_engine,
                risk_engine=self.risk_engine,
                dynamic_leverage_engine=self.risk_engine.dynamic_leverage_engine,
                trading_mode=self.trading_mode,
            )
        self.latest_prices = {}
        self.market_overview = self.price_feed.get_market_overview()
        self.market_context = {}
        self.truth_layer_status = {}
        self._last_account_sync_status = {}
        self.latest_news = []
        self.normalized_events = []
        self.agent_advisory = {}
        self.llm_status = self.llm_gateway.status_snapshot()
        self.alerts = []
        self.whale_state = {}
        self.radar_state = {}
        self.radar_scan = {}
        self.portfolio_status = {}
        self.station_learning_exchange = {}
        self.meetings = []
        self.station_briefings = {}
        self.station_chats = self.station_chat_log.recent_grouped()
        self.station_briefings = self.meeting_broadcaster.load_all()
        self.hq_spot_orders = []
        self.hq_spot_trades = []
        self.futures_live_orders = []
        self.futures_live_trades = []
        self.hq_spot_last_action = {symbol: 0.0 for symbol in HQ_SPOT_SYMBOLS}
        self._bootstrapped = False
        self._previous_prices = {}
        self._thread = None
        self._exchange_refresh_lock = threading.RLock()
        self._last_exchange_refresh_at = 0.0
        self._last_news_sync_at = 0.0
        self._live_sync_status = {}
        self._stop = threading.Event()
        self._manual_pause = False
        self._pause_reason = None
        self._last_major_news_id = None
        self._news_pause_active = False
        self._news_pause_until = 0.0
        self._lock = threading.RLock()
        self._last_binance_sync = {
            "spot": {},
            "futures": {},
            "last_sync_time": 0,
            "sync_status": "idle",
            "errors": [],
        }
        self.event_bus.subscribe("*", self._on_event)
        self._hydrate_from_store()
        self._validation_prune_counter = 0

    def _hydrate_from_store(self):
        snapshot = runtime_store.load_snapshot()
        if not snapshot:
            return
        try:
            self.ledger.ledger_entries = []
            self.position_manager.positions = {}
            self.execution_engine.orders = []
            self.execution_engine.trades = []
            self.hq_spot_orders = []
            self.hq_spot_trades = []
            self.futures_live_orders = []
            self.futures_live_trades = []
            self.latest_prices = {}
            self.latest_news = list(snapshot.get("news", []))
            self.meetings = [self._normalize_meeting_record(item) for item in list(snapshot.get("meetings", []))]
            self.alerts = list(snapshot.get("alerts", []))[:80]
            stored_overview = snapshot.get("market_overview") or {}
            if isinstance(stored_overview, dict) and stored_overview.get("indices"):
                self.market_overview = stored_overview
                self.price_feed.seed_index_cache(stored_overview.get("indices") or {})
            self.station_briefings = snapshot.get("station_briefings", {}) or self.station_briefings
            analytics = snapshot.get("analytics", {})
            self._previous_prices = dict(analytics.get("previous_prices", {}))
            self._manual_pause = False
            self._pause_reason = None
        except Exception as exc:
            print(f"[nexus_runtime] hydration skipped: {exc}")

    def _normalize_meeting_record(self, meeting):
        record = _sanitize_for_display(dict(meeting or {}))
        meeting_type = str(record.get("type") or "")
        conclusion = dict(record.get("conclusion") or {})
        if meeting_type == "SCHEDULED_ROUND_TABLE":
            time_value = str(record.get("time") or "")
            slot = str(record.get("slot") or "") or (time_value[11:16] if len(time_value) >= 16 else "")
            record["slot"] = slot
            record["summary"] = f"{slot} 固定圓桌會議" if slot else _clean_display_text(record.get("summary"), "固定圓桌會議")
            summary_text = _clean_display_text(conclusion.get("summary"), "")
            if not summary_text or (slot and summary_text.count(slot) > 1) or "固定圓桌會議完成" not in summary_text:
                summary_text = f"{slot} 固定圓桌會議已完成，會議重點請參考下方摘要。" if slot else "固定圓桌會議已完成，會議重點請參考下方摘要。"
            focus = [item for item in (conclusion.get("next_6h_focus") or []) if str(item or "").strip()]
            conclusion["summary"] = summary_text
            conclusion["next_6h_focus"] = (focus[:3] if len(focus) >= 3 else _meeting_focus_defaults("scheduled"))
        elif meeting_type == "EMERGENCY_ROUND_TABLE":
            record["summary"] = _clean_display_text(record.get("summary"), "緊急圓桌會議")
            summary_text = _clean_display_text(conclusion.get("summary"), "")
            if not summary_text:
                summary_text = f"緊急圓桌會議已完成：{record['summary']}。"
            focus = [item for item in (conclusion.get("next_6h_focus") or []) if str(item or "").strip()]
            conclusion["summary"] = summary_text
            conclusion["next_6h_focus"] = (focus[:3] if len(focus) >= 3 else _meeting_focus_defaults("emergency"))
        if "fleet_restrictions" not in conclusion or not conclusion.get("fleet_restrictions"):
            conclusion["fleet_restrictions"] = dict(getattr(self, "portfolio_status", {}).get("fleet_restrictions", {}))
        if "capital_adjustments" not in conclusion or not conclusion.get("capital_adjustments"):
            conclusion["capital_adjustments"] = dict(getattr(self, "portfolio_status", {}).get("capital_adjustments", {}))
        conclusion["reserve_action"] = conclusion.get("reserve_action") or getattr(self, "portfolio_status", {}).get("reserve_action", "hold")
        if not conclusion.get("station_shares"):
            conclusion["station_shares"] = list(getattr(self, "station_learning_exchange", {}).get("station_shares", []) or [])
        if not conclusion.get("cross_station_lessons"):
            conclusion["cross_station_lessons"] = list(getattr(self, "station_learning_exchange", {}).get("cross_station_lessons", []) or [])
        if not conclusion.get("opportunity_board"):
            conclusion["opportunity_board"] = list(getattr(self, "station_learning_exchange", {}).get("opportunity_board", []) or [])
        if not conclusion.get("hedge_recommendations"):
            conclusion["hedge_recommendations"] = list(getattr(self, "portfolio_status", {}).get("hedge_recommendations", []) or [])
        record["conclusion"] = conclusion
        return record

    def _build_scheduled_roundtable(self, meeting_id, slot, latest_news):
        summary = _clean_display_text(
            latest_news.get("summary_zh") or latest_news.get("summary"),
            "目前沒有重大新增事件，維持原有觀察節奏。",
        )
        date_part = meeting_id.split("_")[1] if "_" in meeting_id else nexus_now().strftime("%Y-%m-%d")
        portfolio_status = dict(self.portfolio_status or {})
        station_learning_exchange = dict(self.station_learning_exchange or {})
        fleet_status = dict((self.state_manager.snapshot() or {}).get("fleet_status", {}))
        trading_fleets = [
            fleet
            for fleet in FLEETS
            if str(fleet_status.get(fleet, "")).upper() in {"TRADING", "ACTIVE", "BUSY"}
        ]
        live_line = f"更新 {nexus_now().strftime('%Y-%m-%d %H:%M')} Taipei"
        if trading_fleets:
            live_line += f"，交易中：{', '.join(trading_fleets)}"
        return {
            "meeting_id": meeting_id,
            "slot": slot,
            "time": f"{date_part} {slot}:00",
            "created_at": _now(),
            "updated_at": _now(),
            "type": "SCHEDULED_ROUND_TABLE",
            "summary": f"{slot} 固定圓桌會議",
            "participants": [{"station": station, "speaker": station} for station in ["HQ", "NEWS", "RADAR", *FLEETS]],
            "conclusion": {
                "summary": f"{slot} 固定圓桌會議完成（{live_line}）。重點摘要：{summary}",
                "next_6h_focus": _meeting_focus_defaults("scheduled"),
                "fleet_restrictions": dict(portfolio_status.get("fleet_restrictions", {})),
                "capital_adjustments": dict(portfolio_status.get("capital_adjustments", {})),
                "reserve_action": portfolio_status.get("reserve_action", "hold"),
                "station_shares": list(station_learning_exchange.get("station_shares", []) or []),
                "cross_station_lessons": list(station_learning_exchange.get("cross_station_lessons", []) or []),
                "opportunity_board": list(station_learning_exchange.get("opportunity_board", []) or []),
                "hedge_recommendations": list(portfolio_status.get("hedge_recommendations", []) or []),
            },
        }

    def _on_event(self, event):
        event_type = event["type"]
        payload = event.get("payload", {})
        if event_type in {"trade_opened", "trade_closed"}:
            trade = payload.get("trade") or payload.get("order") or {}
            fleet = str(trade.get("fleet") or "HQ").upper()
            pnl = float(trade.get("pnl", 0.0) or 0.0)
            if event_type == "trade_closed" and pnl < 0:
                self._broadcast_loss_reflection(trade, fleet, pnl)
            else:
                runtime_store.append_station_chat(
                    {
                        "timestamp": _now(),
                        "station": fleet,
                        "speaker": "SYSTEM",
                        "message": f"{event_type}: {trade.get('symbol', '')} pnl={pnl:.4f}",
                        "source": "runtime",
                        "importance": "INFO",
                    }
                )
            self.station_chats = self.station_chat_log.recent_grouped()

    def _broadcast_loss_reflection(self, trade, fleet, pnl):
        learning = self._build_learning_status()
        recs = learning.get("latest_recommendations", []) or []
        rec_text = recs[0].get("recommendation") if recs and isinstance(recs[0], dict) else ""
        if not rec_text and recs:
            rec_text = str(recs[0])
        symbol = trade.get("symbol", fleet)
        reason = trade.get("reason") or trade.get("exit_reason") or "unknown"
        msg = (
            f"虧損平倉 {symbol}：{pnl:.2f}U。原因：{reason}。"
            f"{' 學習建議：' + str(rec_text)[:200] if rec_text else ' 已寫入學習紀錄，風控將收緊。'}"
        )
        for channel in ("WORLD", fleet if fleet in {"BTC", "ETH", "SOL", "PEPE", "RADAR"} else "HQ", "RISK"):
            self.station_chat_log.add(channel, "風控反思", msg, source="虧損反思", importance="WARNING")
        self.station_chats = self.station_chat_log.recent_grouped()

    def refresh_live_exchange_state(self, force=False, min_interval_sec=None):
        """Refresh Binance, prices, global news/indices, and roundtables (web-safe, throttled)."""
        if min_interval_sec is None:
            min_interval_sec = EXCHANGE_REFRESH_MIN_SECONDS
        now = time.time()
        if not force and (now - float(self._last_exchange_refresh_at or 0.0)) < min_interval_sec:
            return False
        if not (self.spot_client.is_configured() or self.futures_client.is_configured()):
            self._sync_live_market_and_world_state(force=force, writer="live_refresh")
            return True
        with self._exchange_refresh_lock:
            now = time.time()
            if not force and (now - float(self._last_exchange_refresh_at or 0.0)) < min_interval_sec:
                return False
            prices = self.price_feed.get_prices(self.futures_client)
            self.latest_prices = dict(prices)
            if self.spot_client.is_configured():
                self._last_spot_account = self._sync_spot_account(prices)
            if self.futures_client.is_configured():
                futures_account = self._sync_futures_account(prices)
                self._last_futures_account = futures_account
                self._sync_futures_activity()
                self._reconcile_liquidation_losses(futures_account)
                self._apply_live_capital_plan(futures_account)
                self._synchronize_live_futures_state(futures_account)
                futures_total = futures_equity_from_account(futures_account)
                self.growth_status = self.capital_growth_guard.evaluate(futures_total)
            self._sync_live_market_and_world_state(force=force, writer="exchange_refresh")
            self._last_binance_sync["last_sync_time"] = int(time.time() * 1000)
            self._last_exchange_refresh_at = time.time()
            runtime_store.save_snapshot(
                self.snapshot(),
                worker_pid=os.getpid(),
                worker_status="ONLINE",
                writer="exchange_refresh",
                single_instance=False,
            )
            return True

    def _sync_live_market_and_world_state(self, force=False, writer="live_refresh"):
        prices = self.latest_prices or self.price_feed.get_prices(self.futures_client)
        self.latest_prices = dict(prices)
        self.market_overview = self.price_feed.get_market_overview(
            max_age_seconds=GLOBAL_INDEX_REFRESH_SECONDS,
            force=force,
        )
        symbol_prices = self._build_symbol_prices(prices)
        self.position_manager.update_unrealized(prices, symbol_prices=symbol_prices)
        if force or self._news_refresh_due():
            self._sync_news()
        else:
            self._maybe_sync_news_for_meetings(min_interval_sec=NEWS_REFRESH_SECONDS)
        self._ensure_fixed_roundtables()
        if LIVE_REFRESH_RADAR and self.futures_client.is_configured():
            self.radar_scan = self.radar_market_scan_service.scan()
            self.radar_state = dict(self.radar_scan or {})
            self.whale_state = {
                "generated_at": self.radar_scan.get("generated_at", _now()),
                "watch": list(self.radar_scan.get("whale_watch", []) or []),
                "candidates": list(self.radar_scan.get("candidates", []) or []),
            }
        price_sources = {fleet: (data or {}).get("source") for fleet, data in prices.items() if isinstance(data, dict)}
        self._live_sync_status = {
            "updated_at": _now(),
            "updated_at_ms": int(time.time() * 1000),
            "writer": writer,
            "binance_sync_ms": int(self._last_binance_sync.get("last_sync_time") or 0),
            "news_sync_at": float(self._last_news_sync_at or 0.0),
            "news_count": len(self.latest_news or []),
            "event_count": len(self.normalized_events or []),
            "price_sources": price_sources,
            "index_source": (self.market_overview or {}).get("source"),
            "radar_enabled": bool(LIVE_REFRESH_RADAR and self.futures_client.is_configured()),
        }

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        try:
            runtime_store.prune_trade_validation_events(keep_limit=60)
        except Exception as exc:
            print(f"[nexus_runtime] validation prune skipped: {exc}")
        self._ensure_trading_resumed(force=True)
        self.account_sync.start()
        # On startup, immediately refresh exchange state and evaluate exits for any
        # existing live positions (do not wait for the first scheduled tick).
        try:
            self.refresh_live_exchange_state(force=True)
        except Exception as exc:
            print(f"[nexus_runtime] startup exchange refresh skipped: {exc}")
        if self.futures_client.is_configured():
            self._refresh_futures_trading_access("ETHUSDT")
        try:
            self._evaluate_startup_position_exits()
        except Exception as exc:
            print(f"[nexus_runtime] startup position exit check skipped: {exc}")
        self._force_immediate_tick = True
        if AI_LED_TRADING_ENABLED and self.llm_gateway.enabled():
            try:
                self.llm_gateway.warmup()
            except Exception as exc:
                print(f"[nexus_runtime] llm warmup skipped: {exc}")
        try:
            self.external_market_intel.start(bootstrap=True)
        except Exception as exc:
            print(f"[nexus_runtime] market_intel_cache start skipped: {exc}")
        try:
            self.upgrade_pipeline.start_background_services()
        except Exception as exc:
            print(f"[nexus_runtime] upgrade_pipeline background start skipped: {exc}")
        try:
            self.regime_classifier.start(bootstrap=True)
        except Exception as exc:
            print(f"[nexus_runtime] regime_classifier start skipped: {exc}")
        self._thread = threading.Thread(target=self._loop, daemon=True, name="nexus-runtime")
        self._thread.start()

    def _evaluate_startup_position_exits(self):
        """Evaluate R-exit on existing Binance positions immediately after startup."""
        result = {
            "ran_at": _now(),
            "positions_checked": 0,
            "exits_triggered": 0,
            "errors": [],
            "details": [],
        }
        if not self.futures_client.is_configured():
            result["skipped"] = "futures_not_configured"
            self._startup_exit_check = result
            return result

        prices = self.price_feed.get_prices(self.futures_client)
        self.latest_prices = dict(prices)
        futures_account = dict(getattr(self, "_last_futures_account", None) or {})
        if not futures_account.get("positions"):
            futures_account = self._sync_futures_account(prices)
            self._last_futures_account = futures_account
        sync_error = str(futures_account.get("sync_error") or "")
        if sync_error:
            result["errors"].append(sync_error)
        self._synchronize_live_futures_state(futures_account)
        symbol_prices = self._build_symbol_prices(prices)
        self.position_manager.update_unrealized(prices, symbol_prices=symbol_prices)

        from config.exit_config import RISK_PCT, STOP_R

        live_rows = list(futures_account.get("positions") or [])
        if not live_rows:
            self._startup_exit_check = result
            return result

        for live in live_rows:
            fleet = str(live.get("fleet") or "RADAR").upper()
            symbol = str(live.get("symbol") or "").upper()
            if not symbol:
                continue
            result["positions_checked"] += 1
            positions = self.position_manager.get_by_fleet(fleet)
            position = positions[0] if positions else {
                "id": f"live_{fleet}_{symbol}",
                "fleet": fleet,
                "symbol": symbol,
                "side": live.get("side", "BUY"),
                "quantity": live.get("quantity", 0.0),
                "margin": live.get("margin", 0.0),
                "unrealized_pnl": live.get("unrealized_pnl", 0.0),
                "mark_price": live.get("mark_price", 0.0),
                "position_side": live.get("position_side", "BOTH"),
            }
            current = float(
                symbol_prices.get(symbol)
                or (prices.get(fleet) or {}).get("price", 0.0)
                or position.get("mark_price", 0.0)
                or live.get("mark_price", 0.0)
                or 0.0
            )
            margin = float(position.get("margin", 0.0) or live.get("margin", 0.0) or 0.0)
            unrealized = float(position.get("unrealized_pnl", 0.0) or live.get("unrealized_pnl", 0.0) or 0.0)
            risk_r_usd = max(margin * float(RISK_PCT), 1e-6)
            pnl_r = unrealized / risk_r_usd if risk_r_usd > 0 else 0.0
            stop_triggered = bool(pnl_r <= -float(STOP_R))
            detail = {
                "fleet": fleet,
                "symbol": symbol,
                "status": "hold",
                "unrealized_pnl": round(unrealized, 4),
                "pnl_r": round(pnl_r, 4),
                "stop_r": float(STOP_R),
                "stop_triggered": stop_triggered,
                "inventory_source": "binance_live",
            }
            result["details"].append(detail)

            if stop_triggered:
                emergency = self._attempt_emergency_position_close(
                    fleet,
                    position,
                    current,
                    reason="startup_inventory_stop_r",
                )
                if emergency:
                    result["exits_triggered"] += 1
                    detail["status"] = "emergency_closed"
                    detail["emergency"] = emergency
                    continue

            engine = self.strategy_engines.get(fleet)
            if not engine:
                continue
            try:
                exit_trades = engine.manage_position_exits(
                    {"action": "HOLD", "confidence": 0.0, "reason": "startup_exit_check"},
                    current,
                )
                if exit_trades:
                    result["exits_triggered"] += len(exit_trades)
                    detail["status"] = "closed"
                    for trade in exit_trades:
                        detail["reason"] = trade.get("reason")
                        detail["exit_class"] = trade.get("exit_class")
            except Exception as exc:
                message = f"{fleet}: {exc}"
                result["errors"].append(message)
                print(f"[nexus_runtime] startup exit check failed: {message}")
                if stop_triggered:
                    emergency = self._attempt_emergency_position_close(
                        fleet,
                        position,
                        current,
                        reason="startup_exit_error",
                    )
                    if emergency:
                        result["exits_triggered"] += 1
                        detail["status"] = "emergency_closed"
                        detail["emergency"] = emergency

        self._startup_exit_check = result
        if result["positions_checked"]:
            print(
                "[nexus_runtime] startup exit check: "
                f"checked={result['positions_checked']} "
                f"exits={result['exits_triggered']} "
                f"errors={len(result['errors'])}"
            )
        if result.get("errors") and not self._futures_write_allowed():
            self._alert_futures_write_blocked("startup_exit_check")
        return result

    def _refresh_futures_trading_access(self, symbol="ETHUSDT"):
        try:
            self._futures_trading_access = self.futures_client.validate_trading_access(symbol)
            access = self._futures_trading_access or {}
            post_probe = access.get("write_post_probe") or {}
            print(
                "[nexus_runtime] futures trading access: "
                f"ok={access.get('ok')} can_trade={access.get('can_trade')} "
                f"write_post={post_probe.get('ok')} hedge={access.get('dual_side_position')} "
                f"base={access.get('base_url')}"
            )
            if not self._futures_write_allowed():
                self._alert_futures_write_blocked("startup")
        except Exception as exc:
            self._futures_trading_access = {"ok": False, "error": str(exc)}
            print(f"[nexus_runtime] futures trading access check skipped: {exc}")

    def _futures_write_allowed(self):
        access = getattr(self, "_futures_trading_access", None) or {}
        post_probe = access.get("write_post_probe") or {}
        if post_probe:
            return bool(post_probe.get("ok"))
        return bool(access.get("ok"))

    def _alert_futures_write_blocked(self, source="runtime"):
        post_probe = (getattr(self, "_futures_trading_access", None) or {}).get("write_post_probe") or {}
        error = str(post_probe.get("error") or "")
        summary = (
            "【合約 API 無法下單】NEXUS 已讀到持倉並完成止損評估，但 Binance Demo 拒絕所有平倉/下單請求"
            f"（{error or '-1109 Invalid account'}）。"
            "這不是「沒偵測到庫存」：請到 demo.binance.com 重建 API 金鑰（勾選 Reading + Futures），"
            "Secret 貼到 BINANCE_FUTURES_TESTNET_SECRET_KEY 後 Redeploy；"
            "或先在 App 手動平倉 ETH。"
        )
        self._append_alert("ALERT_RED", summary)
        print(f"[nexus_runtime] futures write blocked ({source}): {error or '-1109'}")

    def _attempt_emergency_position_close(self, fleet, position, price, reason="emergency_close"):
        symbol = str(position.get("symbol") or "").upper()
        if not symbol or not self.futures_client.is_configured():
            return None
        try:
            order = self.futures_client.close_open_position_market(
                symbol,
                client_order_id=f"nexus_emg_{str(fleet).lower()}_{uuid4().hex[:12]}",
            )
            try:
                self.refresh_live_exchange_state(force=True)
            except Exception:
                pass
            return {
                "fleet": fleet,
                "symbol": symbol,
                "reason": reason,
                "price": float(price or 0.0),
                "external_order_id": order.get("orderId"),
                "status": order.get("status"),
            }
        except Exception as exc:
            print(f"[nexus_runtime] emergency close failed {fleet}/{symbol}: {exc}")
            return None

    def stop(self):
        self._stop.set()
        self.account_sync.stop()
        try:
            self.external_market_intel.stop()
        except Exception:
            pass
        try:
            runtime_store.save_snapshot(
                self.snapshot(),
                worker_pid=os.getpid(),
                worker_status="STOPPED",
                writer="nexus_worker_stop",
                flush_now=True,
            )
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _loop(self):
        tick_seconds = max(1.0, float(os.getenv("NEXUS_RUNTIME_TICK_SECONDS", "2")))
        while not self._stop.is_set():
            try:
                self.state_manager.set_module_health("worker", "ONLINE")
                self.state_manager.set_module_health("runtime", "ONLINE")
                self.tick()
                runtime_store.save_snapshot(
                    self.snapshot(),
                    worker_pid=os.getpid(),
                    worker_status="ONLINE",
                    writer="nexus_worker",
                    single_instance=True,
                )
            except Exception as exc:
                self._last_tick_error = str(exc)
                self.state_manager.set_module_health("worker", f"ERROR: {exc}")
                self.state_manager.set_module_health("runtime", f"ERROR: {exc}")
                print(f"[nexus_runtime] tick failed: {exc}")
            sleep_seconds = 0.35 if self._force_immediate_tick else tick_seconds
            self._force_immediate_tick = False
            time.sleep(sleep_seconds)

    def tick(self):
        self._last_tick_error = None
        self.upgrade_pipeline.begin_tick()
        self._process_commands()
        prices = self.price_feed.get_prices(self.futures_client)
        self.latest_prices = dict(prices)
        self.market_overview = self.price_feed.get_market_overview(max_age_seconds=GLOBAL_INDEX_REFRESH_SECONDS)
        symbol_prices = self._build_symbol_prices(prices)
        self.position_manager.update_unrealized(prices, symbol_prices=symbol_prices)
        self._sync_news()

        self._ensure_trading_resumed()
        self._validation_prune_counter = int(getattr(self, "_validation_prune_counter", 0) or 0) + 1
        if self._validation_prune_counter % 45 == 0:
            try:
                runtime_store.prune_trade_validation_events(keep_limit=80)
            except Exception:
                pass

        spot_account = self._sync_spot_account(prices)
        futures_account = self._sync_futures_account(prices)
        self._sync_futures_activity()
        self._reconcile_liquidation_losses(futures_account)
        # Refresh prices after the heavier sync steps so downstream AI/risk/execution
        # logic evaluates against the newest Binance values available in this tick.
        prices = self.price_feed.get_prices(self.futures_client)
        self.latest_prices = dict(prices)
        self.market_overview = self.price_feed.get_market_overview(max_age_seconds=GLOBAL_INDEX_REFRESH_SECONDS)
        self._last_binance_sync["last_sync_time"] = max(
            int(spot_account.get("update_time") or 0),
            int(futures_account.get("update_time") or 0),
            int(time.time() * 1000),
        )
        self._last_binance_sync["sync_status"] = "connected" if self.spot_client.is_configured() or self.futures_client.is_configured() else "disconnected"
        self._last_binance_sync["errors"] = [err for err in [spot_account.get("sync_error"), futures_account.get("sync_error")] if err]
        heuristic_contexts = self._build_market_contexts(prices)
        self.market_context_service.begin_technical_tick()
        exchange_contexts = self.market_context_service.build_futures_contexts(
            {fleet: self.futures_client.resolve_symbol(fleet) for fleet in FLEETS},
            prices,
            futures_account=futures_account,
        )
        market_contexts = {}
        for fleet in FLEETS:
            market_contexts[fleet] = {
                **heuristic_contexts.get(fleet, {}),
                **exchange_contexts.get(fleet, {}),
            }
        self.market_context = market_contexts
        account_sync_status = self._build_account_sync_status()
        truth_status = self.market_context_service.build_truth_layer_status(
            prices=prices,
            spot_account=spot_account,
            futures_account=futures_account,
            account_sync_status=account_sync_status,
            market_contexts=market_contexts,
        )
        truth_status.update(
            self.truth_layer_guard.evaluate(
                truth_status,
                account_sync_status,
                fleet_symbols=FLEETS,
                spot_symbols=list(HQ_SPOT_SYMBOLS),
            )
        )
        self.truth_layer_status = truth_status
        self._last_account_sync_status = account_sync_status
        calibration_snapshot = self.learning_feedback.build_calibration_snapshot()
        radar_symbols = self.upgrade_pipeline.resolve_radar_symbols(self.futures_client)
        try:
            external_radar = self.external_market_intel.top_radar_symbols(self.futures_client)
            if external_radar:
                merged_radar = []
                seen_radar = set()
                for symbol in list(external_radar) + list(radar_symbols):
                    sym = str(symbol or "").upper()
                    if not sym or sym in seen_radar:
                        continue
                    seen_radar.add(sym)
                    merged_radar.append(sym)
                radar_symbols = merged_radar
        except Exception:
            pass
        self.radar_market_scan_service.symbols = tuple(radar_symbols)
        self.radar_scan = self.radar_market_scan_service.scan()
        self.radar_state = dict(self.radar_scan or {})
        self._enrich_market_contexts_with_symbols(market_contexts, futures_account, prices)
        try:
            market_contexts = self.external_market_intel.apply_to_contexts(market_contexts)
        except Exception:
            pass
        try:
            self._refresh_regime_if_due(market_contexts, futures_account)
        except Exception:
            pass
        self.market_context = market_contexts
        self._radar_llm_proposals = self.radar_llm_bridge.fetch_proposals(self.radar_scan, self.truth_layer_status)
        self.whale_state = {
            "generated_at": self.radar_scan.get("generated_at", _now()),
            "watch": list(self.radar_scan.get("whale_watch", []) or []),
            "candidates": list(self.radar_scan.get("candidates", []) or []),
        }
        self.portfolio_status = self.portfolio_governor.evaluate(
            futures_account=futures_account,
            market_context=market_contexts,
            radar_scan=self.radar_scan,
            learning_snapshot=calibration_snapshot,
        )
        futures_total = futures_equity_from_account(futures_account)
        self.growth_status = self.capital_growth_guard.evaluate(futures_total)
        try:
            self.growth_status = self.external_market_intel.apply_growth_directives(self.growth_status)
        except Exception:
            pass
        monthly_risk = self.monthly_drawdown_guard.evaluate(futures_total)
        self.growth_status["monthly_risk"] = dict(monthly_risk or {})
        if monthly_risk.get("block_new_entries"):
            self.growth_status["block_new_entries"] = True
            self.growth_status["block_reason"] = monthly_risk.get("block_reason") or "monthly_max_drawdown"
        walk_forward_status = self.walk_forward_evaluator.evaluate(runtime_store.recent_trade_results(limit=160))
        self._research_gate_status = self.research_gate_service.build_status(
            runtime_store.recent_trade_results(limit=160),
        )
        rotation = self.upgrade_pipeline.strategy_versions.suggest_rotation(
            walk_forward_status,
            {"calibration_snapshot": calibration_snapshot},
        )
        recent_trades = runtime_store.recent_trade_results(limit=80)
        self.growth_status = self.strategy_evolution.evolve_growth_directives(
            self.growth_status,
            walk_forward_status=walk_forward_status,
            rotation=rotation,
            recent_trades=recent_trades,
        )
        self._apply_revenue_exploration_overrides(recent_trades)
        self._apply_testnet_sandbox_overrides(recent_trades)
        if not self._sandbox_startup_done:
            self._maybe_bootstrap_testnet_sandbox()
        self._compound_capital_status = self.compound_capital.build_snapshot(
            futures_total,
            daily_payload=self.growth_status.get("daily"),
            growth_status=self.growth_status,
        )
        self.growth_status["compound"] = dict(self._compound_capital_status)
        self.growth_status["research_gate"] = dict(self._research_gate_status or {})
        if self._research_gate_status.get("block_new_entries"):
            self.growth_status["block_new_entries"] = True
            self.growth_status["block_reason"] = f"research_gate:{self._research_gate_status.get('reason', 'blocked')}"
        self._strategy_evolution_status = {
            "evolution_mode": self.growth_status.get("evolution_mode", "hold"),
            "recent_win_rate": self.growth_status.get("recent_win_rate"),
            "rotation": rotation,
            "walk_forward_ready": bool(walk_forward_status.get("ready")),
            "research_pass": bool(self._research_gate_status.get("research_pass")),
        }
        self._apply_live_capital_plan(futures_account)
        self._synchronize_live_futures_state(futures_account)
        self._ensure_fixed_roundtables()

        if self._manual_pause:
            level = "ALERT_RED" if self._news_pause_active else "WARNING"
            self.state_manager.set_alert(level, emergency=self._news_pause_active, trading_paused=True)
            self._run_fleet_strategies(prices, market_contexts, self.truth_layer_status, exits_only=True)
            self._run_radar_dispatch(prices, market_contexts, self.truth_layer_status, exits_only=True)
            symbol_prices = self._build_symbol_prices(prices)
            self.position_manager.update_unrealized(prices, symbol_prices=symbol_prices)
        else:
            self.state_manager.clear_alert()
            if not FUTURES_ONLY_TRADING:
                self._bootstrap_live_activity(prices, spot_account, self.truth_layer_status)
                self._run_hq_spot_strategy(prices, spot_account, self.truth_layer_status)
            else:
                self._bootstrapped = True
            self._run_fleet_strategies(
                prices,
                market_contexts,
                self.truth_layer_status,
                exits_only=AI_LED_PRIMARY_MODE,
            )
            self._run_ai_led_proposals(prices, market_contexts, self.truth_layer_status)
            self._run_radar_dispatch(
                prices,
                market_contexts,
                self.truth_layer_status,
                exits_only=AI_LED_PRIMARY_MODE,
            )
            symbol_prices = self._build_symbol_prices(prices)
            self.position_manager.update_unrealized(prices, symbol_prices=symbol_prices)
            self._apply_position_ai_actions(prices, market_contexts)

        self._apply_kill_switch(futures_account)
        if not self._manual_pause and not self._news_pause_active:
            self.state_manager.clear_alert()

        if self.futures_client.is_configured():
            emergency, reason = False, ""
        else:
            emergency, reason = self.risk_engine.should_trigger_emergency()
        if emergency:
            self.state_manager.set_alert("ALERT_RED", emergency=True, trading_paused=True)
            self._append_alert("ALERT_RED", reason)
        elif self._manual_pause:
            level = "ALERT_RED" if self._news_pause_active else "WARNING"
            self.state_manager.set_alert(level, emergency=self._news_pause_active, trading_paused=True)
        else:
            self.state_manager.clear_alert()
            self.state_manager.set_module_health("market_data", "ONLINE")

        self._previous_prices = {
            fleet: data["price"]
            for fleet, data in prices.items()
            if fleet in FLEETS
        }
        self._last_spot_account = spot_account
        self._last_futures_account = futures_account
        trade_results = runtime_store.recent_trade_results(limit=200)
        recommendations = runtime_store.recent_signal_weight_recommendations(limit=20)
        self.station_learning_exchange = self.advisory_services.build_station_learning_exchange(
            meetings=self.meetings,
            normalized_events=self.normalized_events,
            market_context=self.market_context,
            learning_status={"calibration_snapshot": calibration_snapshot},
            radar_scan=self.radar_scan,
            portfolio_status=self.portfolio_status,
        )
        self.meetings = [self._normalize_meeting_record(item) for item in self.meetings][:40]
        deterministic_news = self.advisory_services.build_news_understanding(
            self.normalized_events,
            self.truth_layer_status,
            self.market_context,
        )
        deterministic_round = self.advisory_services.build_round_table_advisory(
            self.meetings,
            self.normalized_events,
            self.truth_layer_status,
            portfolio_status=self.portfolio_status,
            station_learning_exchange=self.station_learning_exchange,
        )
        deterministic_reflection = self.advisory_services.build_reflection_advisory(
            trade_results,
            recommendations,
            calibration_snapshot=calibration_snapshot,
        )
        deterministic_radar = self.advisory_services.build_radar_advisory(
            self.normalized_events,
            self.market_context,
            self.truth_layer_status,
        )
        deterministic_multi = self.advisory_services.build_multi_agent_proposals(
            self.normalized_events,
            self.market_context,
            self.truth_layer_status,
            portfolio_status=self.portfolio_status,
            radar_scan=self.radar_scan,
        )

        llm_bundle = self._build_llm_bundle(
            news_payload=deterministic_news,
            roundtable_payload=deterministic_round,
            reflection_payload=deterministic_reflection,
            multi_agent_payload=deterministic_multi,
        )
        self.llm_status = llm_bundle.get("llm_status", self.llm_gateway.status_snapshot())
        self.agent_advisory = {
            "news_understanding": {
                **deterministic_news,
                "llm": llm_bundle.get("news", {}),
            },
            "radar_interpretation": {
                **deterministic_radar,
                "market_scan": self.radar_scan,
                "llm": llm_bundle.get("radar", {}),
            },
            "round_table": {
                **deterministic_round,
                "llm": llm_bundle.get("roundtable", {}),
            },
            "reflection": {
                **deterministic_reflection,
                "llm": llm_bundle.get("reflection", {}),
            },
            "multi_agent": {
                **deterministic_multi,
                "station_learning_exchange": self.station_learning_exchange,
                "portfolio_status": self.portfolio_status,
                "llm_discussion": llm_bundle.get("agent", {}),
                "proposal_output": (llm_bundle.get("agent", {}) or {}).get("output", {}),
            },
            "station_learning_exchange": dict(self.station_learning_exchange or {}),
        }
        reflection_llm = llm_bundle.get("reflection") or {}
        if isinstance(reflection_llm, dict):
            llm_output = reflection_llm.get("output") if isinstance(reflection_llm.get("output"), dict) else {}
            self.upgrade_pipeline.on_llm_reflection({**deterministic_reflection, **llm_output, **reflection_llm})
        self._meeting_execution_directives = self._build_meeting_execution_directives(llm_bundle)
        self.agent_advisory["radar_llm_proposals"] = {
            "count": len(getattr(self, "_radar_llm_proposals", []) or []),
            "items": list(getattr(self, "_radar_llm_proposals", []) or [])[:6],
        }
        self._finalize_scheduled_roundtables(
            deterministic_round,
            llm_bundle.get("roundtable", {}),
        )
        self._live_sync_status = {
            "updated_at": _now(),
            "updated_at_ms": int(time.time() * 1000),
            "writer": "nexus_worker",
            "binance_sync_ms": int(self._last_binance_sync.get("last_sync_time") or 0),
            "news_sync_at": float(self._last_news_sync_at or 0.0),
            "news_count": len(self.latest_news or []),
            "event_count": len(self.normalized_events or []),
            "price_sources": {
                fleet: (data or {}).get("source")
                for fleet, data in (self.latest_prices or {}).items()
                if isinstance(data, dict)
            },
            "index_source": (self.market_overview or {}).get("source"),
            "radar_enabled": bool(LIVE_REFRESH_RADAR and self.futures_client.is_configured()),
        }
        self._maybe_broadcast_daily_ops_report(calibration_snapshot)
        try:
            self.station_dialogue.maybe_refresh_channels(self._dialogue_snapshot())
            self.station_chats = self.station_chat_log.recent_grouped()
        except Exception as exc:
            print(f"[nexus_runtime] station dialogue refresh failed: {exc}")

    def _dialogue_snapshot(self):
        system_snapshot = self.state_manager.snapshot()
        spot_account = getattr(self, "_last_spot_account", {}) or {}
        futures_account = getattr(self, "_last_futures_account", {}) or {}
        exchange_capital = build_ui_capital(
            spot_account,
            futures_account,
            futures_configured=self.futures_client.is_configured(),
            spot_configured=self.spot_client.is_configured(),
        )
        return {
            "system": {
                "alert_level": system_snapshot.get("alert_level", "NORMAL"),
                "trading_paused": bool(self._manual_pause or self._news_pause_active),
                "fleet_status": dict(system_snapshot.get("fleet_status", {})),
            },
            "capital": {
                "total": float(exchange_capital.get("total", 0.0) or 0.0),
                "spot_total": float(exchange_capital.get("spot_total", 0.0) or 0.0),
                "futures_total": float(exchange_capital.get("futures_total", 0.0) or 0.0),
                "source": "binance_rest",
            },
            "news": list(self.latest_news or []),
            "whale": dict(self.whale_state or {}),
            "market_context": dict(self.market_context or {}),
        }

    def _sync_news(self):
        try:
            raw_items = self.news_ingestion.latest(limit=24)
            self.latest_news = self.news_analysis.analyze(raw_items)
            self.normalized_events = self.event_normalizer.normalize(self.latest_news)
            self.upgrade_pipeline.on_news(self.normalized_events)
            self.state_manager.set_module_health("news", "ONLINE")
            self._last_news_sync_at = time.time()
            self._refresh_station_briefings()
            self._maybe_pause_for_major_news()
        except Exception as exc:
            self.state_manager.set_module_health("news", f"ERROR: {exc}")
            self.normalized_events = []
            self._append_alert("WARNING", f"新聞同步失敗：{exc}")

    def _maybe_sync_news_for_meetings(self, min_interval_sec=None):
        if min_interval_sec is None:
            min_interval_sec = NEWS_REFRESH_SECONDS
        last = float(getattr(self, "_last_news_sync_at", 0.0) or 0.0)
        if self.latest_news and (time.time() - last) < min_interval_sec:
            return
        self._sync_news()

    def _news_refresh_due(self):
        last = float(getattr(self, "_last_news_sync_at", 0.0) or 0.0)
        return (time.time() - last) >= NEWS_REFRESH_SECONDS

    def _build_radar_briefing(self, base_notes):
        scan = dict(self.radar_scan or {})
        whale_rows = list(scan.get("whale_watch") or [])
        candidates = list(scan.get("candidates") or [])
        if whale_rows:
            top = whale_rows[0]
            summary = (
                f"巨鯨動態：{top.get('symbol')} {top.get('summary')} "
                f"(訂單簿 {top.get('bias', 'balanced')}, 資金費率 {float(top.get('funding_rate') or 0) * 100:.3f}%)。"
            )
        elif candidates:
            top = candidates[0]
            summary = (
                f"雷達掃描：{top.get('symbol')} 結構分 {top.get('candidate_score')} "
                f"方向 {top.get('candidate_side', 'WATCH')}。"
            )
        else:
            summary = "雷達掃描中，尚未偵測到巨鯨級訂單簿／資金費率異常。"
        watchlist = [str(item.get("symbol") or "").replace("USDT", "") for item in whale_rows[:4] if item.get("symbol")]
        if not watchlist:
            watchlist = ["SOL", "PEPE", "BNB", "DOGE"]
        return {
            **base_notes,
            "summary": summary,
            "meeting_type": "RADAR_SCAN",
            "station_instructions": [
                "監控巨鯨、資金流與異常成交（合約訂單簿，非新聞牆）。",
                "特別關注高資金費率與訂單簿失衡標的。",
            ],
            "fleet_instructions": [],
            "forbidden_actions": [],
            "watchlist": watchlist,
            "risk_notes": [],
            "radar_scan_status": scan.get("scan_status", "idle"),
            "whale_watch_count": len(whale_rows),
        }

    def _build_funding_snapshot(self, market_contexts=None):
        rows = []
        for fleet, ctx in dict(market_contexts or self.market_context or {}).items():
            if not isinstance(ctx, dict):
                continue
            symbol = str(ctx.get("symbol") or "").upper()
            if not symbol:
                continue
            rows.append(
                {
                    "fleet": fleet,
                    "symbol": symbol,
                    "funding_rate": round(float(ctx.get("funding_rate") or 0.0), 8),
                    "basis_bps": round(float(ctx.get("basis_bps") or 0.0), 4),
                    "mark_price": round(float(ctx.get("mark_price") or 0.0), 8),
                }
            )
        for item in list((self.radar_scan or {}).get("market_board") or [])[:20]:
            symbol = str(item.get("symbol") or "").upper()
            if not symbol or any(row.get("symbol") == symbol for row in rows):
                continue
            rows.append(
                {
                    "fleet": "RADAR",
                    "symbol": symbol,
                    "funding_rate": round(float(item.get("funding_rate") or 0.0), 8),
                    "basis_bps": round(float(item.get("basis_bps") or 0.0), 4),
                    "mark_price": round(float(item.get("mark_price") or 0.0), 8),
                }
            )
        return {
            "generated_at": (self.radar_scan or {}).get("generated_at") or _now(),
            "rows": rows,
        }

    def _refresh_station_briefings(self):
        latest = self.latest_news[0] if self.latest_news else {}
        latest_text = _clean_display_text(
            latest.get("summary_zh") or latest.get("summary"),
            "目前沒有重大新聞，維持正常監控。",
        )
        watch_assets = [item for item in (latest.get("targets") or ["ALL"]) if item != "ALL"] or ["BTC", "ETH", "SOL", "BNB"]
        common_focus = [
            "先確認這則事件是否正在快速影響價格與成交量。",
            "追蹤 BTC 主方向與主流幣是否出現同步反應。",
        ]
        base_notes = {
            "meeting_id": latest.get("id", "news-briefing"),
            "meeting_type": "NEWS_BRIEFING",
            "summary": latest_text,
            "next_6h_focus": common_focus,
            "updated_at": _now(),
        }

        notes = {
            "HQ": {
                **base_notes,
                "station_instructions": ["統整全局風險與資金配置。", "必要時準備限制高風險艦隊的新倉。"],
                "fleet_instructions": [],
                "forbidden_actions": [],
                "watchlist": watch_assets,
                "risk_notes": ["重大事件期間優先保護總資金。"] if latest.get("impact") == "HIGH" else [],
            },
            "NEWS": {
                **base_notes,
                "station_instructions": ["持續更新事件摘要與市場敘事。", "標記是否出現政策、清算或交易所風險。"],
                "fleet_instructions": [],
                "forbidden_actions": [],
                "watchlist": watch_assets,
                "risk_notes": [],
            },
            "RADAR": self._build_radar_briefing(base_notes),
        }

        for fleet in FLEETS:
            notes[fleet] = {
                **base_notes,
                "station_instructions": [],
                "fleet_instructions": [
                    f"重新評估 {fleet} 艦隊目前方向是否仍與事件一致。",
                    "若新聞與價格結構衝突，先降低進場積極度。",
                ],
                "forbidden_actions": [],
                "watchlist": [fleet, *watch_assets[:2]],
                "risk_notes": ["重大事件期間避免追高槓桿新倉。"] if latest.get("impact") == "HIGH" else [],
            }

        self.station_briefings = notes

    def _maybe_pause_for_major_news(self):
        if not self.latest_news:
            self._news_pause_active = False
            if self._pause_reason == "NEWS":
                self._manual_pause = False
                self._pause_reason = None
            return

        def is_pauseworthy(item):
            text = f"{item.get('title') or ''} {item.get('summary') or ''}".lower()
            hard_patterns = (
                r"\bhack(ed)?\b",
                r"\bexploit(ed)?\b",
                r"\bbreach\b",
                r"\binsolvenc(y|e)\b",
                r"\bbankrupt(cy|)\b",
                r"\btrading halted\b",
                r"\bexchange hacked\b",
                r"\bsecurity incident\b",
                r"\bgovernment ban\b",
                r"\bban on crypto\b",
                r"\bwar\b",
            )
            return any(re.search(pattern, text) for pattern in hard_patterns)

        major = next((item for item in self.latest_news if item.get("major") and is_pauseworthy(item)), None)
        if not major:
            self._news_pause_active = False
            if self._pause_reason == "NEWS":
                self._manual_pause = False
                self._pause_reason = None
            return

        if self._pause_reason == "NEWS" and self._news_pause_until and time.time() > self._news_pause_until:
            self._news_pause_active = False
            self._manual_pause = False
            self._pause_reason = None
            return

        if self._last_major_news_id == major.get("id"):
            return

        self._last_major_news_id = major.get("id")
        summary = _clean_display_text(major.get("summary"), "市場出現重大風險事件。")
        if always_on_trading_enabled():
            self._append_alert("ALERT_RED", f"重大事件警報（24/7 模式不中斷交易）：{summary}")
            meeting = self._normalize_meeting_record(self._create_structured_news_meeting(major))
            self.meetings.insert(0, meeting)
            self._append_meeting_alert(meeting)
            return

        self._news_pause_active = True
        self._manual_pause = True
        self._pause_reason = "NEWS"
        self._news_pause_until = time.time() + int(os.getenv("NEXUS_NEWS_PAUSE_SECONDS", "900"))
        self._append_alert("ALERT_RED", f"重大事件警報：{_clean_display_text(major.get('summary'), '市場出現重大風險事件。')}")
        meeting = self._normalize_meeting_record(self._create_structured_news_meeting(major))
        self.meetings.insert(0, meeting)
        self.meetings = self.meetings[:40]
        runtime_store.append_meeting(meeting)
        self._save_round_table_memory(meeting)
        self._append_meeting_alert(meeting)
        try:
            self.meeting_broadcaster.broadcast(meeting)
        except Exception:
            pass
        self.station_briefings = self.meeting_broadcaster.load_all() or self.station_briefings

    def _ensure_fixed_roundtables(self):
        stored = runtime_store.recent_meetings(limit=40)
        if stored:
            self.meetings = [self._normalize_meeting_record(item) for item in stored]

        now = nexus_now()
        today = now.strftime("%Y-%m-%d")
        existing = {item.get("meeting_id"): item for item in self.meetings}

        for slot in FIXED_MEETING_SLOTS:
            slot_hour, slot_minute = [int(part) for part in slot.split(":")]
            slot_time = now.replace(hour=slot_hour, minute=slot_minute, second=0, microsecond=0)
            if slot_time > now:
                continue

            meeting_id = f"scheduled_{today}_{slot.replace(':', '-')}"
            latest_news = self.latest_news[0] if self.latest_news else {}
            meeting = self._build_scheduled_roundtable(meeting_id, slot, latest_news)
            current = existing.get(meeting_id)
            if current:
                meeting["created_at"] = current.get("created_at") or meeting.get("created_at") or _now()
                self.meetings = [item for item in self.meetings if item.get("meeting_id") != meeting_id]
            meeting = self._normalize_meeting_record(meeting)
            meeting["updated_at"] = _now()
            self.meetings.insert(0, meeting)
            self.meetings = self._prune_meeting_list(self.meetings)
            runtime_store.append_meeting(meeting)
            self._save_round_table_memory(meeting)
            self._append_meeting_alert(meeting)

        if len(self.alerts) < 2 and self.meetings:
            for item in self.meetings[:4]:
                self._append_meeting_alert(item)

    def _prune_meeting_list(self, meetings):
        now = nexus_now()
        today = now.strftime("%Y-%m-%d")
        cutoff = (now.date() - timedelta(days=14)).isoformat()
        kept = []
        for item in meetings or []:
            meeting_type = str(item.get("type") or "").upper()
            time_prefix = str(item.get("time") or "")[:10]
            if meeting_type == "SCHEDULED_ROUND_TABLE":
                if time_prefix >= today:
                    kept.append(item)
                continue
            if meeting_type == "EMERGENCY_ROUND_TABLE" and time_prefix >= cutoff:
                kept.append(item)
        return sorted(kept, key=lambda item: item.get("time", ""), reverse=True)[:40]

    def _finalize_scheduled_roundtables(self, roundtable_payload, llm_roundtable=None):
        self._ensure_fixed_roundtables()
        self._enrich_today_scheduled_meetings(roundtable_payload, llm_roundtable)

    def _enrich_today_scheduled_meetings(self, roundtable_payload, llm_roundtable=None):
        if not roundtable_payload and not llm_roundtable:
            return
        today = nexus_now().strftime("%Y-%m-%d")
        llm_output = {}
        if isinstance(llm_roundtable, dict):
            llm_output = llm_roundtable.get("output") or {}
        llm_summary = ""
        if isinstance(llm_output, dict):
            llm_summary = str(llm_output.get("meeting_summary") or "").strip()
        machine = str((roundtable_payload or {}).get("machine_summary") or "").strip()
        risk_level = str((roundtable_payload or {}).get("risk_level") or "NORMAL").strip()

        for idx, meeting in enumerate(list(self.meetings)):
            meeting_id = str(meeting.get("meeting_id", ""))
            if not meeting_id.startswith(f"scheduled_{today}_"):
                continue
            conclusion = dict(meeting.get("conclusion") or {})
            base = str(conclusion.get("summary") or meeting.get("summary") or "")
            if "｜AI：" in base:
                base = base.split("｜AI：", 1)[0].rstrip()
            extras = []
            if machine:
                extras.append(machine[:160])
            if llm_summary:
                extras.append(llm_summary[:220])
            if extras:
                conclusion["summary"] = f"{base}｜AI：{' '.join(extras)[:380]}"
            conclusion["risk_level"] = risk_level
            if roundtable_payload and roundtable_payload.get("fleet_restrictions"):
                conclusion["fleet_restrictions"] = dict(roundtable_payload.get("fleet_restrictions", {}))
            updated = self._normalize_meeting_record({**meeting, "conclusion": conclusion, "updated_at": _now()})
            self.meetings[idx] = updated
            runtime_store.append_meeting(updated)

    def _create_news_meeting(self, major_news):
        summary = _clean_display_text(
            major_news.get("summary_zh") or major_news.get("summary"),
            "市場出現需要即時討論的重大事件。",
        )
        impact_targets = major_news.get("targets") or ["ALL"]
        now = _now()
        return {
            "meeting_id": f"news_{str(major_news.get('id', 'major')).replace('|', '_')}",
            "time": now,
            "created_at": now,
            "type": "EMERGENCY_ROUND_TABLE",
            "summary": summary,
            "participants": [{"station": station, "speaker": station} for station in ["HQ", "NEWS", "RADAR", *FLEETS]],
            "conclusion": {
                "summary": f"緊急圓桌會議完成：{summary}。總部先收斂風險，等待各單位回報後續市場方向。",
                "next_6h_focus": [
                    "確認新聞是否已被市場快速定價。",
                    "對比 BTC 主方向與 SOL / PEPE 等高波動標的是否同步或反向。",
                    "在會議結論落地前避免擴大風險曝險。",
                ],
                "forbidden_actions": {"ALL": ["未完成風險確認前禁止追加高風險新倉。"]},
                "fleet_instructions": {
                    fleet: [f"{fleet} 艦隊先重新評估目前持倉與事件是否衝突。"] for fleet in FLEETS
                },
                "station_instructions": {
                    "HQ": ["統整所有單位回報後再決定是否恢復主動進場。"],
                    "NEWS": ["持續更新事件摘要與後續敘事變化。"],
                    "RADAR": ["觀察資金流與巨鯨是否出現反向動作。"],
                },
                "watchlist": {
                    "ALL": impact_targets,
                    "HQ": impact_targets,
                    "NEWS": impact_targets,
                    "RADAR": ["BTC", "SOL", "PEPE"],
                },
                "risk_notes": {"RISK": ["若價格、新聞與資金流互相衝突，優先維持保守風控。"]},
            },
        }

    def _create_structured_news_meeting(self, major_news):
        summary = _clean_display_text(
            major_news.get("summary_zh") or major_news.get("summary"),
            "重大新聞觸發緊急會議",
        )
        impact_targets = list(major_news.get("targets") or ["ALL"])
        now = _now()
        portfolio_status = dict(self.portfolio_status or {})
        station_learning_exchange = dict(self.station_learning_exchange or {})
        return {
            "meeting_id": f"news_{str(major_news.get('id', 'major')).replace('|', '_')}",
            "time": now,
            "created_at": now,
            "type": "EMERGENCY_ROUND_TABLE",
            "summary": summary,
            "participants": [{"station": station, "speaker": station} for station in ["HQ", "NEWS", "RADAR", *FLEETS]],
            "conclusion": {
                "summary": f"緊急會議完成：{summary}",
                "next_6h_focus": [
                    "先確認事件真實影響範圍與持續時間。",
                    "提高 BTC、SOL、PEPE 與高波動標的的監控強度。",
                    "若衝突風險擴大，優先降槓桿、減曝險、延後新單。",
                ],
                "forbidden_actions": {"ALL": ["高衝擊新聞未釐清前，不得提高槓桿或擴大曝險"]},
                "fleet_instructions": {
                    fleet: [f"{fleet} 先重新檢查事件是否與自身標的直接衝突，再決定是否保留新單資格"] for fleet in FLEETS
                },
                "station_instructions": {
                    "HQ": ["統整風險與資金調整方案，必要時提高 reserve。"],
                    "NEWS": ["持續更新事件摘要、影響範圍與可信度。"],
                    "RADAR": ["觀察全市場異常流動性、巨鯨方向與候選機會。"],
                },
                "watchlist": {
                    "ALL": impact_targets,
                    "HQ": impact_targets,
                    "NEWS": impact_targets,
                    "RADAR": ["BTC", "SOL", "PEPE"],
                },
                "risk_notes": {"RISK": ["高衝擊新聞階段需優先保護資本，避免追價與逆勢擴倉。"]},
                "fleet_restrictions": dict(portfolio_status.get("fleet_restrictions", {})),
                "capital_adjustments": dict(portfolio_status.get("capital_adjustments", {})),
                "reserve_action": portfolio_status.get("reserve_action", "hold"),
                "station_shares": list(station_learning_exchange.get("station_shares", []) or []),
                "cross_station_lessons": list(station_learning_exchange.get("cross_station_lessons", []) or []),
                "opportunity_board": list(station_learning_exchange.get("opportunity_board", []) or []),
                "hedge_recommendations": list(portfolio_status.get("hedge_recommendations", []) or []),
            },
        }

    def _save_round_table_memory(self, meeting):
        conclusion = dict(meeting.get("conclusion") or {})
        memory = {
            "meeting_time": meeting.get("time") or meeting.get("created_at") or _now(),
            "market_summary": conclusion.get("summary") or meeting.get("summary") or "",
            "risk_level": self.state_manager.snapshot().get("alert_level", "NORMAL"),
            "enabled_strategies": conclusion.get("enabled_strategies", ["adaptive_signal_fusion"]),
            "disabled_strategies": conclusion.get("disabled_strategies", []),
            "fleet_restrictions": conclusion.get("fleet_restrictions", {}),
            "capital_adjustments": conclusion.get("capital_adjustments", {}),
            "reserve_action": conclusion.get("reserve_action", "hold"),
            "station_shares": list(conclusion.get("station_shares", []) or []),
            "cross_station_lessons": list(conclusion.get("cross_station_lessons", []) or []),
            "opportunity_board": list(conclusion.get("opportunity_board", []) or []),
            "hedge_recommendations": list(conclusion.get("hedge_recommendations", []) or []),
            "reason": meeting.get("summary") or conclusion.get("summary") or "",
            "timestamp": meeting.get("created_at") or _now(),
        }
        runtime_store.save_round_table_decision_memory(memory)

    def _record_trade_journal(self, journal):
        payload = dict(journal)
        payload.setdefault("timestamp", _now())
        self.learning_feedback.record_trade_journal(payload)

    def _build_symbol_prices(self, prices):
        symbol_prices = {}
        for item in (self.radar_scan or {}).get("market_board", []) or []:
            symbol = str(item.get("symbol") or "").upper()
            mark = float(item.get("mark_price", 0.0) or item.get("price", 0.0) or 0.0)
            if symbol and mark > 0:
                symbol_prices[symbol] = mark
        for fleet, data in (prices or {}).items():
            px = float(data.get("price", 0.0) or 0.0)
            if px > 0:
                symbol_prices[f"{fleet}USDT"] = px
                if fleet == "PEPE":
                    symbol_prices["1000PEPEUSDT"] = px
        return symbol_prices

    def _build_meeting_execution_directives(self, llm_bundle=None):
        notes = self._resolve_meeting_notes()
        blocked_fleets = set()
        for fleet, restriction in dict(notes.get("fleet_restrictions") or {}).items():
            if isinstance(restriction, dict) and not restriction.get("allowed_new_entries", True):
                blocked_fleets.add(str(fleet).upper())
        for meeting in list(self.meetings or [])[:6]:
            conclusion = dict(meeting.get("conclusion") or {})
            for desk in list(conclusion.get("disabled_desks") or []):
                blocked_fleets.add(str(desk).upper())
            risk_level = str(conclusion.get("risk_level") or meeting.get("risk_level") or "").upper()
            if risk_level in {"RED", "HIGH", "CRITICAL", "ALERT_RED"}:
                blocked_fleets.add("RADAR")
        llm_bundle = llm_bundle or {}
        round_llm = llm_bundle.get("roundtable") or {}
        round_output = round_llm.get("output") if isinstance(round_llm.get("output"), dict) else round_llm
        if isinstance(round_output, dict):
            for desk in list(round_output.get("disabled_desks") or []):
                blocked_fleets.add(str(desk).upper())
        return {
            "blocked_fleets": sorted(blocked_fleets),
            "forbidden_actions": list(notes.get("forbidden_actions") or [])[:12],
            "source_meeting_id": notes.get("source_meeting_id"),
        }

    def _fleet_blocked_by_meeting(self, fleet):
        fleet = str(fleet or "").upper()
        return fleet in set(self._meeting_execution_directives.get("blocked_fleets") or [])

    def _run_ai_led_proposals(self, prices, market_contexts, truth_status=None):
        if not AI_LED_TRADING_ENABLED or self._manual_pause:
            return
        growth_directives = dict(self.growth_status or {})
        if growth_directives.get("block_new_entries"):
            return
        meeting_notes = self._resolve_meeting_notes()
        core_fleets = {}
        for fleet in FLEETS:
            if self._fleet_blocked_by_meeting(fleet):
                continue
            current = float(prices.get(fleet, {}).get("price", 0.0) or 0.0)
            previous = float(self._previous_prices.get(fleet, current) or current)
            signal = self.signal_fusion.fuse(
                fleet=fleet,
                price_now=current,
                price_prev=previous,
                news_items=self.latest_news,
                alert_level=self.state_manager.snapshot().get("alert_level", "NORMAL"),
                market_context=market_contexts.get(fleet, {}),
                meeting_notes=meeting_notes,
            )
            core_fleets[fleet] = {
                "symbol": self.futures_client.resolve_symbol(fleet),
                "signal": signal,
            }
        radar_guidance = self.learning_feedback.get_strategy_guidance(
            "RADAR",
            "ai_led_trade_proposer",
            "radar_alt",
            market_context=market_contexts.get("RADAR", {}) if isinstance(market_contexts, dict) else {},
        )
        blocked = set(radar_guidance.get("blocked_symbols") or [])
        agent = self.agent_advisory.get("multi_agent") or {}
        agent_output = agent.get("proposal_output") or (agent.get("llm_discussion") or {}).get("output") or {}
        deployable = float(
            (getattr(self, "_compound_capital_status", None) or self.growth_status.get("compound") or {}).get(
                "deployable_pool", 0.0
            )
            or 0.0
        )
        context = {
            "radar_llm_items": getattr(self, "_radar_llm_proposals", []) or [],
            "agent_output": agent_output,
            "positions": self.position_manager.all_positions(),
            "market_context": market_contexts,
            "blocked_symbols": sorted(blocked),
            "news_headlines": [
                (item.get("headline") or item.get("summary") or "")[:120]
                for item in (self.latest_news or [])[:6]
            ],
            "radar_scan": self.radar_scan,
            "core_fleets": core_fleets,
            "deployable_pool": deployable,
        }
        symbol_prices = self._build_symbol_prices(prices)
        requests = list(self.ai_trade_proposer.collect_proposals(context))
        if self.rule_signal_bridge.enabled():
            requests.extend(
                self.rule_signal_bridge.collect_proposals(
                    prices,
                    market_contexts=market_contexts,
                    positions=context.get("positions"),
                    deployable_pool=deployable,
                )
            )
        requests.extend(
            self.strategy_proposal_hub.collect_proposals(
                prices,
                market_contexts=market_contexts,
                positions=context.get("positions"),
                deployable_pool=deployable,
            )
        )
        held_symbols = {
            str(item.get("symbol") or "").upper()
            for item in (context.get("positions") or [])
            if item.get("symbol")
        }
        requests.extend(
            self.market_neutral_engine.collect_proposals(
                market_contexts,
                total_equity=self._futures_available_balance(),
                held_symbols=held_symbols,
            )
        )
        seen = set()
        for request in requests:
            key = (str(request.get("fleet")), str(request.get("symbol")), str(request.get("side")))
            if key in seen:
                continue
            seen.add(key)
            if (
                self.market_neutral_engine.pause_radar_directional()
                and str(request.get("fleet") or "").upper() == "RADAR"
                and request.get("strategy_key") != "market_neutral_funding"
            ):
                continue
            if self.dynamic_blocklist.is_symbol_blocked(str(request.get("symbol") or "")):
                continue
            request = self._apply_confidence_sizing_pipeline(
                request,
                market_contexts,
                deployable_pool=deployable,
            )
            request = self.strategy_proposal_hub.scale_proposal(
                request,
                market_contexts,
            )
            if self.upgrade_pipeline.trade_proposals:
                self.upgrade_pipeline.trade_proposals.create_from_request(
                    request,
                    proposer=request.get("proposer", "llm_proposer"),
                    rationale=request.get("ai_rationale") or request.get("reason"),
                )
            self._try_execute_futures_request(request, symbol_prices, market_contexts, truth_status)

    def _apply_position_ai_actions(self, prices, market_contexts):
        if not self.futures_client.is_configured() or self._manual_pause:
            return
        positions = self.position_manager.all_positions()
        if not positions:
            self._last_position_ai_review = {}
            return
        review = self.ai_position_manager.review_positions(
            positions,
            market_contexts=market_contexts,
            llm_gateway=self.llm_gateway,
        )
        self._last_position_ai_review = dict(review or {})
        for action in list(review.get("actions") or []):
            symbol = str(action.get("symbol") or "").upper()
            fleet = str(action.get("fleet") or "").upper()
            if not symbol or not fleet:
                continue
            position = next(
                (item for item in positions if str(item.get("symbol") or "").upper() == symbol),
                None,
            )
            if not position:
                continue
            engine = self.strategy_engines.get(fleet)
            if not engine:
                continue
            price = float(
                (prices.get(fleet) or {}).get("price")
                or position.get("mark_price")
                or 0.0
            )
            if price <= 0:
                continue
            reason = f"ai_position_{action.get('reason', 'action')}"
            act = str(action.get("action") or "")
            if act == "take_partial_profit":
                action_ctx = {**action, "market_context": market_contexts.get(fleet, {}) or {}}
                if not self.fee_churn_guard.allow_ai_exit(position, action_ctx)[0]:
                    continue
                fraction = float(action.get("fraction") or 0.3)
                trade = engine.execution_engine.reduce_position(
                    position["id"], fraction, price, reason=reason
                )
                if trade:
                    self.fee_churn_guard.mark_partial_exit(position["id"])
            elif act == "reduce":
                action_ctx = {**action, "market_context": market_contexts.get(fleet, {}) or {}}
                if not self.fee_churn_guard.allow_ai_exit(position, action_ctx)[0]:
                    continue
                trade = engine.execution_engine.reduce_position(position["id"], 0.5, price, reason=reason)
                if trade:
                    self.fee_churn_guard.mark_partial_exit(position["id"])
            elif act == "reduce_or_close":
                action_ctx = {**action, "market_context": market_contexts.get(fleet, {}) or {}}
                if not self.fee_churn_guard.allow_ai_exit(position, action_ctx)[0]:
                    continue
                trade = engine.execution_engine.close_position(position["id"], price, reason=reason)
            else:
                trade = None
            if trade:
                self._record_trade_result(
                    {
                        "order_id": trade.get("id"),
                        "symbol": trade.get("symbol"),
                        "market_type": trade.get("market_type", "futures"),
                        "fleet": fleet,
                        "entry_price": trade.get("entry_price"),
                        "exit_price": trade.get("exit_price"),
                        "pnl": trade.get("pnl"),
                        "exit_reason": trade.get("reason"),
                        "exit_class": trade.get("exit_class", "ai_exit"),
                        "strategy_key": f"{fleet.lower()}_adaptive_strategy",
                    },
                    context=market_contexts.get(fleet, {}) or {},
                )

    def _apply_testnet_sandbox_overrides(self, recent_trades=None):
        """Unblock testnet trial trading: learning cooldowns, weak-window growth gates, shadow execution."""
        from backend.trading.sandbox_mode import (
            sandbox_active,
            sandbox_min_approval_score,
            sandbox_min_confidence,
            sandbox_relax_growth_blocks,
        )

        if not sandbox_active():
            return
        soft_block_reasons = {
            "",
            "quality_gate_weak_window",
            "rotation_tighten",
            "monthly_max_drawdown",
            "rotation_hold",
        }
        critical_blocks = {"daily_loss_limit_reached", "daily_max_loss", "monthly_max_drawdown"}
        block_reason = str(self.growth_status.get("block_reason") or "").strip().lower()
        if block_reason in critical_blocks:
            return
        if sandbox_relax_growth_blocks() and block_reason in soft_block_reasons:
            self.growth_status["block_new_entries"] = False
            self.growth_status.pop("block_reason", None)
        monthly = dict(self.growth_status.get("monthly_risk") or {})
        if sandbox_relax_growth_blocks() and monthly.get("block_new_entries") and not monthly.get("breached"):
            self.growth_status["block_new_entries"] = False
        self.growth_status["min_approval_score"] = min(
            float(self.growth_status.get("min_approval_score", 0.55) or 0.55),
            sandbox_min_approval_score(),
        )
        self.growth_status["min_trade_confidence"] = min(
            float(self.growth_status.get("min_trade_confidence", 0.55) or 0.55),
            sandbox_min_confidence(),
        )
        mode = str(self.growth_status.get("evolution_mode") or "")
        if mode in {"rotation_tighten", "tighten_guards"}:
            self.growth_status["evolution_mode"] = "sandbox_explore"

    def _maybe_bootstrap_testnet_sandbox(self):
        from backend.trading.sandbox_mode import sandbox_active
        from config.testnet_sandbox_config import SANDBOX_AUTO_RESET_ON_STARTUP

        self._sandbox_startup_done = True
        if not sandbox_active() or not SANDBOX_AUTO_RESET_ON_STARTUP:
            return
        try:
            self.reset_testnet_sandbox(source="sandbox_startup", clear_loss_history=True)
        except Exception:
            pass

    def _apply_revenue_exploration_overrides(self, recent_trades=None):
        """Loosen entry blocks when revenue track has few/no live closes (bootstrap sampling)."""
        if not REVENUE_GROWTH_MODE:
            return
        trades = list(recent_trades or [])
        closes = [item for item in trades if str(item.get("event") or "").upper() == "CLOSE"]
        critical_blocks = {
            "daily_loss_limit_reached",
            "daily_max_loss",
            "daily_positive_mode_defense",
            "profit_lock_active",
            "daily_target_locked_for_compound",
            "monthly_max_drawdown",
        }
        block_reason = str(self.growth_status.get("block_reason") or "").strip().lower()
        if block_reason in critical_blocks:
            return
        if len(closes) < 3:
            self.growth_status["block_new_entries"] = False
            if block_reason in {"", "quality_gate_weak_window", "rotation_tighten"}:
                self.growth_status.pop("block_reason", None)
            self.growth_status["min_quality_score"] = min(
                float(self.growth_status.get("min_quality_score", 0.65) or 0.65),
                EXPLORATION_MIN_QUALITY,
            )
            mode = str(self.growth_status.get("evolution_mode") or "")
            if mode in {"rotation_tighten", "tighten_guards"}:
                self.growth_status["evolution_mode"] = "exploration_sample"

    def _ensure_trading_resumed(self, force=False):
        if self._news_pause_active and not force:
            return
        reason = str(self._pause_reason or self.growth_status.get("kill_switch_reason") or "").lower()
        soft_tokens = (
            "validation_choke",
            "recent_validation",
            "kill_switch",
            "validation",
            "exchange_sync_stale",
            "consecutive_losses",
        )
        critical_tokens = ("daily_max_loss", "news", "manual", "emergency")
        if not force:
            if any(token in reason for token in critical_tokens):
                return
            if self._manual_pause and not any(token in reason for token in soft_tokens):
                return
        self._manual_pause = False
        self._pause_reason = None
        self.growth_status.pop("kill_switch_reason", None)
        if not self._news_pause_active:
            self.state_manager.clear_alert()

    def resume_trading(self, source="manual"):
        self._news_pause_active = False
        self._news_pause_until = 0.0
        try:
            runtime_store.prune_trade_validation_events(keep_limit=50)
        except Exception:
            pass
        self._ensure_trading_resumed(force=True)
        self._append_alert("INFO", f"交易已恢復（{source}）")
        return {"ok": True, "source": source, "trading_paused": False}

    def reset_testnet_sandbox(self, source="manual", clear_loss_history=True):
        """Clear validation backlog + learning loss history for testnet trial trading."""
        from backend.trading.sandbox_mode import sandbox_active

        removed_losses = 0
        if clear_loss_history:
            try:
                removed_losses = int(runtime_store.clear_negative_trade_results() or 0)
            except Exception:
                removed_losses = 0
        try:
            runtime_store.prune_trade_validation_events(keep_limit=15)
        except Exception:
            pass
        try:
            runtime_store.prune_rejected_decision_audits(keep_limit=20)
        except Exception:
            pass
        try:
            self.learning_feedback._calibration_cache = {"snapshot": None, "expires_at": 0.0}
        except Exception:
            pass
        self._apply_testnet_sandbox_overrides()
        resume = self.resume_trading(source=source)
        self._append_alert(
            "INFO",
            f"測試網沙盒已重置（清除虧損紀錄 {removed_losses} 筆，sandbox={sandbox_active()}）",
        )
        return {
            "ok": True,
            "source": source,
            "removed_loss_trades": removed_losses,
            "sandbox_enabled": bool(sandbox_active()),
            "resume": resume,
        }

    def _apply_kill_switch(self, futures_account):
        if not self.futures_client.is_configured():
            return
        trade_results = runtime_store.recent_trade_results(limit=80)
        live_sync = dict(getattr(self, "_live_sync_status", {}) or {})
        live_sync.setdefault("updated_at_ms", int(self._last_binance_sync.get("last_sync_time") or 0))
        report = self.kill_switch.evaluate(
            growth_status=self.growth_status,
            validation_events=runtime_store.recent_trade_validation_events(limit=80),
            live_sync=live_sync,
            trading_paused=bool(self._manual_pause or self._news_pause_active),
            trade_results=trade_results,
        )
        self.growth_status["kill_switch"] = report
        if not report.get("triggered"):
            return
        if report.get("action") == "already_paused":
            reason_text = str(report.get("reason") or "").lower()
            if any(
                token in reason_text
                for token in ("validation_choke", "validation", "exchange_sync_stale", "consecutive_losses")
            ):
                self._ensure_trading_resumed(force=True)
            return
        reason = str(report.get("reason") or "kill_switch")
        pause_reasons = list(report.get("pause_reasons") or [])
        if not report.get("should_pause", True) or not pause_reasons:
            self.growth_status["kill_switch_warning"] = reason
            if "validation_choke" in str(reason):
                self._append_alert("WARNING", f"驗證拒絕率偏高（未暫停交易）: {reason}")
            return
        pause_reason = ",".join(pause_reasons) or reason
        self._manual_pause = True
        self._pause_reason = pause_reason
        self.growth_status["kill_switch_reason"] = pause_reason
        critical = any(token in pause_reason for token in ("daily_max_loss", "exchange_sync_stale"))
        level = "ALERT_RED" if critical else "WARNING"
        self.state_manager.set_alert(level, emergency=critical, trading_paused=True)
        self._append_alert(level, f"Kill-switch: {pause_reason}")
        if report.get("action") == "pause_and_flatten":
            try:
                self.flatten_all_positions(reason=f"kill_switch:{reason}", source="kill_switch")
            except Exception as exc:
                self._append_alert("WARNING", f"Kill-switch flatten failed: {exc}")

    def _execute_market_neutral_request(self, request, symbol_prices, market_contexts, truth_status):
        request = dict(request or {})
        symbol = str(request.get("symbol") or "").upper()
        price = float(symbol_prices.get(symbol, 0.0) or 0.0)
        margin = float(request.get("margin") or 0.0)
        if not symbol or price <= 0 or margin <= 0 or not self.execution_router:
            return False
        spot_order, futures_order = self.market_neutral_engine.execute_hedge(
            self.execution_router,
            symbol,
            price,
            margin,
        )
        if spot_order and futures_order:
            return True
        self.market_neutral_engine.emergency_flatten_one_leg(
            self.execution_router,
            symbol,
            price,
            "spot" if spot_order else "futures",
        )
        return False

    def ingest_external_proposal(self, proposal):
        """TradingView / external signal entry — same validation chain as AI-led."""
        if self._manual_pause or not self.futures_client.is_configured():
            return False
        proposal = dict(proposal or {})
        symbol = str(proposal.get("symbol") or proposal.get("symbol_override") or "").upper()
        fleet = str(proposal.get("fleet") or "RADAR").upper()
        price = float(proposal.get("price") or (self.latest_prices or {}).get(symbol, 0.0) or 0.0)
        if price <= 0 or not symbol:
            return False
        proposal["price"] = price
        if float(proposal.get("margin") or 0.0) <= 0:
            proposal["margin"] = max(20.0, float(os.getenv("NEXUS_MIN_MARGIN_USD", "45") or 45))
        ctx = self.market_context_service.build_symbol_context(symbol, (self.latest_prices or {}).get(symbol), fleet=fleet)
        market_contexts = dict(self.market_context or {})
        market_contexts[fleet] = {**(market_contexts.get(fleet) or {}), **ctx}
        market_contexts[symbol] = ctx
        return self._try_execute_futures_request(
            proposal,
            self.latest_prices or {},
            market_contexts,
            self.truth_layer_status or {},
        )

    def _try_execute_futures_request(self, request, symbol_prices, market_contexts, truth_status, learning_guidance=None):
        request = dict(request or {})
        if str(request.get("side") or "").upper() == "NEUTRAL_HEDGE":
            return self._execute_market_neutral_request(request, symbol_prices, market_contexts, truth_status)
        fleet = str(request.get("fleet") or "RADAR").upper()
        symbol = str(request.get("symbol") or request.get("symbol_override") or "").upper().replace("/", "")
        if self.dynamic_blocklist.is_symbol_blocked(symbol):
            return False
        request = self._apply_confidence_sizing_pipeline(request, market_contexts)
        if not symbol or self._fleet_blocked_by_meeting(fleet):
            return False
        learning_guidance = learning_guidance or self.learning_feedback.get_strategy_guidance(
            fleet,
            request.get("strategy_key") or f"{fleet.lower()}_adaptive_strategy",
            (market_contexts.get(fleet, {}) or {}).get("market_regime", "normal"),
            market_context=market_contexts.get(fleet, {}) or {},
        )
        if fleet == "RADAR":
            if not self.radar_dispatch.can_open_symbol(symbol, learning_guidance=learning_guidance):
                return False
            if symbol in set(learning_guidance.get("blocked_symbols") or []):
                return False
        current = float(symbol_prices.get(symbol, 0.0) or 0.0)
        if current <= 0:
            return False
        alt_context = (
            market_contexts.get(fleet, {})
            if fleet != "RADAR"
            else (self.market_context_service.build_symbol_context(symbol, self.latest_prices) or {})
        )
        signal = {"action": request.get("side", "HOLD"), "confidence": request.get("adjusted_confidence", 0.5), "reason": request.get("reason")}
        growth_context = self._build_growth_context(fleet, signal, alt_context, request)
        validation = self.validation_pipeline.evaluate(
            request,
            market_context=alt_context,
            truth_status=truth_status or {},
            recent_orders=self.futures_live_orders if self.futures_client.is_configured() else self.execution_engine.recent_orders(limit=120),
            recent_trades=self.futures_live_trades if self.futures_client.is_configured() else self.execution_engine.recent_trades(limit=120),
            portfolio_status=self.portfolio_status,
            growth_context=growth_context,
        )
        validation = self._govern_trade_validation(request, validation, alt_context)
        self._append_decision_audit(request, validation, alt_context, decision_source=request.get("decision_source", "ai_led"))
        if not validation.get("approved"):
            return False
        churn_ok, churn_reason = self.fee_churn_guard.allow_open(request)
        if not churn_ok:
            self._append_decision_audit(
                request,
                {
                    **validation,
                    "approved": False,
                    "reason": churn_reason,
                    "reject_layer": "fee_churn_guard",
                },
                alt_context,
                decision_source=request.get("decision_source", "ai_led"),
            )
            return False
        allowed, _risk_reason = self.risk_engine.validate_order(request)
        if not allowed:
            return False
        execution_engine = self.execution_router.futures_engine if self.execution_router else self.execution_engine
        try:
            if self.execution_router:
                self.execution_router.route_futures_order(
                    fleet=fleet,
                    side=request["side"],
                    price=current,
                    margin=request["margin"],
                    reason=request.get("reason"),
                    confidence_score=request.get("adjusted_confidence", 0.0),
                    market_regime=alt_context.get("market_regime", "normal"),
                    risk_context=alt_context,
                    symbol_override=symbol if fleet == "RADAR" else None,
                    capital_pool=request.get("capital_pool", "radar" if fleet == "RADAR" else "fleet"),
                )
            else:
                execution_engine.market_order(
                    fleet=fleet,
                    side=request["side"],
                    price=current,
                    margin=request["margin"],
                    leverage=request.get("leverage", 5),
                    reason=request.get("reason"),
                    symbol_override=symbol if fleet == "RADAR" else None,
                    capital_pool=request.get("capital_pool", "radar"),
                )
            if fleet == "RADAR":
                self.radar_dispatch.mark_open(symbol)
            return True
        except Exception as exc:
            self._append_alert("WARNING", f"AI-led order failed {symbol}: {exc}")
            return False

    def _resolve_meeting_notes(self):
        return resolve_meeting_notes(self.meetings, runtime_store)

    def _build_growth_context(self, fleet, signal, market_context, request):
        ledger_capital = self.ledger.snapshot()
        return {
            "signal": signal,
            "meeting_notes": self._resolve_meeting_notes(),
            "growth_directives": dict(self.growth_status or {}),
            "news_items": list(self.latest_news or []),
            "whale_status": {
                "severity": "ALERT_RED" if self.state_manager.snapshot().get("alert_level") == "ALERT_RED" else "NORMAL",
                "watch": list(self.whale_state.get("watch", []) or []),
            },
            "funding_status": {
                "severity": "WARNING" if float(market_context.get("funding_abs", 0.0) or 0.0) > 0.0008 else "NORMAL",
            },
            "trades": runtime_store.recent_trade_journal(limit=240),
            "capital_snapshot": ledger_capital,
            "loan_snapshot": self.loan_manager.snapshot().get("fleets", {}),
            "audits": runtime_store.recent_decision_audit(limit=80),
        }

    def _append_decision_audit(self, proposal, validation, market_context, order_id=None, decision_source=None):
        decision_quality = dict((validation.get("stages") or {}).get("decision_quality") or {})
        source = decision_source or proposal.get("decision_source") or proposal.get("proposer") or "rule_engine"
        runtime_store.append_decision_audit(
            {
                "timestamp": _now(),
                "symbol": proposal.get("symbol") or f"{proposal.get('fleet')}USDT",
                "raw_signal": proposal.get("side", "HOLD"),
                "raw_confidence": proposal.get("raw_confidence", 0.0),
                "adjusted_confidence": proposal.get("adjusted_confidence", 0.0),
                "quality_score": decision_quality.get("quality_score", 0.0),
                "fleet_score": decision_quality.get("fleet_score", 0.0),
                "setup_type": decision_quality.get("setup_type", ""),
                "market_regime": market_context.get("market_regime", "normal"),
                "context_summary": decision_quality.get("reason", validation.get("reason", "")),
                "approved": validation.get("approved"),
                "reject_layer": None if validation.get("approved") else "validation_pipeline",
                "reject_reason": validation.get("reason"),
                "position_size": proposal.get("margin", 0.0),
                "leverage": proposal.get("leverage", 0.0),
                "order_id": order_id,
                "decision_source": source,
                "proposer": proposal.get("proposer") or source,
            }
        )

    def _maybe_broadcast_daily_ops_report(self, calibration_snapshot=None):
        if not DAILY_REPORT_ENABLED:
            return
        now = nexus_now()
        ok, key = should_broadcast(now, self._last_daily_report_key)
        if not ok:
            return
        walk_forward = self.walk_forward_evaluator.evaluate(runtime_store.recent_trade_results(limit=160))
        upgrade_status = self.upgrade_pipeline.build_status(
            walk_forward_status=walk_forward,
            learning_status={"calibration_snapshot": calibration_snapshot or {}},
        )
        message = format_daily_ops_report(runtime_store, walk_forward=walk_forward, upgrade_status=upgrade_status)
        for channel in ("WORLD", "RADAR", "RISK", "HQ"):
            self.station_chat_log.add(channel, "戰報中心", message, source="daily_ops_report", importance="INFO")
        self._last_daily_report_key = key
        self.station_chats = self.station_chat_log.recent_grouped()

    def _govern_trade_validation(self, request, validation, market_context):
        request = dict(request or {})
        fleet = str(request.get("fleet") or "").upper()
        strategy_key = request.get("strategy_key") or f"{fleet.lower()}_adaptive_strategy"
        guidance = self.learning_feedback.get_strategy_guidance(
            fleet,
            strategy_key,
            (market_context or {}).get("market_regime", "normal"),
            market_context=market_context or {},
        )
        governed, _trace = self.upgrade_pipeline.govern_validation(
            request,
            validation,
            portfolio_status=self.portfolio_status,
            learning_guidance=guidance,
            regime_state=self.regime_classifier.snapshot(),
            dynamic_blocklist=self.dynamic_blocklist,
        )
        self._record_validation_event(
            {
                **governed,
                "symbol": request.get("symbol"),
                "fleet": fleet,
                "timestamp": _now(),
            }
        )
        self._append_decision_audit(request, governed, market_context or {})
        return governed

    def _record_trade_result(self, result, context=None):
        payload = dict(result)
        payload.setdefault("timestamp", _now())
        if not payload.get("event") and (
            payload.get("exit_reason") or payload.get("exit_price") or payload.get("exit_class")
        ):
            payload["event"] = "CLOSE"
        context = context or {}
        fleet = str(payload.get("fleet") or "").upper()
        setup_type = payload.get("setup_type") or context.get("setup_type")
        regime = payload.get("market_regime") or context.get("market_regime", "normal")
        if setup_type:
            self.setup_performance_tracker.record_outcome(fleet, setup_type, regime, payload.get("pnl", 0.0))
            side = str(payload.get("side") or context.get("side") or "BUY").upper()
            strategy_key = payload.get("strategy_key") or f"{fleet.lower()}_adaptive_strategy"
            self.signal_memory_engine.record_trade_outcome(
                fleet,
                side,
                strategy_key,
                regime,
                setup_type,
                context,
                payload.get("pnl", 0.0),
            )
        result, recommendation = self.learning_feedback.record_trade_result(payload, context=context or {})
        self.upgrade_pipeline.on_trade_result(result, recommendation)
        event = str(payload.get("event") or result.get("event") or "").upper()
        if event == "CLOSE" and float(payload.get("pnl", 0.0) or 0.0) < 0:
            try:
                ctx_snap = dict(context or {})
                ctx_snap["market_regime_ai"] = (self.regime_classifier.snapshot() or {}).get("label")
                diagnosis = self.post_trade_postmortem.on_trade_close(
                    {**payload, "confidence_matrix": payload.get("confidence_matrix")},
                    ctx_snap,
                )
                payload["post_mortem"] = diagnosis
            except Exception as exc:
                print(f"[nexus_runtime] post_mortem skipped: {exc}")
        if event in {"CLOSE", "LIVE"} or payload.get("exit_reason") or payload.get("exit_price"):
            symbol = str(payload.get("symbol") or result.get("symbol") or "").upper()
            if symbol:
                self.fee_churn_guard.mark_symbol_closed(symbol)
        if str(result.get("failure_reason") or "") == "exchange_liquidation":
            self._force_immediate_tick = True
            self._append_alert("ALERT_RED", f"強平學習：{result.get('symbol')} 進入冷卻，非永久黑名單。")
        return result

    def _record_validation_event(self, validation_event):
        payload = dict(validation_event or {})
        payload.setdefault("timestamp", _now())
        runtime_store.append_trade_validation_event(payload)

    def _build_learning_status(self):
        recommendations = runtime_store.recent_signal_weight_recommendations(limit=10)
        trade_results = runtime_store.recent_trade_results(limit=200)
        failures = [item for item in trade_results if item.get("failure_reason")]
        disabled_patterns = sorted(
            {
                rec.get("disabled_pattern_candidate")
                for rec in recommendations
                if rec.get("disabled_pattern_candidate")
            }
        )
        return {
            "trade_journal_count": len(runtime_store.recent_trade_journal(limit=500)),
            "failure_patterns_count": len(failures),
            "latest_recommendations": recommendations[:5],
            "disabled_patterns": disabled_patterns,
            "calibration_snapshot": self.learning_feedback.build_calibration_snapshot(),
            "strategy_adaptation": self.learning_feedback.build_strategy_adaptation_snapshot(self.market_context or {}),
            "learning_reviews": self.upgrade_pipeline.learning_reviews.status_snapshot(),
        }

    def _build_validation_status(self):
        return self.validation_pipeline.build_status_snapshot(limit=160)

    def _build_llm_bundle(self, news_payload, roundtable_payload, reflection_payload, multi_agent_payload):
        compact_market_context = {
            fleet: {
                "symbol": context.get("symbol"),
                "market_regime": context.get("market_regime", "normal"),
                "spread_status": context.get("spread_status", "normal"),
                "liquidity_status": context.get("liquidity_status", "healthy"),
                "oi_status": context.get("oi_status", "healthy"),
                "basis_bps": round(float(context.get("basis_bps", 0.0) or 0.0), 4),
                "imbalance_bias": context.get("imbalance_bias", "balanced"),
                "liquidation_risk": context.get("liquidation_risk", "none"),
                "funding_rate_sign": "positive"
                if float(context.get("funding_rate", 0.0) or 0.0) > 0
                else "negative"
                if float(context.get("funding_rate", 0.0) or 0.0) < 0
                else "flat",
            }
            for fleet, context in (self.market_context or {}).items()
        }
        minimal_news = {
            "truth_ready": bool(self.truth_layer_status.get("fresh_for_ai")),
            "bucket_counts": dict(news_payload.get("bucket_counts", {})),
            "highest_risk_events": list(news_payload.get("highest_risk_events", []))[:4],
            "market_regimes": dict(news_payload.get("market_regimes", {})),
        }
        minimal_radar = {
            "market_context": compact_market_context,
            "radar_scan": dict(self.radar_scan or {}),
            "normalized_events": list(self.normalized_events or [])[:6],
            "truth_layer_status": {
                "fresh_for_ai": bool(self.truth_layer_status.get("fresh_for_ai")),
                "degraded_market_contexts": list(self.truth_layer_status.get("degraded_market_contexts", []) or []),
            },
        }
        minimal_roundtable = {
            "meeting_reference": roundtable_payload.get("meeting_reference", ""),
            "machine_summary": roundtable_payload.get("machine_summary", ""),
            "risk_level": roundtable_payload.get("risk_level", "NORMAL"),
            "enabled_desks": list(roundtable_payload.get("enabled_desks", [])),
            "disabled_desks": list(roundtable_payload.get("disabled_desks", [])),
            "fleet_restrictions": dict(roundtable_payload.get("fleet_restrictions", {})),
            "capital_adjustments": dict(roundtable_payload.get("capital_adjustments", {})),
            "normalized_events": list(self.normalized_events or [])[:5],
        }
        minimal_reflection = {
            "loss_count": reflection_payload.get("loss_count", 0),
            "failure_pattern_counts": dict(reflection_payload.get("failure_pattern_counts", {})),
            "latest_recommendations_by_fleet": dict(reflection_payload.get("latest_recommendations_by_fleet", {})),
        }
        minimal_agent = {
            "world_channel": list(multi_agent_payload.get("world_channel", [])),
            "internal_channels": dict(multi_agent_payload.get("internal_channels", {})),
            "truth_layer_status": {
                "fresh_for_ai": bool(self.truth_layer_status.get("fresh_for_ai")),
                "futures_ready_for_ai": bool(self.truth_layer_status.get("futures_ready_for_ai")),
                "spot_ready_for_ai": bool(self.truth_layer_status.get("spot_ready_for_ai")),
            },
            "market_context": compact_market_context,
            "portfolio_status": dict(self.portfolio_status or {}),
            "station_learning_exchange": dict(self.station_learning_exchange or {}),
        }
        return {
            "news": self.llm_gateway.run_task("news", minimal_news, fallback_output=news_payload),
            "radar": self.llm_gateway.run_task("radar", minimal_radar, fallback_output=self.advisory_services.build_radar_advisory(self.normalized_events, self.market_context, self.truth_layer_status)),
            "roundtable": self.llm_gateway.run_task("roundtable", minimal_roundtable, fallback_output=roundtable_payload),
            "reflection": self.llm_gateway.run_task("reflection", minimal_reflection, fallback_output=reflection_payload),
            "agent": self.llm_gateway.run_task("agent", minimal_agent, fallback_output=multi_agent_payload),
            "llm_status": self.llm_gateway.status_snapshot(),
        }

    def _build_account_sync_status(self):
        spot_stream_health = (
            self.account_sync.spot_stream_manager.health_snapshot()
            if getattr(self.account_sync, "spot_stream_manager", None)
            else {
                "status": "disconnected",
                "status_detail": "",
                "connected": False,
                "truth_mode": "stream",
                "last_sync_time": 0,
                "listen_key_active": False,
                "reconnect_attempt": 0,
                "last_keepalive_time": 0,
                "last_rest_reconcile_time": 0,
                "event_counts": {
                    "executionReport": 0,
                    "outboundAccountPosition": 0,
                    "balanceUpdate": 0,
                },
                "errors": [],
            }
        )
        spot_truth_mode = "stream" if spot_stream_health.get("truth_mode") == "stream" and spot_stream_health.get("connected") else "rest_only"
        futures_truth_mode = "stream" if self.account_sync.futures_status.websocket_status in {"connected", "healthy"} else "rest_only"
        return {
            "spot_connected": self.account_sync.spot_status.connected,
            "futures_connected": self.account_sync.futures_status.connected,
            "spot_truth_mode": spot_truth_mode,
            "futures_truth_mode": futures_truth_mode,
            "spot_truth_scope": str(getattr(self, "_last_spot_account", {}).get("truth_scope", HQ_SPOT_TRUTH_MODE)),
            "spot_allowed_assets": list(getattr(self, "_last_spot_account", {}).get("allowed_assets", HQ_SPOT_ALLOWED_ASSETS)),
            "spot_excluded_assets_count": int(getattr(self, "_last_spot_account", {}).get("excluded_assets_count", 0) or 0),
            "websocket_status": {
                "spot": self.account_sync.spot_status.websocket_status,
                "futures": self.account_sync.futures_status.websocket_status,
            },
            "rest_snapshot_status": {
                "spot": self.account_sync.spot_status.rest_snapshot_status,
                "futures": self.account_sync.futures_status.rest_snapshot_status,
            },
            "spot_stream_health": spot_stream_health,
        }

    def _apply_live_capital_plan(self, futures_account):
        if not self.futures_client.is_configured():
            return
        futures_total = futures_equity_from_account(futures_account)
        if futures_total <= 0:
            return

        if FUTURES_ONLY_TRADING:
            deployable = max(futures_total * float(FUTURES_DEPLOY_FRACTION), 0.0)
            reserve = max(futures_total - deployable, 0.0)
        else:
            reserve = futures_total * FUTURES_RESERVE_RATIO
            deployable = max(futures_total - reserve, 0.0)
        fleet_allocations = {
            fleet: round(deployable * FLEET_ALLOCATION_WEIGHTS.get(fleet, 0.0), 4)
            for fleet in FLEETS
        }
        radar_budget = round(deployable * RADAR_ALLOCATION_WEIGHT, 4)
        self.ledger.apply_live_distribution(reserve, radar_budget, fleet_allocations)
        self.radar_state = {
            "budget": round(radar_budget, 4),
            "deployable_pool": round(deployable, 4),
            "weights": {
                **{fleet: FLEET_ALLOCATION_WEIGHTS.get(fleet, 0.0) for fleet in FLEETS},
                "RADAR": RADAR_ALLOCATION_WEIGHT,
            },
        }

    def _futures_available_balance(self, futures_account=None) -> float:
        account = futures_account or getattr(self, "_last_futures_account", None) or {}
        return float(futures_equity_from_account(account) or 0.0)

    def _apply_confidence_sizing_pipeline(
        self,
        request,
        market_contexts,
        *,
        deployable_pool: float = 0.0,
        futures_account=None,
    ):
        if not request:
            return request
        fleet = str(request.get("fleet") or "").upper()
        symbol = str(request.get("symbol") or request.get("symbol_override") or fleet).upper()
        ctx = (market_contexts or {}).get(fleet) or (market_contexts or {}).get(symbol) or {}
        try:
            return self.confidence_sizing_pipeline.apply(
                dict(request),
                market_context=ctx,
                market_contexts=market_contexts,
                regime_state=self.regime_classifier.snapshot(),
                deployable_pool=deployable_pool,
                available_balance=self._futures_available_balance(futures_account),
            )
        except Exception:
            return request

    def _refresh_regime_if_due(self, market_contexts, futures_account):
        now = time.time()
        if now - float(getattr(self, "_last_regime_refresh_at", 0.0) or 0.0) < REGIME_REFRESH_SECONDS:
            return self.regime_classifier.snapshot()
        btc_ctx = dict((market_contexts or {}).get("BTC") or {})
        intel = self.external_market_intel.snapshot() if getattr(self, "external_market_intel", None) else {}
        cq = intel.get("cryptoquant") or {}
        payload = {
            "btc_trend": btc_ctx.get("trend_bias"),
            "btc_atr_pct": btc_ctx.get("atr_pct"),
            "btc_change_24h": btc_ctx.get("price_change_15m"),
            "external_alerts": intel.get("alerts") or [],
            "external_oi_stress": bool(cq.get("oi_stress")),
            "external_whale_dump_alert": bool(cq.get("whale_dump_alert")),
            "major_news_event": any(
                str(item.get("impact") or "").upper() in {"HIGH", "CRITICAL"}
                for item in (self.normalized_events or [])[:12]
                if isinstance(item, dict)
            ),
        }
        state = self.regime_classifier.refresh(payload)
        self._last_regime_refresh_at = now
        label = state.get("label", "CHOP_RNG")
        for key, ctx in list((market_contexts or {}).items()):
            if isinstance(ctx, dict):
                ctx["market_regime_ai"] = label
        if isinstance(self.growth_status, dict):
            self.growth_status["market_regime_ai"] = label
            self.growth_status["regime_classifier"] = state
            if self.market_neutral_engine.pause_radar_directional():
                self.growth_status["pause_radar_directional"] = True
                self.growth_status.setdefault("block_reason", "market_neutral_active")
        return state

    def _enrich_market_contexts_with_symbols(self, market_contexts, futures_account, prices):
        if not self.futures_client.is_configured():
            return
        positions_by_symbol = {
            str(item.get("symbol") or "").upper(): dict(item)
            for item in ((futures_account or {}).get("positions") or [])
            if item.get("symbol")
        }
        symbols = set()
        for fleet in FLEETS:
            symbols.add(self.futures_client.resolve_symbol(fleet))
        for symbol, payload in positions_by_symbol.items():
            if abs(float(payload.get("signed_quantity") or payload.get("quantity") or 0.0)):
                symbols.add(symbol)
        radar = self.radar_scan or {}
        for row in list(radar.get("candidates") or []) + list(radar.get("whale_watch") or []):
            symbols.add(str(row.get("symbol") or "").upper())
        fleet_by_symbol = {
            self.futures_client.resolve_symbol(fleet): fleet for fleet in FLEETS
        }
        for symbol in symbols:
            if not symbol:
                continue
            sym = str(symbol).upper()
            if getattr(self.futures_client, "is_tradable_symbol", None) and not self.futures_client.is_tradable_symbol(sym):
                continue
            fleet = fleet_by_symbol.get(sym, sym)
            price_payload = prices.get(fleet, {}) if fleet in FLEETS else {}
            if not price_payload:
                for candidate in FLEETS:
                    if self.futures_client.resolve_symbol(candidate) == sym:
                        price_payload = prices.get(candidate, {})
                        fleet = candidate
                        break
            context = self.market_context_service.build_symbol_context(
                sym,
                price_payload=price_payload,
                position_payload=positions_by_symbol.get(sym, {}),
                fleet=fleet,
            )
            if context:
                market_contexts[sym] = context
                if fleet in FLEETS:
                    market_contexts[fleet] = {
                        **dict(market_contexts.get(fleet) or {}),
                        **context,
                    }

    def _build_market_contexts(self, prices):
        btc_now = float(prices.get("BTC", {}).get("price", 0.0) or 0.0)
        btc_prev = float(self._previous_prices.get("BTC", btc_now) or btc_now)
        btc_change = 0.0 if not btc_prev else (btc_now - btc_prev) / btc_prev
        whale_bias = "BULLISH" if btc_change >= 0.0025 else "BEARISH" if btc_change <= -0.0025 else "NEUTRAL"
        whale_severity = "ACTIVE" if abs(btc_change) >= 0.0025 else "WATCH"
        if abs(btc_change) >= 0.005:
            whale_severity = "SURGE"

        contexts = {}
        for fleet in FLEETS:
            price_now = float(prices.get(fleet, {}).get("price", 0.0) or 0.0)
            price_prev = float(self._previous_prices.get(fleet, price_now) or price_now)
            local_change = 0.0 if not price_prev else (price_now - price_prev) / price_prev
            follow_strength = min(1.0, abs(local_change) / 0.01)
            contexts[fleet] = {
                "trend_strength": local_change,
                "local_change_fast": local_change,
                "volume_confirmed": abs(local_change) >= 0.0012,
                "support_distance": max(0.01, 0.08 - min(abs(local_change) * 10, 0.06)),
                "resistance_distance": max(0.01, 0.08 - min(abs(local_change) * 10, 0.06)),
                "fake_breakout_risk": abs(local_change) >= 0.008 and fleet in {"SOL", "PEPE"},
                "btc_market_bias": whale_bias,
                "whale_bias": whale_bias if fleet in RADAR_ALT_TARGETS else "NEUTRAL",
                "whale_follow_strength": follow_strength if fleet in RADAR_ALT_TARGETS else 0.0,
            }

        tracked_alts = []
        for fleet in RADAR_ALT_TARGETS:
            change = float(contexts.get(fleet, {}).get("local_change_fast", 0.0) or 0.0)
            if whale_bias == "BULLISH" and change > 0:
                tracked_alts.append(fleet)
            elif whale_bias == "BEARISH" and change < 0:
                tracked_alts.append(fleet)

        self.whale_state = {
            "severity": whale_severity,
            "bias": whale_bias,
            "tracked_wallets": 1 if whale_bias != "NEUTRAL" else 0,
            "summary": "巨鯨方向與小幣走勢目前同步。" if tracked_alts else "目前沒有明確的巨鯨帶動小幣訊號。",
            "focus_assets": tracked_alts,
            "btc_change_pct": round(btc_change * 100, 4),
        }
        return contexts

    def flatten_all_positions(self, reason="manual_flatten_all", source="chat", trigger_text=""):
        """Force-close all open USDT-M futures positions on Binance (reduce-only market)."""
        outcome = {
            "ok": True,
            "reason": reason,
            "source": source,
            "trigger_text": str(trigger_text or "")[:120],
            "closed": [],
            "failed": [],
            "skipped": [],
        }
        try:
            self.refresh_live_exchange_state(force=True)
        except Exception as exc:
            outcome["sync_warning"] = str(exc)

        futures_positions = self._collect_futures_positions_for_flatten()
        if not futures_positions:
            if source != "player_chat":
                self._broadcast_flatten_chat(outcome)
            return outcome

        prices = self.latest_prices or {}
        for position in futures_positions:
            symbol = str(position.get("symbol") or "").upper()
            fleet = str(position.get("fleet") or "RADAR").upper()
            side = str(position.get("side") or "").upper()
            pos_id = position.get("id") or f"live_{fleet}_{symbol}"
            qty = float(position.get("quantity", 0.0) or 0.0)
            if qty <= 0 or side not in {"BUY", "SELL"}:
                outcome["skipped"].append({"symbol": symbol, "reason": "empty_or_hold"})
                continue

            price = float(position.get("mark_price", 0.0) or 0.0)
            if price <= 0:
                price = float((prices.get(fleet) or {}).get("price", 0.0) or 0.0)
            if price <= 0 and self.futures_client.is_configured():
                try:
                    ticker = self.futures_client.get_book_ticker(symbol)
                    price = float(ticker.get("bidPrice") or ticker.get("askPrice") or 0.0)
                except Exception:
                    price = 0.0
            if price <= 0:
                outcome["failed"].append({"symbol": symbol, "fleet": fleet, "error": "no_mark_price"})
                continue

            record = dict(position)
            record["id"] = pos_id
            with self.position_manager._lock:
                self.position_manager.positions[pos_id] = record

            close_reason = f"{reason}:{source}"
            try:
                trade = self.execution_engine.close_position(pos_id, price, reason=close_reason)
            except Exception as exc:
                trade = None
                outcome["failed"].append({"symbol": symbol, "fleet": fleet, "error": str(exc)})

            if trade:
                outcome["closed"].append(
                    {
                        "symbol": trade.get("symbol", symbol),
                        "fleet": trade.get("fleet", fleet),
                        "side": trade.get("side", side),
                        "pnl": trade.get("pnl"),
                        "external_order_id": trade.get("external_order_id"),
                    }
                )
                self._record_trade_result(
                    {
                        "order_id": trade.get("id"),
                        "symbol": trade.get("symbol", symbol),
                        "market_type": "futures",
                        "fleet": fleet,
                        "entry_price": trade.get("entry_price"),
                        "exit_price": trade.get("exit_price"),
                        "pnl": trade.get("pnl"),
                        "exit_reason": trade.get("reason"),
                        "exit_class": "manual_flatten",
                        "strategy_key": f"{fleet.lower()}_adaptive_strategy",
                    },
                    context={},
                )
                continue

            direct = self._close_exchange_futures_position_direct(symbol, side, qty, price, close_reason)
            if direct.get("ok"):
                outcome["closed"].append(direct)
                with self.position_manager._lock:
                    self.position_manager.positions.pop(pos_id, None)
            else:
                outcome["failed"].append(
                    {"symbol": symbol, "fleet": fleet, "error": direct.get("error") or "close_failed"}
                )

        self._flatten_exchange_futures_leftovers(outcome, reason=f"{reason}:{source}")
        try:
            self.refresh_live_exchange_state(force=True)
        except Exception:
            pass

        outcome["ok"] = bool(outcome["closed"]) or (not outcome["failed"] and not futures_positions)
        self._force_immediate_tick = True
        if source != "player_chat":
            self._broadcast_flatten_chat(outcome)
        return outcome

    def _collect_futures_positions_for_flatten(self):
        items = []
        seen = set()
        for position in self.position_manager.all_positions():
            if str(position.get("market_type", "futures")) != "futures":
                continue
            symbol = str(position.get("symbol") or "").upper()
            qty = float(position.get("quantity", 0.0) or 0.0)
            if qty <= 0 or not symbol:
                continue
            key = (symbol, str(position.get("side") or "").upper())
            if key in seen:
                continue
            seen.add(key)
            items.append(position)

        if items or not self.futures_client.is_configured():
            return items

        futures_account = getattr(self, "_last_futures_account", {}) or {}
        for position in self._live_futures_positions_snapshot(futures_account):
            symbol = str(position.get("symbol") or "").upper()
            qty = float(position.get("quantity", 0.0) or 0.0)
            if qty <= 0 or not symbol:
                continue
            key = (symbol, str(position.get("side") or "").upper())
            if key in seen:
                continue
            seen.add(key)
            items.append(position)
        return items

    def _close_exchange_futures_position_direct(self, symbol, side, quantity, price, reason):
        if not self.futures_client.is_configured():
            return {"ok": False, "error": "futures_not_configured"}
        close_side = "SELL" if side == "BUY" else "BUY"
        qty = self.futures_client.normalize_quantity(symbol, quantity)
        if qty <= 0:
            return {"ok": False, "error": "invalid_quantity"}
        external_id = f"nexus_flatten_{uuid4().hex[:16]}"
        try:
            order = self.futures_client.place_market_order(
                symbol=symbol,
                side=close_side,
                quantity=qty,
                reduce_only=True,
                client_order_id=external_id,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        fill_price = self.futures_client.extract_fill_price(order, fallback_price=price)
        return {
            "ok": True,
            "symbol": symbol,
            "side": side,
            "quantity": qty,
            "exit_price": fill_price,
            "external_order_id": order.get("orderId"),
            "reason": reason,
            "execution_source": "binance_futures_direct_flatten",
        }

    def _flatten_exchange_futures_leftovers(self, outcome, reason="flatten_leftover"):
        if not self.futures_client.is_configured():
            return
        closed_symbols = {str(item.get("symbol") or "").upper() for item in outcome.get("closed") or []}
        symbol_map = {self.futures_client.resolve_symbol(fleet): fleet for fleet in FLEETS}
        try:
            risks = self.futures_client.get_all_position_risk() or []
        except Exception as exc:
            outcome.setdefault("sync_warning", str(exc))
            return

        for item in risks:
            symbol = str(item.get("symbol") or "").upper()
            position_amt = float(item.get("positionAmt", 0.0) or 0.0)
            if abs(position_amt) < 1e-12 or symbol in closed_symbols:
                continue
            side = "BUY" if position_amt > 0 else "SELL"
            qty = abs(position_amt)
            price = float(item.get("markPrice", 0.0) or 0.0)
            fleet = fleet_for_exchange_position(symbol, symbol_map)
            direct = self._close_exchange_futures_position_direct(symbol, side, qty, price, reason)
            if direct.get("ok"):
                outcome["closed"].append(direct)
                closed_symbols.add(symbol)
            else:
                outcome["failed"].append({"symbol": symbol, "fleet": fleet, "error": direct.get("error")})

    def _broadcast_flatten_chat(self, outcome):
        from backend.coordination.chat_command_handler import format_flatten_reply

        message = format_flatten_reply(outcome)
        importance = "HIGH" if outcome.get("failed") else "WARNING"
        runtime_store.append_station_chat(
            {
                "timestamp": _now(),
                "station": "RISK",
                "speaker": "風控中心主任",
                "message": message,
                "source": "整體平倉",
                "importance": importance,
            }
        )
        self.station_chats = self.station_chat_log.recent_grouped()

    def _process_commands(self):
        commands = runtime_store.claim_pending_commands(limit=20)
        for item in commands:
            try:
                command = item["command"]
                if command == "PAUSE_TRADING":
                    self._manual_pause = True
                    self._pause_reason = "MANUAL"
                    self.state_manager.set_alert("WARNING", emergency=False, trading_paused=True)
                    result = {"ok": True, "command": command}
                elif command == "RESUME_TRADING":
                    result = {**self.resume_trading(source="control_api"), "command": command}
                elif command in {"CLOSE_ALL_POSITIONS", "FLATTEN_ALL", "CLOSE_ALL"}:
                    payload = item.get("payload") or {}
                    result = self.flatten_all_positions(
                        reason=f"control:{command}",
                        source="control_api",
                        trigger_text=str(payload.get("note") or command),
                    )
                else:
                    result = {"ok": False, "error": f"unsupported command: {command}"}
                runtime_store.complete_command(item["id"], result=result, ok=result.get("ok", False))
            except Exception as exc:
                runtime_store.complete_command(item["id"], result={"ok": False, "error": str(exc)}, ok=False)

    def _run_hq_spot_strategy(self, prices, spot_account, truth_status=None):
        if not self.spot_client.is_configured():
            self.state_manager.set_module_health("hq_spot", "DISABLED")
            return
        ext_alerts = list(((self.growth_status or {}).get("external_market_intel") or {}).get("alerts") or [])
        if any("btc_exchange_inflow_spike" in item for item in ext_alerts):
            self.state_manager.set_module_health("hq_spot", "CAUTION")
            self.state_manager.update_fleet("HQ", status="MONITORING", last_signal="HOLD", last_reason="cryptoquant_whale_inflow")
            return
        if truth_status and not truth_status.get("spot_ready_for_ai", truth_status.get("fresh_for_ai", False)):
            self.state_manager.set_module_health("hq_spot", "DEGRADED")
            return

        usdt_free = float(spot_account["balances"].get("USDT", {}).get("free", 0.0) or 0.0)
        trade_budget = max(25.0, usdt_free * 0.08)
        threshold = float(os.getenv("NEXUS_HQ_SPOT_THRESHOLD", "0.0035"))
        cooldown = int(os.getenv("NEXUS_HQ_SPOT_COOLDOWN_SECONDS", "600"))

        for fleet in HQ_SPOT_SYMBOLS:
            current = float(prices.get(fleet, {}).get("price", 0.0) or 0.0)
            previous = float(self._previous_prices.get(fleet, current) or current)
            if not current or not previous:
                continue
            if time.time() - self.hq_spot_last_action.get(fleet, 0.0) < cooldown:
                continue

            change = (current - previous) / previous if previous else 0.0
            asset_qty = float(spot_account["balances"].get(fleet, {}).get("free", 0.0) or 0.0)

            if change >= threshold and usdt_free >= 50:
                quote_amount = min(trade_budget, usdt_free * 0.2)
                validation = self.validation_pipeline.evaluate(
                    {
                        "fleet": "HQ",
                        "symbol": self.spot_client.resolve_symbol(fleet),
                        "market_type": "spot",
                        "side": "BUY",
                        "price": current,
                        "margin": quote_amount,
                        "strategy_key": "hq_spot_momentum",
                        "reason": f"hq_spot_momentum_buy:{change:.4f}",
                        "timestamp": _now(),
                    },
                    market_context={
                        "market_regime": "hq_spot",
                        "spread_bps": 0.0,
                        "top5_cross_notional": max(quote_amount * 20.0, 25000.0),
                        "liquidity_status": "healthy",
                    },
                    truth_status=truth_status or {},
                    recent_orders=self.hq_spot_orders,
                    recent_trades=self.hq_spot_trades,
                    portfolio_status=self.portfolio_status,
                )
                if not validation.get("approved"):
                    self._append_alert("INFO", f"HQ {fleet} spot buy blocked: {validation.get('reason')}")
                    continue
                risk_allowed, risk_reason = self.risk_engine.validate_order(
                    {
                        "fleet": "HQ",
                        "market_type": "spot",
                        "margin": quote_amount,
                        "available_cash": usdt_free,
                        "max_cash_pct": 0.25,
                    }
                )
                if not risk_allowed:
                    self._append_alert("INFO", f"HQ {fleet} spot buy risk-blocked: {risk_reason}")
                    continue
                try:
                    self._place_hq_spot_buy(
                        fleet,
                        current,
                        quote_amount,
                        f"hq_spot_momentum_buy:{change:.4f}",
                        validation_result=validation,
                    )
                    self.hq_spot_last_action[fleet] = time.time()
                    usdt_free -= quote_amount
                except Exception as exc:
                    self._append_alert("WARNING", f"HQ {fleet} spot buy failed: {exc}")
            elif change <= -threshold and asset_qty * current >= 50:
                sell_qty = self.spot_client.normalize_quantity(
                    self.spot_client.resolve_symbol(fleet),
                    max(asset_qty * 0.25, 0.0),
                )
                if sell_qty > 0:
                    validation = self.validation_pipeline.evaluate(
                        {
                            "fleet": "HQ",
                            "symbol": self.spot_client.resolve_symbol(fleet),
                            "market_type": "spot",
                            "side": "SELL",
                            "price": current,
                            "margin": sell_qty * current,
                            "strategy_key": "hq_spot_momentum",
                            "reason": f"hq_spot_risk_sell:{change:.4f}",
                            "timestamp": _now(),
                        },
                        market_context={
                            "market_regime": "hq_spot",
                            "spread_bps": 0.0,
                            "top5_cross_notional": max(sell_qty * current * 20.0, 25000.0),
                            "liquidity_status": "healthy",
                        },
                        truth_status=truth_status or {},
                        recent_orders=self.hq_spot_orders,
                        recent_trades=self.hq_spot_trades,
                        portfolio_status=self.portfolio_status,
                    )
                    if not validation.get("approved"):
                        self._append_alert("INFO", f"HQ {fleet} spot sell blocked: {validation.get('reason')}")
                        continue
                    try:
                        self._place_hq_spot_sell(
                            fleet,
                            current,
                            sell_qty,
                            f"hq_spot_risk_sell:{change:.4f}",
                            validation_result=validation,
                        )
                        self.hq_spot_last_action[fleet] = time.time()
                    except Exception as exc:
                        self._append_alert("WARNING", f"HQ {fleet} spot sell failed: {exc}")

        self.state_manager.set_module_health("hq_spot", "ONLINE")

    def _bootstrap_live_activity(self, prices, spot_account, truth_status=None):
        if self._bootstrapped:
            return
        if os.getenv("NEXUS_BOOTSTRAP_TRADES", "1").strip().lower() in {"0", "false", "no"}:
            self._bootstrapped = True
            return

        try:
            if (
                self.spot_client.is_configured()
                and truth_status
                and truth_status.get("spot_ready_for_ai", False)
                and not self.hq_spot_orders
            ):
                btc_price = float(prices.get("BTC", {}).get("price", 0.0) or 0.0)
                usdt_free = float(spot_account.get("balances", {}).get("USDT", {}).get("free", 0.0) or 0.0)
                if btc_price > 0 and usdt_free >= 25:
                    self._place_hq_spot_buy("BTC", btc_price, 25.0, "bootstrap_spot_connectivity_trade")
        except Exception as exc:
            self._append_alert("WARNING", f"HQ bootstrap spot trade failed: {exc}")

        try:
            if (
                self.futures_client.is_configured()
                and self.execution_router
                and truth_status
                and truth_status.get("futures_ready_for_ai", False)
                and not self.execution_engine.recent_orders(limit=1)
            ):
                btc_price = float(prices.get("BTC", {}).get("price", 0.0) or 0.0)
                request = {"fleet": "BTC", "side": "BUY", "price": btc_price, "margin": 20.0, "leverage": 15.0}
                allowed, risk_reason = self.risk_engine.validate_order(request)
                if allowed and btc_price > 0:
                    self._record_trade_journal(
                        {
                            "symbol": self.futures_client.resolve_symbol("BTC"),
                            "market_type": "futures",
                            "fleet": "BTC",
                            "direction": "BUY",
                            "entry_reason": "bootstrap_futures_connectivity_trade",
                            "signal_sources": ["bootstrap"],
                            "confidence_score": 0.5,
                            "risk_score": 0.2,
                            "market_regime": "bootstrap",
                            "news_score": 0.0,
                            "whale_score": 0.0,
                            "funding_score": 0.0,
                            "technical_score": 0.5,
                            "position_size": 20.0,
                            "leverage": 15.0,
                        }
                    )
                    self.execution_router.route_futures_order(
                        fleet="BTC",
                        side="BUY",
                        price=btc_price,
                        margin=20.0,
                        reason="bootstrap_futures_connectivity_trade",
                        confidence_score=0.5,
                        market_regime="bootstrap",
                        risk_context={},
                    )
                    self.state_manager.update_fleet("BTC", status="TRADING", last_signal="BUY", last_reason="bootstrap_futures_connectivity_trade")
                else:
                    self._append_alert("WARNING", f"BTC bootstrap futures blocked: {risk_reason}")
        except Exception as exc:
            self._append_alert("WARNING", f"BTC bootstrap futures trade failed: {exc}")

        self._bootstrapped = True

    def _place_hq_spot_buy(self, fleet, price, quote_amount, reason, validation_result=None):
        symbol = self.spot_client.resolve_symbol(fleet)
        self._record_trade_journal(
            {
                "symbol": symbol,
                "market_type": "spot",
                "fleet": "HQ",
                "direction": "BUY",
                "entry_reason": reason,
                "signal_sources": ["hq_spot"],
                "confidence_score": 0.55,
                "risk_score": 0.15,
                "market_regime": "hq_spot",
                "news_score": 0.0,
                "whale_score": 0.0,
                "funding_score": 0.0,
                "technical_score": 0.55,
                "position_size": quote_amount,
                "leverage": 1.0,
                "strategy_key": "hq_spot_momentum",
                "validation": validation_result or {},
            }
        )
        if self.execution_router:
            order, _position = self.execution_router.route_spot_order(
                fleet="HQ",
                side="BUY",
                price=price,
                margin=quote_amount,
                reason=reason,
                actor="strategy",
                symbol=symbol,
            )
            order["fleet"] = "HQ"
            order["desk"] = "SPOT"
            order["quote_amount"] = round(float(order.get("margin", quote_amount) or quote_amount), 6)
            self.hq_spot_orders.insert(0, order)
            self.hq_spot_orders = self.hq_spot_orders[:120]
            self.hq_spot_trades.insert(0, {**order, "event": "OPEN"})
            self.hq_spot_trades = self.hq_spot_trades[:120]
            return
        order_id = f"hq_spot_buy_{fleet.lower()}_{int(time.time())}"
        response = self.spot_client.place_market_buy(symbol, quote_amount, client_order_id=order_id)
        fill_price = self.spot_client.extract_fill_price(response, price)
        executed_qty = float(response.get("executedQty") or (quote_amount / price))
        order = {
            "id": order_id,
            "time": _now(),
            "fleet": "HQ",
            "desk": "SPOT",
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "price": round(fill_price, 10),
            "quote_amount": round(quote_amount, 6),
            "margin": round(quote_amount, 6),
            "leverage": 1.0,
            "quantity": round(executed_qty, 10),
            "status": str(response.get("status", "FILLED")),
            "reason": reason,
            "execution_source": "binance_spot_testnet",
            "external_order_id": response.get("orderId"),
        }
        order["desk"] = "SPOT"
        order["quote_amount"] = round(float(order.get("margin", quote_amount) or quote_amount), 6)
        self.hq_spot_orders.insert(0, order)
        self.hq_spot_orders = self.hq_spot_orders[:120]
        self.hq_spot_trades.insert(0, {**order, "event": "OPEN"})
        self.hq_spot_trades = self.hq_spot_trades[:120]

    def _place_hq_spot_sell(self, fleet, price, quantity, reason, validation_result=None):
        symbol = self.spot_client.resolve_symbol(fleet)
        self._record_trade_journal(
            {
                "symbol": symbol,
                "market_type": "spot",
                "fleet": "HQ",
                "direction": "SELL",
                "entry_reason": reason,
                "signal_sources": ["hq_spot"],
                "confidence_score": 0.5,
                "risk_score": 0.2,
                "market_regime": "hq_spot",
                "news_score": 0.0,
                "whale_score": 0.0,
                "funding_score": 0.0,
                "technical_score": 0.5,
                "position_size": quantity * price,
                "leverage": 1.0,
                "strategy_key": "hq_spot_momentum",
                "validation": validation_result or {},
            }
        )
        order_id = f"hq_spot_sell_{fleet.lower()}_{int(time.time())}"
        response = self.spot_client.place_market_sell(symbol, quantity, client_order_id=order_id)
        fill_price = self.spot_client.extract_fill_price(response, price)
        executed_qty = float(response.get("executedQty") or quantity)
        order = {
            "id": order_id,
            "time": _now(),
            "fleet": "HQ",
            "desk": "SPOT",
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "price": round(fill_price, 10),
            "margin": round(fill_price * executed_qty, 6),
            "quote_amount": round(fill_price * executed_qty, 6),
            "leverage": 1.0,
            "quantity": round(executed_qty, 10),
            "status": str(response.get("status", "FILLED")),
            "reason": reason,
            "execution_source": "binance_spot_testnet",
            "external_order_id": response.get("orderId"),
        }
        self.hq_spot_orders.insert(0, order)
        self.hq_spot_orders = self.hq_spot_orders[:120]
        self.hq_spot_trades.insert(0, {**order, "event": "CLOSE"})
        self.hq_spot_trades = self.hq_spot_trades[:120]
        self._record_trade_result(
            {
                "order_id": order["id"],
                "symbol": symbol,
                "market_type": "spot",
                "fleet": "HQ",
                "entry_price": order["price"],
                "exit_price": order["price"],
                "pnl": 0.0,
                "fee": 0.0,
                "slippage": 0.0,
                "holding_time": 0.0,
                "max_drawdown": 0.0,
                "max_favorable_excursion": 0.0,
                "exit_reason": reason,
                "final_leverage": 1.0,
                "confidence_score": 0.5,
                "market_regime": "hq_spot",
            },
            context={},
        )

    def _run_fleet_strategies(self, prices, market_contexts, truth_status=None, exits_only=False):
        futures_ready = truth_status.get("futures_ready_for_ai", False) if truth_status else True
        portfolio_restrictions = dict((self.portfolio_status or {}).get("fleet_restrictions", {}) or {})
        portfolio_capital_plans = dict((self.portfolio_status or {}).get("capital_adjustments", {}) or {})
        meeting_notes = self._resolve_meeting_notes()
        growth_directives = dict(self.growth_status or {})
        if growth_directives.get("block_new_entries"):
            for fleet in FLEETS:
                if not self.position_manager.get_by_fleet(fleet):
                    self.state_manager.update_fleet(
                        fleet,
                        status="BLOCKED",
                        last_signal="HOLD",
                        last_reason=f"growth_guard:{growth_directives.get('block_reason', 'blocked')}",
                    )
        for fleet in FLEETS:
            if self._fleet_blocked_by_meeting(fleet):
                self.state_manager.update_fleet(fleet, status="BLOCKED", last_signal="HOLD", last_reason="meeting_execution_block")
                continue
            current = float(prices.get(fleet, {}).get("price", 0.0) or 0.0)
            previous = float(self._previous_prices.get(fleet, current) or current)
            signal = self.signal_fusion.fuse(
                fleet=fleet,
                price_now=current,
                price_prev=previous,
                news_items=self.latest_news,
                alert_level=self.state_manager.snapshot().get("alert_level", "NORMAL"),
                market_context=market_contexts.get(fleet, {}),
                meeting_notes=meeting_notes,
            )

            engine = self.strategy_engines[fleet]
            # Even when truth layer is degraded, still allow exit management to prevent liquidations.
            try:
                if not futures_ready:
                    self.state_manager.update_fleet(fleet, status="DEGRADED", last_signal="HOLD", last_reason="truth_layer_not_ready")
                    exit_trades = engine.manage_position_exits(
                        {"action": "HOLD", "confidence": 0.0, "reason": "truth_layer_degraded_exit_check"},
                        current,
                    )
                else:
                    exit_trades = engine.manage_position_exits(signal, current)
            except Exception as exc:
                exit_trades = []
                print(f"[nexus_runtime] exit check failed for {fleet}: {exc}")
                self._append_alert("WARNING", f"{fleet} exit check failed: {exc}")
            for closed_trade in exit_trades:
                close_context = dict(market_contexts.get(fleet, {}))
                close_context["setup_type"] = self.validation_pipeline.decision_quality_engine.setup_classifier.classify(
                    fleet,
                    signal,
                    close_context,
                    self.latest_news,
                    {"severity": "NORMAL"},
                    {"severity": "NORMAL"},
                )
                close_context["side"] = closed_trade.get("side")
                self._record_trade_result(
                    {
                        "order_id": closed_trade.get("id"),
                        "symbol": closed_trade.get("symbol"),
                        "market_type": closed_trade.get("market_type", "futures"),
                        "fleet": fleet,
                        "entry_price": closed_trade.get("entry_price"),
                        "exit_price": closed_trade.get("exit_price"),
                        "pnl": closed_trade.get("pnl"),
                        "fee": closed_trade.get("commission", 0.0),
                        "slippage": 0.0,
                        "holding_time": 0.0,
                        "max_drawdown": 0.0,
                        "max_favorable_excursion": 0.0,
                        "exit_reason": closed_trade.get("reason"),
                        "exit_class": closed_trade.get("exit_class"),
                        "pnl_r": closed_trade.get("pnl_r"),
                        "final_leverage": closed_trade.get("leverage", 0.0),
                        "confidence_score": float(signal.get("confidence", 0.0) or 0.0),
                        "market_regime": market_contexts.get(fleet, {}).get("market_regime", "normal"),
                        "strategy_key": f"{fleet.lower()}_adaptive_strategy",
                        "setup_type": close_context.get("setup_type"),
                        "side": closed_trade.get("side"),
                    },
                    context=close_context,
                )
                if closed_trade.get("event") == "CLOSE":
                    self.state_manager.update_fleet(fleet, status="EXITED", last_signal=signal["action"], last_reason=closed_trade.get("reason"))

            if exits_only:
                if self.position_manager.get_by_fleet(fleet):
                    self.state_manager.update_fleet(fleet, status="TRADING", last_signal=signal["action"], last_reason=signal["reason"])
                continue

            if self.position_manager.get_by_fleet(fleet):
                self.state_manager.update_fleet(fleet, status="TRADING", last_signal=signal["action"], last_reason=signal["reason"])
                continue

            if growth_directives.get("block_new_entries"):
                self.state_manager.update_fleet(
                    fleet,
                    status="BLOCKED",
                    last_signal="HOLD",
                    last_reason=f"growth_guard:{growth_directives.get('block_reason', 'blocked')}",
                )
                continue

            request = engine.build_open_request(signal, current, market_context=market_contexts.get(fleet, {}))
            if not request:
                self.state_manager.update_fleet(fleet, status="MONITORING", last_signal=signal["action"], last_reason=engine.last_reason or signal["reason"])
                continue

            fleet_restriction = portfolio_restrictions.get(fleet, {})
            if not fleet_restriction.get("allowed_new_entries", True):
                self.state_manager.update_fleet(fleet, status="BLOCKED", last_signal="REJECTED", last_reason="portfolio_governor_block")
                continue

            capital_plan = portfolio_capital_plans.get(fleet, {})
            capital_multiplier = float(capital_plan.get("capital_multiplier", 1.0) or 1.0)
            if capital_multiplier != 1.0:
                request["margin"] = round(float(request["margin"]) * capital_multiplier, 4)
            if capital_plan.get("leverage_cap") is not None:
                request["leverage"] = min(float(request["leverage"]), float(capital_plan.get("leverage_cap") or request["leverage"]))
            request["portfolio_governance"] = {
                "restriction": fleet_restriction,
                "capital_plan": capital_plan,
            }

            growth_multiplier = float(growth_directives.get("position_multiplier", 1.0) or 1.0)
            if growth_multiplier != 1.0:
                request["margin"] = round(float(request["margin"]) * growth_multiplier, 4)
            growth_leverage_cap = growth_directives.get("max_leverage")
            if growth_leverage_cap is not None:
                request["leverage"] = min(float(request["leverage"]), float(growth_leverage_cap))

            request = self._apply_confidence_sizing_pipeline(
                request,
                market_contexts,
                deployable_pool=float((self.growth_status or {}).get("deployable_pool", 0.0) or 0.0),
                futures_account=futures_account,
            )

            request["symbol"] = self.futures_client.resolve_symbol(fleet)
            request["market_type"] = "futures"
            growth_context = self._build_growth_context(fleet, signal, market_contexts.get(fleet, {}), request)
            validation = self.validation_pipeline.evaluate(
                request,
                market_context=market_contexts.get(fleet, {}),
                truth_status=truth_status or {},
                recent_orders=self.futures_live_orders if self.futures_client.is_configured() else self.execution_engine.recent_orders(limit=120),
                recent_trades=self.futures_live_trades if self.futures_client.is_configured() else self.execution_engine.recent_trades(limit=120),
                portfolio_status=self.portfolio_status,
                growth_context=growth_context,
            )
            validation = self._govern_trade_validation(request, validation, market_contexts.get(fleet, {}))
            if not validation.get("approved"):
                self.state_manager.update_fleet(fleet, status="BLOCKED", last_signal="REJECTED", last_reason=f"validation:{validation.get('reason')}")
                continue

            churn_ok, churn_reason = self.fee_churn_guard.allow_open(request)
            if not churn_ok:
                self.state_manager.update_fleet(
                    fleet,
                    status="BLOCKED",
                    last_signal="REJECTED",
                    last_reason=f"fee_churn:{churn_reason}",
                )
                continue

            allowed, risk_reason = self.risk_engine.validate_order(request)
            if not allowed:
                self.state_manager.update_fleet(fleet, status="BLOCKED", last_signal="REJECTED", last_reason=risk_reason)
                continue

            try:
                risk_context = dict(market_contexts.get(fleet, {}))
                bracket = self.futures_client.get_symbol_leverage_bracket(
                    self.futures_client.resolve_symbol(fleet),
                    estimated_notional=float(request["margin"]) * float(request["leverage"]),
                )
                risk_context["symbol_max_leverage"] = bracket.get("initialLeverage")
                self._record_trade_journal(
                    {
                        "symbol": self.futures_client.resolve_symbol(fleet),
                        "market_type": "futures",
                        "fleet": fleet,
                        "direction": request["side"],
                        "entry_reason": request["reason"],
                        "signal_sources": ["signal_fusion"],
                        "confidence_score": request.get("adjusted_confidence", request.get("raw_confidence", 0.0)),
                        "risk_score": 1.0 - float(request.get("adjusted_confidence", request.get("raw_confidence", 0.0)) or 0.0),
                        "market_regime": risk_context.get("market_regime", "normal"),
                        "news_score": float(risk_context.get("news_score", 0.0) or 0.0),
                        "whale_score": float(risk_context.get("whale_score", 0.0) or 0.0),
                          "funding_score": float(risk_context.get("funding_score", 0.0) or 0.0),
                          "technical_score": float(risk_context.get("technical_score", request.get("adjusted_confidence", 0.0)) or 0.0),
                          "position_size": request["margin"],
                          "leverage": request["leverage"],
                          "strategy_key": request.get("strategy_key"),
                          "validation": validation,
                      }
                  )
                if self.execution_router:
                    order, _position = self.execution_router.route_futures_order(
                        fleet=fleet,
                        side=request["side"],
                        price=current,
                        margin=request["margin"],
                        reason=request["reason"],
                        confidence_score=request.get("adjusted_confidence", request.get("raw_confidence", 0.0)),
                        market_regime=risk_context.get("market_regime", "normal"),
                        risk_context=risk_context,
                    )
                else:
                    order, _position = self.execution_engine.market_order(
                        fleet=fleet,
                        side=request["side"],
                        price=current,
                        margin=request["margin"],
                        leverage=request["leverage"],
                        reason=request["reason"],
                    )
                self.state_manager.update_fleet(fleet, status="TRADING", last_signal=request["side"], last_reason=order["reason"])
            except Exception as exc:
                self.state_manager.update_fleet(fleet, status="ERROR", last_signal="ERROR", last_reason=str(exc))
                self._append_alert("WARNING", f"{fleet} order failed: {exc}")

    def _radar_trade_candidates(self):
        return self.radar_llm_bridge.merge_with_scan_candidates(
            self.radar_scan,
            getattr(self, "_radar_llm_proposals", []) or [],
        )

    def _run_radar_dispatch(self, prices, market_contexts, truth_status=None, exits_only=False):
        futures_ready = truth_status.get("futures_ready_for_ai", False) if truth_status else True
        if not futures_ready:
            return
        growth_directives = dict(self.growth_status or {})
        symbol_prices = self._build_symbol_prices(prices)
        execution_engine = self.execution_router.futures_engine if self.execution_router else self.execution_engine
        radar_positions = self.position_manager.get_by_fleet("RADAR")

        for position in list(radar_positions):
            symbol = str(position.get("symbol") or "").upper().replace("/", "")
            current = float(symbol_prices.get(symbol, position.get("mark_price", 0.0)) or 0.0)
            if current <= 0:
                continue
            signal = {"action": "HOLD", "confidence": 0.0, "reason": "radar_hold"}
            for trade in self.radar_dispatch.manage_position_exits(
                position,
                current,
                signal=signal,
                execution_engine=execution_engine,
                position_manager=self.position_manager,
            ):
                self._record_trade_result(
                    {
                        "order_id": trade.get("id"),
                        "symbol": trade.get("symbol"),
                        "market_type": "futures",
                        "fleet": "RADAR",
                        "entry_price": trade.get("entry_price"),
                        "exit_price": trade.get("exit_price"),
                        "pnl": trade.get("pnl"),
                        "exit_reason": trade.get("reason"),
                        "exit_class": trade.get("exit_class"),
                        "pnl_r": trade.get("pnl_r"),
                        "strategy_key": "radar_market_scan_strategy",
                        "market_regime": "radar_alt",
                        "side": trade.get("side"),
                    },
                    context={"setup_type": "radar_dispatch", "market_regime": "radar_alt"},
                )

        if exits_only:
            return

        if growth_directives.get("block_new_entries"):
            return
        if self._fleet_blocked_by_meeting("RADAR"):
            return

        radar_guidance = self.learning_feedback.get_strategy_guidance(
            "RADAR",
            "radar_market_scan_strategy",
            "radar_alt",
            market_context=market_contexts.get("RADAR", {}) if isinstance(market_contexts, dict) else {},
        )

        open_symbols = {str(item.get("symbol") or "").upper().replace("/", "") for item in self.position_manager.get_by_fleet("RADAR")}
        if len(open_symbols) >= RADAR_MAX_OPEN_POSITIONS:
            return

        for candidate in self._radar_trade_candidates():
            symbol = str(candidate.get("symbol") or "").upper()
            if symbol in open_symbols:
                continue
            if not self.radar_dispatch.can_open_symbol(symbol, learning_guidance=radar_guidance):
                continue
            current = float(symbol_prices.get(symbol, 0.0) or 0.0)
            if current <= 0:
                continue
            alt_context = self.market_context_service.build_symbol_context(symbol, prices) or {}
            request = self.radar_dispatch.build_open_request(
                candidate,
                current,
                alt_context,
                self.ledger,
                growth_directives=growth_directives,
                learning_guidance=radar_guidance,
            )
            if not request:
                continue
            request = self._apply_volatility_position_sizing(request, alt_context, market_contexts)
            signal = self.radar_dispatch.build_signal_from_candidate(candidate)
            growth_context = self._build_growth_context("RADAR", signal, alt_context, request)
            validation = self.validation_pipeline.evaluate(
                request,
                market_context=alt_context,
                truth_status=truth_status or {},
                recent_orders=self.futures_live_orders if self.futures_client.is_configured() else self.execution_engine.recent_orders(limit=120),
                recent_trades=self.futures_live_trades if self.futures_client.is_configured() else self.execution_engine.recent_trades(limit=120),
                portfolio_status=self.portfolio_status,
                growth_context=growth_context,
            )
            validation = self._govern_trade_validation(request, validation, alt_context)
            request["decision_source"] = request.get("decision_source") or "radar_scan"
            self._append_decision_audit(request, validation, alt_context, decision_source=request["decision_source"])
            if not validation.get("approved"):
                continue
            churn_ok, churn_reason = self.fee_churn_guard.allow_open(request)
            if not churn_ok:
                self._append_decision_audit(
                    request,
                    {
                        **validation,
                        "approved": False,
                        "reason": churn_reason,
                        "reject_layer": "fee_churn_guard",
                    },
                    alt_context,
                    decision_source=request.get("decision_source", "radar_scan"),
                )
                continue
            allowed, risk_reason = self.risk_engine.validate_order(request)
            if not allowed:
                continue
            try:
                if self.execution_router:
                    order, _position = self.execution_router.route_futures_order(
                        fleet="RADAR",
                        side=request["side"],
                        price=current,
                        margin=request["margin"],
                        reason=request["reason"],
                        confidence_score=request.get("adjusted_confidence", 0.0),
                        market_regime=alt_context.get("market_regime", "normal"),
                        risk_context=alt_context,
                        symbol_override=symbol,
                        capital_pool="radar",
                    )
                else:
                    order, _position = execution_engine.market_order(
                        fleet="RADAR",
                        side=request["side"],
                        price=current,
                        margin=request["margin"],
                        leverage=request["leverage"],
                        reason=request["reason"],
                        symbol_override=symbol,
                        capital_pool="radar",
                    )
                self.radar_dispatch.mark_open(symbol)
                open_symbols.add(symbol)
            except Exception as exc:
                self._append_alert("WARNING", f"RADAR dispatch failed for {symbol}: {exc}")

    def _sync_spot_account(self, prices):
        if not self.spot_client.is_configured():
            empty_snapshot = self.account_sync.build_spot_snapshot({}, [], [], 0.0, 0, sync_error="spot_client_not_configured")
            self._last_binance_sync["spot"] = empty_snapshot.to_dict()
            return {
                "balances": {},
                "stable_free": 0.0,
                "stable_total": 0.0,
                "usdt_free": 0.0,
                "usdt_total": 0.0,
                "spot_total": 0.0,
                "holdings": [],
                "account_fingerprint": "",
                "update_time": 0,
                "open_orders": [],
                "trade_history": [],
                "sync_status": "disconnected",
                "sync_error": "spot_client_not_configured",
            }
        try:
            current_sync_ms = int(time.time() * 1000)
            account = self.spot_client.get_account()
            balances = {
                item["asset"]: {
                    "free": float(item.get("free", 0.0) or 0.0),
                    "locked": float(item.get("locked", 0.0) or 0.0),
                }
                for item in account.get("balances", [])
                if float(item.get("free", 0.0) or 0.0) or float(item.get("locked", 0.0) or 0.0)
            }
            truth_view = self.spot_truth_service.build_view(balances, prices)
            stable_total = float(truth_view.get("stable_total", 0.0) or 0.0)
            stable_free = float(truth_view.get("stable_free", 0.0) or 0.0)
            spot_total = float(truth_view.get("spot_total", 0.0) or 0.0)
            holdings = list(truth_view.get("visible_holdings", []))
            symbols = [self.spot_client.resolve_symbol(asset) for asset in HQ_SPOT_SYMBOLS]
            open_orders, trade_history = self.order_sync.sync_spot_orders_and_trades(symbols)
            sync_snapshot = self.account_sync.build_spot_snapshot(
                balances=balances,
                open_orders=open_orders,
                trades=trade_history,
                total_equity=spot_total,
                last_sync_time=current_sync_ms,
            )
            self._last_binance_sync["spot"] = sync_snapshot.to_dict()
            self.state_manager.set_module_health("spot_sync", "ONLINE")
            return {
                "balances": balances,
                "stable_free": round(stable_free, 8),
                "stable_total": round(stable_total, 8),
                "usdt_free": float(balances.get("USDT", {}).get("free", 0.0) or 0.0),
                "usdt_total": float(truth_view.get("usdt_total", 0.0) or 0.0),
                "usdc_total": float(truth_view.get("usdc_total", 0.0) or 0.0),
                "spot_total": round(float(truth_view.get("stable_total", spot_total) or 0.0), 4),
                "spot_stable_total": round(float(truth_view.get("stable_total", stable_total) or 0.0), 4),
                "holdings": holdings,
                "truth_scope": truth_view.get("truth_mode", HQ_SPOT_TRUTH_MODE),
                "truth_assets": list(truth_view.get("truth_assets", [])),
                "allowed_assets": list(truth_view.get("allowed_assets", [])),
                "excluded_assets_count": int(truth_view.get("excluded_assets_count", 0) or 0),
                "holdings_total": float(truth_view.get("visible_holdings_total", 0.0) or 0.0),
                "truth_warning": truth_view.get("warning", ""),
                "account_fingerprint": self._build_spot_account_fingerprint(balances),
                "update_time": current_sync_ms,
                "open_orders": open_orders,
                "trade_history": trade_history,
                "sync_status": sync_snapshot.sync_status,
                "sync_error": sync_snapshot.sync_error,
            }
        except Exception as exc:
            self.state_manager.set_module_health("spot_sync", f"ERROR: {exc}")
            self._append_alert("WARNING", f"Spot sync failed: {exc}")
            sync_snapshot = self.account_sync.build_spot_snapshot({}, [], [], 0.0, 0, sync_error=str(exc))
            self._last_binance_sync["spot"] = sync_snapshot.to_dict()
            return {
                "balances": {},
                "stable_free": 0.0,
                "stable_total": 0.0,
                "usdt_free": 0.0,
                "usdt_total": 0.0,
                "spot_total": 0.0,
                "holdings": [],
                "truth_scope": HQ_SPOT_TRUTH_MODE,
                "truth_assets": [],
                "allowed_assets": list(HQ_SPOT_ALLOWED_ASSETS),
                "excluded_assets_count": 0,
                "holdings_total": 0.0,
                "truth_warning": "",
                "account_fingerprint": "",
                "update_time": 0,
                "open_orders": [],
                "trade_history": [],
                "sync_status": "degraded",
                "sync_error": str(exc),
            }

    def _sync_futures_account(self, prices):
        if not self.futures_client.is_configured():
            empty_snapshot = self.account_sync.build_futures_snapshot({}, [], [], [], [], 0, sync_error="futures_client_not_configured")
            self._last_binance_sync["futures"] = empty_snapshot.to_dict()
            return {
                "wallet_total": 0.0,
                "margin_total": 0.0,
                "mobile_wallet_balance": 0.0,
                "mobile_margin_balance": 0.0,
                "wallet_balance": 0.0,
                "margin_balance": 0.0,
                "exchange_wallet_balance": 0.0,
                "exchange_margin_balance": 0.0,
                "available_balance": 0.0,
                "unrealized_pnl": 0.0,
                "positions": [],
                "balance_assets": [],
                "account_alias": "",
                "account_fingerprint": "",
                "positions_fingerprint": "",
                "update_time": 0,
                "open_orders": [],
                "fills": [],
                "funding_rates": [],
                "sync_status": "disconnected",
                "sync_error": "futures_client_not_configured",
            }
        try:
            current_sync_ms = int(time.time() * 1000)
            account_info = self.futures_client.get_account_information()
            balances = self.futures_client.get_balances()
            symbol_map = {self.futures_client.resolve_symbol(fleet): fleet for fleet in FLEETS}
            wallet_total = 0.0
            available = 0.0
            stable_wallet_total = 0.0
            stable_available_total = 0.0
            collateral_total = 0.0
            balance_assets = []
            account_alias = ""
            balance_update_time = 0
            for item in balances or []:
                asset = item.get("asset", "")
                raw_balance = float(item.get("balance", 0.0) or 0.0)
                raw_available = float(item.get("availableBalance", 0.0) or 0.0)
                account_alias = account_alias or str(item.get("accountAlias", "") or "")
                balance_update_time = max(balance_update_time, int(item.get("updateTime") or 0))
                if asset in STABLE_ASSETS:
                    px = 1.0
                else:
                    px = float(prices.get(asset, {}).get("price", 0.0) or 0.0)
                asset_balance_value = raw_balance * px
                asset_available_value = raw_available * px
                wallet_total += asset_balance_value
                available += asset_available_value
                if asset in STABLE_ASSETS:
                    stable_wallet_total += asset_balance_value
                    stable_available_total += asset_available_value
                else:
                    collateral_total += asset_balance_value
                if raw_balance:
                    balance_assets.append(
                        {
                            "asset": asset,
                            "balance": round(raw_balance, 8),
                            "available_balance": round(raw_available, 8),
                            "cross_wallet_balance": round(_safe_float(item.get("crossWalletBalance")), 8),
                            "cross_unrealized_pnl": round(_safe_float(item.get("crossUnPnl")), 8),
                            "value_usd": round(asset_balance_value, 8),
                        }
                    )
            positions = []
            unrealized = 0.0
            position_update_time = 0
            for item in self.futures_client.get_all_position_risk():
                symbol = str(item.get("symbol") or "").upper()
                position_amt = float(item.get("positionAmt", 0.0) or 0.0)
                if abs(position_amt) < 1e-12:
                    continue
                pnl = float(item.get("unRealizedProfit", 0.0) or 0.0)
                unrealized += pnl
                position_update_time = max(position_update_time, int(item.get("updateTime") or 0))
                fleet = fleet_for_exchange_position(symbol, symbol_map)
                side = "BUY" if position_amt > 0 else "SELL"
                leverage = max(_safe_float(item.get("leverage")) or 1.0, 1.0)
                margin = _safe_float(item.get("isolatedMargin"))
                if margin <= 0:
                    margin = _safe_float(item.get("positionInitialMargin"))
                if margin <= 0:
                    notional = abs(_safe_float(item.get("notional")))
                    if notional > 0 and leverage > 0:
                        margin = notional / leverage
                positions.append(
                    {
                        "fleet": fleet,
                        "symbol": symbol,
                        "side": side,
                        "quantity": round(abs(position_amt), 10),
                        "signed_quantity": round(position_amt, 10),
                        "entry_price": float(item.get("entryPrice", 0.0) or 0.0),
                        "mark_price": float(item.get("markPrice", 0.0) or 0.0),
                        "unrealized_pnl": pnl,
                        "leverage": leverage,
                        "margin": round(margin, 6),
                        "liquidation_price": float(item.get("liquidationPrice", 0.0) or 0.0),
                        "margin_ratio": float(item.get("maintMargin", 0.0) or 0.0),
                        "margin_type": str(item.get("marginType", "isolated")).lower(),
                        "position_side": item.get("positionSide", "BOTH"),
                    }
                )
            exchange_wallet_balance = _safe_float(account_info.get("totalWalletBalance"))
            exchange_margin_balance = _safe_float(account_info.get("totalMarginBalance"))
            display_wallet_balance = exchange_wallet_balance if exchange_wallet_balance > 0 else wallet_total
            mobile_wallet_balance = wallet_total
            mobile_margin_balance = wallet_total + unrealized
            stable_margin_balance = stable_wallet_total + unrealized
            account_unrealized = _safe_float(account_info.get("totalUnrealizedProfit"))
            if account_unrealized:
                unrealized = account_unrealized
                mobile_margin_balance = wallet_total + unrealized
                stable_margin_balance = stable_wallet_total + unrealized
            display_margin_balance = exchange_margin_balance if exchange_margin_balance > 0 else (display_wallet_balance + unrealized)
            available_balance = _safe_float(account_info.get("availableBalance"))
            exchange_account = {
                "totalWalletBalance": exchange_wallet_balance,
                "totalMarginBalance": exchange_margin_balance,
                "totalUnrealizedProfit": unrealized,
                "availableBalance": available_balance,
                "totalMaintMargin": _safe_float(account_info.get("totalMaintMargin")),
                "totalInitialMargin": _safe_float(account_info.get("totalInitialMargin")),
                "maxWithdrawAmount": _safe_float(account_info.get("maxWithdrawAmount")),
            }
            balance_assets = sorted(balance_assets, key=lambda item: item.get("asset", ""))
            positions = sorted(positions, key=lambda item: item.get("symbol", ""))
            update_time = current_sync_ms
            open_orders, fills = self.order_sync.sync_futures_orders_and_fills(symbol_map)
            funding_rates = self.position_sync.sync_funding_rates(list(symbol_map.keys()))
            sync_snapshot = self.account_sync.build_futures_snapshot(
                account=account_info,
                positions=positions,
                open_orders=open_orders,
                fills=fills,
                funding_rates=funding_rates,
                last_sync_time=update_time,
            )
            self._last_binance_sync["futures"] = sync_snapshot.to_dict()
            self.state_manager.set_module_health("futures_sync", "ONLINE")
            return {
                "wallet_total": round(display_wallet_balance, 4),
                "margin_total": round(display_margin_balance, 4),
                "mobile_wallet_balance": round(mobile_wallet_balance, 4),
                "mobile_margin_balance": round(mobile_margin_balance, 4),
                "wallet_balance": round(display_wallet_balance, 4),
                "margin_balance": round(display_margin_balance, 4),
                "stable_wallet_total": round(stable_wallet_total, 4),
                "stable_margin_balance": round(stable_margin_balance, 4),
                "collateral_total": round(collateral_total, 4),
                "exchange_wallet_balance": round(exchange_wallet_balance, 4),
                "exchange_margin_balance": round(exchange_margin_balance, 4),
                "exchange_account": exchange_account,
                "available_balance": round(available_balance, 4),
                "unrealized_pnl": round(unrealized, 4),
                "positions": positions,
                "balance_assets": balance_assets,
                "account_alias": account_alias or str(account_info.get("accountAlias", "") or ""),
                "account_fingerprint": self._build_account_fingerprint(balance_assets, account_alias or str(account_info.get("accountAlias", "") or "")),
                "positions_fingerprint": self._build_positions_fingerprint(positions),
                "update_time": update_time,
                "open_orders": open_orders,
                "fills": fills,
                "funding_rates": funding_rates,
                "sync_status": sync_snapshot.sync_status,
                "sync_error": sync_snapshot.sync_error,
            }
        except Exception as exc:
            self.state_manager.set_module_health("futures_sync", f"ERROR: {exc}")
            self._append_alert("WARNING", f"Futures sync failed: {exc}")
            sync_snapshot = self.account_sync.build_futures_snapshot({}, [], [], [], [], 0, sync_error=str(exc))
            self._last_binance_sync["futures"] = sync_snapshot.to_dict()
            return {
                "wallet_total": 0.0,
                "margin_total": 0.0,
                "mobile_wallet_balance": 0.0,
                "mobile_margin_balance": 0.0,
                "wallet_balance": 0.0,
                "margin_balance": 0.0,
                "exchange_wallet_balance": 0.0,
                "exchange_margin_balance": 0.0,
                "available_balance": 0.0,
                "unrealized_pnl": 0.0,
                "positions": [],
                "balance_assets": [],
                "account_alias": "",
                "account_fingerprint": "",
                "positions_fingerprint": "",
                "update_time": 0,
                "open_orders": [],
                "fills": [],
                "funding_rates": [],
                "sync_status": "degraded",
                "sync_error": str(exc),
            }

    def _build_account_fingerprint(self, balance_assets, alias=""):
        parts = [alias or ""]
        for item in balance_assets or []:
            parts.append(
                f"{item.get('asset')}:{round(_safe_float(item.get('balance')), 8)}:{round(_safe_float(item.get('available_balance')), 8)}"
            )
        return _short_fingerprint(parts)

    def _build_positions_fingerprint(self, positions):
        parts = []
        for item in positions or []:
            parts.append(
                f"{item.get('symbol')}:{item.get('side')}:{round(_safe_float(item.get('quantity')), 8)}:{round(_safe_float(item.get('entry_price')), 8)}:{round(_safe_float(item.get('leverage')), 2)}"
            )
        return _short_fingerprint(parts)

    def _build_spot_account_fingerprint(self, balances):
        parts = []
        for asset in sorted((balances or {}).keys()):
            item = balances.get(asset) or {}
            parts.append(
                f"{asset}:{round(_safe_float(item.get('free')), 8)}:{round(_safe_float(item.get('locked')), 8)}"
            )
        return _short_fingerprint(parts)

    def _reconcile_liquidation_losses(self, futures_account):
        if not self.futures_client.is_configured():
            return
        live_positions = self._live_futures_positions_snapshot(futures_account)
        self.liquidation_tracker.reconcile(
            live_positions,
            getattr(self, "futures_live_trades", []) or [],
            self.futures_client,
            self._record_trade_result,
        )

    def _synchronize_live_futures_state(self, futures_account):
        if not self.futures_client.is_configured():
            return

        live_positions = self._live_futures_positions_snapshot(futures_account)
        margin_by_fleet = {}
        for position in live_positions:
            fleet = position.get("fleet")
            if not fleet:
                continue
            margin_by_fleet[fleet] = margin_by_fleet.get(fleet, 0.0) + float(position.get("margin", 0.0) or 0.0)

        self.ledger.sync_live_futures_margins(margin_by_fleet)
        previous_states = {
            str(item.get("symbol") or "").upper(): dict(item.get("r_exit_state") or {})
            for item in self.position_manager.all_positions()
        }
        with self.position_manager._lock:
            merged = {}
            for position in live_positions:
                record = dict(position)
                symbol = str(record.get("symbol") or "").upper()
                if symbol in previous_states and previous_states[symbol]:
                    record["r_exit_state"] = previous_states[symbol]
                merged[record["id"]] = record
            self.position_manager.positions = merged

    def _append_alert(self, level, summary):
        payload = {"time": _now(), "level": level, "summary": summary}
        if self.alerts and self.alerts[0].get("summary") == summary and self.alerts[0].get("level") == level:
            return
        self.alerts.insert(0, payload)
        self.alerts = self.alerts[:80]

    def _append_meeting_alert(self, meeting):
        meeting = self._normalize_meeting_record(meeting or {})
        meeting_type = str(meeting.get("type") or "")
        slot = meeting.get("slot") or (str(meeting.get("time") or "")[-5:] or "會議")
        conclusion = meeting.get("conclusion") or {}
        summary = _clean_display_text(
            conclusion.get("summary") or meeting.get("summary"),
            "圓桌會議已完成，請查看會議紀錄。",
        )
        level = "ALERT_RED" if meeting_type == "EMERGENCY_ROUND_TABLE" else "INFO"
        prefix = "緊急圓桌" if meeting_type == "EMERGENCY_ROUND_TABLE" else f"{slot} 圓桌"
        self._append_alert(level, f"[{prefix}] {summary}")

    def _spot_positions_snapshot(self):
        spot_account = getattr(self, "_last_spot_account", {"holdings": []})
        items = []
        for holding in spot_account.get("holdings", []):
            if holding["quantity"] <= 0:
                continue
            items.append(
                {
                    "id": f"hq_spot_{holding['asset'].lower()}",
                    "opened_at": _now(),
                    "fleet": "HQ",
                    "symbol": f"{holding['asset']}USDT",
                    "side": "BUY",
                    "entry_price": holding["price"],
                    "mark_price": holding["price"],
                    "quantity": holding["quantity"],
                    "margin": holding["value"],
                    "leverage": 1.0,
                    "unrealized_pnl": 0.0,
                    "reason": "hq_spot_inventory",
                    "market_type": "spot",
                }
            )
        return items

    def _live_futures_positions_snapshot(self, futures_account):
        items = []
        opened_at = _now()
        update_time = int(futures_account.get("update_time") or 0)
        if update_time:
            try:
                opened_at = datetime.fromtimestamp(update_time / 1000).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                opened_at = _now()
        for position in futures_account.get("positions", []):
            fleet = str(position.get("fleet") or "").upper()
            capital_pool = "radar" if fleet == "RADAR" else "fleet"
            items.append(
                {
                    "id": f"live_{position.get('fleet', 'FUT')}_{position.get('symbol', 'UNKNOWN')}",
                    "opened_at": opened_at,
                    "fleet": position.get("fleet"),
                    "symbol": position.get("symbol"),
                    "side": position.get("side", "HOLD"),
                    "entry_price": float(position.get("entry_price", 0.0) or 0.0),
                    "mark_price": float(position.get("mark_price", 0.0) or 0.0),
                    "quantity": float(position.get("quantity", 0.0) or 0.0),
                    "signed_quantity": float(position.get("signed_quantity", 0.0) or 0.0),
                    "margin": float(position.get("margin", 0.0) or 0.0),
                    "leverage": float(position.get("leverage", 1.0) or 1.0),
                    "unrealized_pnl": float(position.get("unrealized_pnl", 0.0) or 0.0),
                    "reason": "binance_live_position",
                    "market_type": "futures",
                    "capital_pool": capital_pool,
                    "margin_type": position.get("margin_type", "isolated"),
                    "position_side": position.get("position_side", "BOTH"),
                    "execution_source": "binance_futures_testnet",
                    "source": "binance_live",
                    "liquidation_price": float(position.get("liquidation_price", 0.0) or 0.0),
                    "margin_ratio": float(position.get("margin_ratio", 0.0) or 0.0),
                }
            )
        return items

    def _sync_futures_activity(self):
        if not self.futures_client.is_configured():
            self.futures_live_orders = []
            self.futures_live_trades = []
            return

        symbol_map = {self.futures_client.resolve_symbol(fleet): fleet for fleet in FLEETS}
        live_orders = []
        live_trades = []
        symbols_to_sync = set(symbol_map.keys())
        futures_account = getattr(self, "_last_futures_account", {}) or {}
        symbols_to_sync.update(self.liquidation_tracker.watched_symbols())
        for item in runtime_store.recent_trade_results(limit=80):
            symbol = str(item.get("symbol") or "").upper()
            if symbol:
                symbols_to_sync.add(symbol)
        for position in futures_account.get("positions", []) or []:
            symbols_to_sync.add(str(position.get("symbol") or "").upper())

        for symbol in sorted(symbols_to_sync):
            if not symbol:
                continue
            fleet = fleet_for_exchange_position(symbol, symbol_map)
            try:
                orders = self.futures_client.get_all_orders(symbol, limit=50) or []
            except Exception:
                orders = []
            try:
                trades = self.futures_client.get_user_trades(symbol, limit=50) or []
            except Exception:
                trades = []

            for order in orders:
                raw_time = int(order.get("updateTime") or order.get("time") or 0)
                event_time = datetime.fromtimestamp(raw_time / 1000).strftime("%Y-%m-%d %H:%M:%S") if raw_time else _now()
                live_orders.append(
                    {
                        "id": f"live_order_{fleet}_{order.get('orderId')}",
                        "fleet": fleet,
                        "symbol": symbol,
                        "side": order.get("side"),
                        "type": order.get("type", "MARKET"),
                        "price": _safe_float(order.get("avgPrice") or order.get("price")),
                        "quantity": _safe_float(order.get("origQty")),
                        "executed_quantity": _safe_float(order.get("executedQty")),
                        "status": order.get("status", "UNKNOWN"),
                        "time": event_time,
                        "reason": "binance_live_order",
                        "market_type": "futures",
                        "execution_source": "binance_futures_testnet",
                        "source": "binance_live",
                    }
                )

            for trade in trades:
                raw_time = int(trade.get("time") or 0)
                tzinfo = getattr(nexus_now(), "tzinfo", None)
                if raw_time:
                    if tzinfo is not None:
                        event_time = datetime.fromtimestamp(raw_time / 1000, tz=tzinfo).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        event_time = datetime.fromtimestamp(raw_time / 1000).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    event_time = _now()
                live_trades.append(
                    {
                        "id": f"live_trade_{fleet}_{trade.get('id')}",
                        "event": "LIVE",
                        "fleet": fleet,
                        "symbol": symbol,
                        "side": trade.get("side"),
                        "price": _safe_float(trade.get("price")),
                        "quantity": _safe_float(trade.get("qty")),
                        "pnl": _safe_float(trade.get("realizedPnl")),
                        "commission": _safe_float(trade.get("commission")),
                        "time": event_time,
                        "timestamp": event_time,
                        "reason": "binance_live_trade",
                        "market_type": "futures",
                        "execution_source": "binance_futures_testnet",
                        "source": "binance_live",
                    }
                )

        dedup_orders = {item["id"]: item for item in live_orders if item.get("id")}
        dedup_trades = {item["id"]: item for item in live_trades if item.get("id")}
        self.futures_live_orders = sorted(dedup_orders.values(), key=lambda item: item.get("time", ""), reverse=True)[:160]
        self.futures_live_trades = sorted(dedup_trades.values(), key=lambda item: item.get("time", ""), reverse=True)[:160]

    def snapshot(self):
        ledger_capital = self.ledger.snapshot()
        pnl = self.pnl_tracker.snapshot()
        system_snapshot = self.state_manager.snapshot()
        system_snapshot["pause_reason"] = self._pause_reason
        system_snapshot["manual_pause"] = bool(self._manual_pause)
        system_snapshot["news_pause_active"] = bool(self._news_pause_active)
        system_snapshot["news_pause_until_epoch"] = float(self._news_pause_until or 0.0)
        system_snapshot["block_new_entries"] = bool((self.growth_status or {}).get("block_new_entries"))
        system_snapshot["block_reason"] = str((self.growth_status or {}).get("block_reason") or "")
        ks = dict((self.growth_status or {}).get("kill_switch") or {})
        if ks:
            system_snapshot["kill_switch_status"] = {
                "triggered": bool(ks.get("triggered")),
                "action": ks.get("action"),
                "reason": ks.get("reason"),
                "should_pause": ks.get("should_pause"),
                "checks": ks.get("checks"),
            }
        spot_account = getattr(self, "_last_spot_account", {"spot_total": 0.0, "holdings": [], "balances": {}})
        futures_account = getattr(
            self,
            "_last_futures_account",
            {"wallet_total": 0.0, "margin_total": 0.0, "available_balance": 0.0, "unrealized_pnl": 0.0, "positions": []},
        )

        def _normalize_trade_for_revenue(item: dict) -> dict:
            """Normalize trade rows so monthly revenue KPI can count them."""

            payload = dict(item or {})
            payload.setdefault("market_type", "futures")
            ts = payload.get("timestamp")
            if not (isinstance(ts, str) and len(ts) >= 7 and ts[:4].isdigit() and ts[4] == "-" and ts[6] == "-"):
                raw_time = payload.get("time")
                if isinstance(raw_time, str) and len(raw_time) >= 7 and raw_time[:4].isdigit() and raw_time[4] == "-" and raw_time[6] == "-":
                    payload["timestamp"] = raw_time
                else:
                    try:
                        epoch = float(raw_time or 0.0)
                        if epoch > 10_000_000_000:
                            epoch = epoch / 1000.0
                        tzinfo = getattr(nexus_now(), "tzinfo", None)
                        if tzinfo is not None:
                            payload["timestamp"] = datetime.fromtimestamp(epoch, tz=tzinfo).strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            payload["timestamp"] = datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        payload.setdefault("timestamp", _now())

            event = str(payload.get("event") or "").upper()
            if event not in {"CLOSE", "LIVE"}:
                if payload.get("exit_reason") or payload.get("exit_price") or payload.get("exit_class"):
                    payload["event"] = "CLOSE"
                elif str(payload.get("market_type") or "futures") == "futures":
                    payload["event"] = "LIVE"
            return payload

        exchange_capital = build_ui_capital(
            spot_account,
            futures_account,
            futures_configured=self.futures_client.is_configured(),
            spot_configured=self.spot_client.is_configured(),
        )
        spot_stable_total = float(exchange_capital.get("spot_stable_total", 0.0) or 0.0)
        spot_usdt_total = float(exchange_capital.get("spot_usdt_total", 0.0) or 0.0)
        spot_usdc_total = float(exchange_capital.get("spot_usdc_total", 0.0) or 0.0)
        futures_wallet = float(exchange_capital.get("futures_wallet_display", 0.0) or 0.0)
        futures_total = float(exchange_capital.get("futures_total", 0.0) or 0.0)
        combined_total = float(exchange_capital.get("total", 0.0) or 0.0)
        if self.futures_client.is_configured():
            combined_orders = (self.hq_spot_orders + self.futures_live_orders)[:160]
            combined_trades = (self.hq_spot_trades + self.futures_live_trades)[:160]
        else:
            combined_orders = (self.hq_spot_orders + self.execution_engine.recent_orders(limit=120))[:160]
            combined_trades = (self.hq_spot_trades + self.execution_engine.recent_trades(limit=120))[:160]

        combined_trades = [
            _normalize_trade_for_revenue(item) if isinstance(item, dict) else item for item in (combined_trades or [])
        ]
        active_plan = ledger_capital.get("fleets", {})
        futures_fill_count = len(futures_account.get("fills", []) or [])
        spot_trade_count = len(spot_account.get("trade_history", []) or [])
        true_recent_trade_count = futures_fill_count + spot_trade_count
        configured_futures_baseline = _safe_float(os.getenv("NEXUS_FUTURES_BASELINE_CAPITAL", "11800"))
        treasury_unrealized = round(float(exchange_capital.get("futures_unrealized_pnl", 0.0) or 0.0), 4)
        exchange_unrealized = resolve_futures_display_unrealized(futures_account, treasury_unrealized)
        exchange_capital["futures_unrealized_pnl"] = exchange_unrealized
        if exchange_capital.get("binance_futures"):
            exchange_capital["binance_futures"]["unrealized_pnl"] = exchange_unrealized
        futures_account_total_pnl = exchange_unrealized if self.futures_client.is_configured() else 0.0

        account_binding = build_account_binding_status(self.spot_client, self.futures_client)

        capital = {
            **exchange_capital,
            "account_binding": account_binding,
            "futures_wallet_total": round(futures_wallet, 4),
            "futures_mobile_wallet_balance": round(float(futures_account.get("mobile_wallet_balance", 0.0) or 0.0), 4),
            "futures_mobile_margin_balance": round(float(futures_account.get("mobile_margin_balance", 0.0) or 0.0), 4),
            "futures_wallet_balance": round(futures_wallet, 4),
            "futures_margin_balance": round(futures_total, 4),
            "futures_stable_wallet_total": round(float(futures_account.get("stable_wallet_total", 0.0) or 0.0), 4),
            "futures_stable_margin_balance": round(float(futures_account.get("stable_margin_balance", 0.0) or 0.0), 4),
            "futures_collateral_total": round(float(futures_account.get("collateral_total", 0.0) or 0.0), 4),
            "futures_baseline_capital": round(configured_futures_baseline, 4),
            "futures_account_total_pnl": futures_account_total_pnl,
            "spot_usdt_free": round(float(spot_account.get("usdt_free", 0.0) or 0.0), 4),
            "internal_allocation": {
                "hq_reserve": round(float(ledger_capital.get("hq_reserve", 0.0) or 0.0), 4),
                "radar_budget": round(float(ledger_capital.get("radar_budget", 0.0) or 0.0), 4),
                "active_total": round(float(ledger_capital.get("active_total", 0.0) or 0.0), 4),
                "source": "internal_ledger",
            },
            "spot_truth_scope": str(spot_account.get("truth_scope") or HQ_SPOT_TRUTH_MODE),
            "spot_truth_assets": list(spot_account.get("truth_assets", [])),
            "spot_allowed_assets": list(spot_account.get("allowed_assets", [])),
            "spot_excluded_assets_count": int(spot_account.get("excluded_assets_count", 0) or 0),
            "spot_holdings_total": round(float(spot_account.get("holdings_total", 0.0) or 0.0), 4),
            "spot_truth_warning": str(spot_account.get("truth_warning") or ""),
            "realized_pnl": round(float(pnl.get("total_realized", 0.0) or 0.0), 4),
            "spot_holdings": spot_account.get("holdings", []),
            "futures_positions": futures_account.get("positions", []),
            "futures_balance_assets": futures_account.get("balance_assets", []),
            "spot_account_fingerprint": spot_account.get("account_fingerprint", ""),
            "futures_account_fingerprint": futures_account.get("account_fingerprint", ""),
            "futures_positions_fingerprint": futures_account.get("positions_fingerprint", ""),
            "spot_last_update_time": int(spot_account.get("update_time") or 0),
            "futures_last_update_time": int(futures_account.get("update_time") or 0),
            "order_count": len(combined_orders),
            "trade_count": true_recent_trade_count,
            "fleets": active_plan if active_plan else {fleet: {"allocated": FLEET_ACTIVE_CAPITAL[fleet], "available": 0.0, "frozen": 0.0, "realized_pnl": 0.0} for fleet in FLEETS},
            "entries": ledger_capital.get("entries", []),
        }

        if self.futures_client.is_configured():
            all_positions = self._live_futures_positions_snapshot(futures_account) + self._spot_positions_snapshot()
        else:
            all_positions = self.position_manager.all_positions() + self._spot_positions_snapshot()

        live_positions_by_fleet = {
            fleet: [item for item in all_positions if item.get("fleet") == fleet and item.get("market_type") == "futures"]
            for fleet in FLEETS
        }

        if self.futures_client.is_configured():
            for fleet in FLEETS:
                fleet_live_positions = live_positions_by_fleet.get(fleet, [])
                live_position = fleet_live_positions[0] if fleet_live_positions else None
                if live_position:
                    system_snapshot.setdefault("fleet_status", {}).setdefault(fleet, {})
                    system_snapshot["fleet_status"][fleet]["status"] = "TRADING"
                    system_snapshot["fleet_status"][fleet]["last_signal"] = live_position.get("side", "HOLD")
                    system_snapshot["fleet_status"][fleet]["last_reason"] = "binance_live_position"
                else:
                    current_status = system_snapshot.setdefault("fleet_status", {}).setdefault(fleet, {})
                    if current_status.get("status") == "TRADING":
                        current_status["status"] = "MONITORING"
                        current_status["last_signal"] = "HOLD"
                        current_status["last_reason"] = "no_live_position"

            radar_live = [item for item in all_positions if item.get("fleet") == "RADAR" and item.get("market_type") == "futures"]
            if radar_live:
                radar_position = radar_live[0]
                system_snapshot.setdefault("fleet_status", {}).setdefault("RADAR", {})
                system_snapshot["fleet_status"]["RADAR"]["status"] = "TRADING"
                system_snapshot["fleet_status"]["RADAR"]["last_signal"] = radar_position.get("side", "HOLD")
                system_snapshot["fleet_status"]["RADAR"]["last_reason"] = f"binance_live:{radar_position.get('symbol', '')}"

        fleet_data = {}
        for fleet in FLEETS:
            live_positions = live_positions_by_fleet.get(fleet, [])[0:1] if self.futures_client.is_configured() else [item for item in all_positions if item.get("fleet") == fleet]
            latest_position = live_positions[0] if live_positions else None
            fleet_pnl = dict(pnl.get("fleets", {}).get(fleet, {}))
            if latest_position:
                fleet_pnl["unrealized"] = round(float(latest_position.get("unrealized_pnl", 0.0) or 0.0), 4)
                fleet_pnl["total"] = round(
                    float(fleet_pnl.get("realized", 0.0) or 0.0) + float(fleet_pnl["unrealized"]),
                    4,
                )

            fleet_status = dict(system_snapshot.get("fleet_status", {}).get(fleet, {}))

            if self.futures_client.is_configured():
                fleet_trades = [item for item in self.futures_live_trades if item.get("fleet") == fleet][:12]
                fleet_orders = [item for item in self.futures_live_orders if item.get("fleet") == fleet][:12]
                if latest_position and not fleet_trades:
                    fleet_trades = [
                        {
                            "event": "LIVE",
                            "fleet": fleet,
                            "symbol": latest_position.get("symbol"),
                            "side": latest_position.get("side"),
                            "price": latest_position.get("entry_price"),
                            "quantity": latest_position.get("quantity"),
                            "margin": latest_position.get("margin"),
                            "leverage": latest_position.get("leverage"),
                            "status": "OPEN",
                            "time": latest_position.get("opened_at"),
                            "reason": "binance_live_position",
                        }
                    ]
            else:
                fleet_trades = []
                fleet_orders = []

            fleet_data[fleet] = {
                "system": fleet_status,
                "capital": capital["fleets"].get(fleet, {}),
                "pnl": fleet_pnl,
                "positions": live_positions,
                "trades": fleet_trades,
                "orders": fleet_orders,
                "briefing": self.station_briefings.get(fleet, {}),
            }

        # Diagnostics: expose R-exit thresholds per open position so users can verify stop/TP evaluation.
        position_exit_diagnostics = []
        try:
            from config.exit_config import RISK_PCT, STOP_R, TP_LADDER

            for pos in list(all_positions or [])[:24]:
                margin = float(pos.get("margin", 0.0) or 0.0)
                unrealized = float(pos.get("unrealized_pnl", 0.0) or 0.0)
                qty = float(pos.get("quantity", 0.0) or 0.0)
                entry = float(pos.get("entry_price", 0.0) or 0.0)
                side = str(pos.get("side") or "BUY").upper()
                risk_r_usd = max(margin * float(RISK_PCT), 1e-6)
                pnl_r = unrealized / risk_r_usd if risk_r_usd > 0 else 0.0
                stop_usd = -float(STOP_R) * risk_r_usd
                sign = 1.0 if side == "BUY" else -1.0
                tp_prices = []
                if entry > 0 and qty > 0:
                    for spec in TP_LADDER:
                        target_r = float(spec.get("r", 0.0) or 0.0)
                        move_usd = target_r * risk_r_usd
                        tp_prices.append(
                            {
                                "tag": str(spec.get("tag") or ""),
                                "r": round(target_r, 4),
                                "target_price": round(entry + sign * (move_usd / qty), 8),
                                "fraction": float(spec.get("fraction", 0.0) or 0.0),
                            }
                        )
                position_exit_diagnostics.append(
                    {
                        "fleet": str(pos.get("fleet") or ""),
                        "symbol": str(pos.get("symbol") or ""),
                        "side": side,
                        "margin": round(margin, 6),
                        "unrealized_pnl": round(unrealized, 6),
                        "risk_r_usd": round(risk_r_usd, 6),
                        "pnl_r": round(pnl_r, 4),
                        "stop_r": float(STOP_R),
                        "stop_usd": round(stop_usd, 6),
                        "stop_triggered": bool(unrealized <= stop_usd),
                        "tp_targets": tp_prices,
                    }
                )
        except Exception:
            position_exit_diagnostics = []

        learning_status = self._build_learning_status()
        validation_status = self._build_validation_status()
        account_sync_status = self._last_account_sync_status or self._build_account_sync_status()
        walk_forward_status = self.walk_forward_evaluator.evaluate(runtime_store.recent_trade_results(limit=160))
        position_ai = dict(getattr(self, "_last_position_ai_review", {}) or {})
        if not position_ai and all_positions:
            position_ai = self.ai_position_manager.review_positions(
                all_positions,
                market_contexts=getattr(self, "market_context", {}) or {},
                llm_gateway=self.llm_gateway,
            )
        leverage_status = {
            fleet: (live_positions_by_fleet.get(fleet, [{}])[0].get("leverage_status") if live_positions_by_fleet.get(fleet) else None)
            for fleet in FLEETS
        }

        snapshot_payload = {
            "system": system_snapshot,
            "capital": capital,
            "loans": self.loan_manager.snapshot(),
            "positions": all_positions,
            "pnl": {
                **pnl,
                "source": "binance_futures_rest" if self.futures_client.is_configured() else "internal",
                "total_unrealized": exchange_unrealized,
                "total_pnl": futures_account_total_pnl,
                "exchange_unrealized_pnl": exchange_unrealized,
            },
            "orders": combined_orders,
            "trades": combined_trades,
            "prices": self.latest_prices,
            "market_overview": self.market_overview,
            "news": self.latest_news,
            "whale": self.whale_state,
            "funding": self._build_funding_snapshot(self.market_context),
            "alerts": list(self.alerts),
            "meetings": [self._normalize_meeting_record(item) for item in self.meetings],
            "events": self.event_bus.recent(limit=80),
            "daily_report": {
                "spot_total": round(spot_stable_total, 4),
                "spot_usdt_total": round(spot_usdt_total, 4),
                "spot_usdc_total": round(spot_usdc_total, 4),
                "futures_total": round(futures_total, 4),
                "futures_account_total_pnl": futures_account_total_pnl,
                "combined_total": combined_total,
                "hq_reserve": (capital.get("internal_allocation") or {}).get("hq_reserve", 0.0),
                "radar_budget": (capital.get("internal_allocation") or {}).get("radar_budget", 0.0),
                "updated_at": _now(),
            },
            "decision_summary": {
                "runtime_mode": self.trading_mode,
                "always_on_trading": always_on_trading_enabled(),
                "ai_led_trading": AI_LED_TRADING_ENABLED,
                "ai_led_primary": AI_LED_PRIMARY_MODE,
                "hq_spot_enabled": self.spot_client.is_configured(),
                "futures_enabled": self.futures_client.is_configured(),
                "exchange_synced_at": int(self._last_binance_sync.get("last_sync_time") or 0),
                "live_position_count": len(futures_account.get("positions", []) or []),
                "exchange_position_symbols": [
                    str(item.get("symbol") or "") for item in (futures_account.get("positions", []) or [])
                ],
                "order_count": len(combined_orders),
                "trade_count": true_recent_trade_count,
                "active_positions": len(all_positions),
                "position_exit_diagnostics": position_exit_diagnostics,
                "startup_exit_check": dict(getattr(self, "_startup_exit_check", None) or {}),
                "futures_trading_access": dict(getattr(self, "_futures_trading_access", None) or {}),
                "futures_write_allowed": self._futures_write_allowed()
                if self.futures_client.is_configured()
                else None,
                "last_tick_error": getattr(self, "_last_tick_error", None),
                "external_market_intel": self.external_market_intel.snapshot(),
                "last_trade": combined_trades[0] if combined_trades else None,
                "account_consistency": {
                    "spot_base_url": getattr(self.spot_client, "base_url", ""),
                    "futures_base_url": getattr(self.futures_client, "BASE_URL", ""),
                    "spot_account_fingerprint": spot_account.get("account_fingerprint", ""),
                    "futures_account_fingerprint": futures_account.get("account_fingerprint", ""),
                    "futures_positions_fingerprint": futures_account.get("positions_fingerprint", ""),
                    "futures_account_alias_masked": (
                        f"{str(futures_account.get('account_alias', ''))[:2]}****{str(futures_account.get('account_alias', ''))[-2:]}"
                        if futures_account.get("account_alias")
                        else ""
                    ),
                    "spot_update_time": int(spot_account.get("update_time") or 0),
                    "futures_update_time": int(futures_account.get("update_time") or 0),
                    "spot_truth_scope": str(spot_account.get("truth_scope") or HQ_SPOT_TRUTH_MODE),
                },
            },
            "decision_audit": runtime_store.recent_decision_audit(limit=100),
            "growth_mode": dict(self.growth_status or {}),
            "compound_capital": dict(getattr(self, "_compound_capital_status", {}) or {}),
            "radar_dispatch": {
                "enabled": bool(getattr(self.radar_dispatch, "FLEET", "RADAR")),
                "open_positions": self.position_manager.get_by_fleet("RADAR"),
                "eligible_candidates": self._radar_trade_candidates(),
                "llm_proposals": list(getattr(self, "_radar_llm_proposals", []) or [])[:8],
                "radar_budget_available": round(float(self.ledger.radar_available()), 4),
            },
            "analytics": {
                "previous_prices": dict(self._previous_prices),
                "walk_forward": walk_forward_status,
                "setup_performance": self.setup_performance_tracker.export_state(),
            },
            "fleet_data": fleet_data,
            "station_chats": self.station_chats,
            "station_briefings": self.station_briefings,
            "binance_sync": dict(self._last_binance_sync),
            "learning_status": learning_status,
            "validation_status": validation_status,
            "normalized_events": list(self.normalized_events or []),
            "agent_advisory": dict(self.agent_advisory or {}),
            "llm_status": dict(self.llm_status or self.llm_gateway.status_snapshot()),
            "account_sync_status": account_sync_status,
            "leverage_status": leverage_status,
            "truth_layer_status": dict(self.truth_layer_status or {}),
            "market_context": dict(self.market_context or {}),
            "radar_scan": dict(self.radar_scan or {}),
            "portfolio_status": dict(self.portfolio_status or {}),
            "station_learning_exchange": dict(self.station_learning_exchange or {}),
            "upgrade_pipeline": self.upgrade_pipeline.build_status(
                walk_forward_status=walk_forward_status,
                learning_status=learning_status,
                recent_trades=combined_trades,
            ),
            "event_registry": self.upgrade_pipeline.event_registry.snapshot(),
            "decision_traces": runtime_store.recent_decision_traces(limit=50),
            "live_sync": dict(self._live_sync_status or {}),
            "meeting_execution_directives": dict(self._meeting_execution_directives or {}),
            "strategy_evolution": dict(getattr(self, "_strategy_evolution_status", {}) or {}),
            "strategy_modules": self.strategy_proposal_hub.status_snapshot(),
            "position_ai": position_ai,
        }
        try:
            from backend.runtime.embed_flags import embedded_worker_error, embedded_worker_started
        except Exception:
            embedded_worker_started = False
            embedded_worker_error = None
        ops_report = self.ops_health.build_report(
            snapshot_payload,
            embedded_worker_started=embedded_worker_started,
            embedded_worker_error=embedded_worker_error,
        )
        snapshot_payload["ops_health"] = ops_report
        self.ops_health.maybe_alert(ops_report, previous_status=self._last_ops_status)
        self._last_ops_status = ops_report.get("status")
        snapshot_payload["trading_health"] = self.trading_health.build_report(
            snapshot_payload,
            runtime_store=runtime_store,
        )
        snapshot_payload["maturity_radar"] = self.maturity_radar.build_report(
            snapshot_payload,
            runtime_store=runtime_store,
            embedded_worker_started=embedded_worker_started,
            embedded_worker_error=embedded_worker_error,
            ops_health=ops_report,
        )
        snapshot_payload["trading_health"]["maturity_radar"] = snapshot_payload["maturity_radar"]

        trade_results_db = runtime_store.recent_trade_results(limit=400)
        # UI revenue KPI should reflect real exchange fills even when local trade_results
        # has not yet recorded CLOSE/LIVE rows (e.g. after deploy/restart).
        merged_trade_results = [
            _normalize_trade_for_revenue(item) if isinstance(item, dict) else item for item in list(trade_results_db)
        ]
        try:
            seen_ids = {str(item.get("id") or item.get("order_id") or "") for item in merged_trade_results if item.get("id") or item.get("order_id")}
            for item in list(combined_trades or [])[:240]:
                if str(item.get("market_type") or "futures") != "futures":
                    continue
                norm = _normalize_trade_for_revenue(item) if isinstance(item, dict) else item
                if str(norm.get("event") or "").upper() not in {"LIVE", "CLOSE"}:
                    continue
                _id = str(norm.get("id") or norm.get("order_id") or "")
                if _id and _id in seen_ids:
                    continue
                merged_trade_results.append(norm)
                if _id:
                    seen_ids.add(_id)
        except Exception:
            merged_trade_results = [
                _normalize_trade_for_revenue(item) if isinstance(item, dict) else item
                for item in (list(trade_results_db) or list(combined_trades or []))
            ]
        futures_equity = float(
            (snapshot_payload.get("compound_capital") or {}).get("live_futures_equity")
            or capital.get("futures_margin_balance")
            or 0.0
        )
        daily = dict((snapshot_payload.get("growth_mode") or {}).get("daily") or {})
        start_eq = float(daily.get("start_equity") or daily.get("reinvest_base_equity") or futures_equity)
        snapshot_payload["monthly_revenue"] = self.monthly_revenue.build_report(
            futures_equity,
            trade_results=merged_trade_results,
            start_equity=start_eq,
        )
        snapshot_payload["revenue_plan"] = self.revenue_plan.build_plan(
            snapshot_payload["monthly_revenue"],
            compound_capital=snapshot_payload.get("compound_capital"),
            maturity_radar=snapshot_payload.get("maturity_radar"),
        )
        snapshot_payload["decision_funnel"] = self.decision_funnel.build_report(
            audits=runtime_store.recent_decision_audit(limit=200),
            validations=runtime_store.recent_trade_validation_events(limit=200),
            proposals=runtime_store.recent_trade_proposals(limit=100),
            trade_results=merged_trade_results,
            decision_traces=runtime_store.recent_decision_traces(limit=50),
        )
        exec_quality = self.execution_quality_monitor.evaluate(
            recent_trades=combined_trades,
            validation_events=runtime_store.recent_trade_validation_events(limit=120),
        )
        gross = float((snapshot_payload["monthly_revenue"] or {}).get("realized_pnl_gross") or 0.0)
        fees = float((snapshot_payload["monthly_revenue"] or {}).get("fees_usd") or 0.0)
        exec_quality["fee_to_gross_ratio"] = round(fees / gross, 4) if gross > 0 else 0.0
        exec_quality["futures_only_mode"] = FUTURES_ONLY_TRADING
        snapshot_payload["execution_quality"] = exec_quality
        snapshot_payload["futures_only_trading"] = FUTURES_ONLY_TRADING
        return snapshot_payload


nexus_runtime = NexusRuntime()
