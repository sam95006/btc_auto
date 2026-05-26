from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta

from config.quality_gates_config import (
    MIN_TRADE_CONFIDENCE,
    QUALITY_GATE_ENABLED,
    TARGET_WIN_RATE,
)
from config.revenue_target_config import REVENUE_GROWTH_MODE
from config.validation_config import (
    BACKTEST_CONFIDENT_OVERRIDE,
    BACKTEST_MAX_ALLOWED_RECENT_LOSSES,
    BACKTEST_MAX_NEGATIVE_AVG_PNL,
    BACKTEST_MIN_SAMPLE_SIZE,
    BACKTEST_MIN_WIN_RATE,
    PAPER_BOOTSTRAP_SKIP_BLOCKS,
    PAPER_MAX_RECENT_EXECUTION_ERRORS,
    PAPER_MAX_RECENT_VALIDATION_BLOCKS,
    PAPER_VALIDATION_WINDOW_SECONDS,
    SIMULATION_BLOCKED_REGIMES,
    SIMULATION_MAX_SPREAD_BPS,
    SIMULATION_MIN_TOP5_NOTIONAL,
    VALIDATION_MIN_APPROVAL_SCORE,
)
from backend.trading.decision_quality_engine import DecisionQualityValidationEngine
from config.fleet_routing_config import validate_futures_open_route
from config.market_data_config import (
    LIQUIDATION_CRITICAL_DISTANCE_PCT,
    SIMULATION_MAX_BASIS_ABS_BPS,
    SIMULATION_MAX_FUNDING_ABS,
    SIMULATION_MAX_SLIPPAGE_BPS,
)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value, default=0.0):
    try:
        return float(value if value is not None else default)
    except Exception:
        return float(default)


def _bold_testnet_enabled() -> bool:
    return str(os.getenv("NEXUS_BOLD_TESTNET", "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _learning_relaxed() -> bool:
    return _bold_testnet_enabled() or REVENUE_GROWTH_MODE


def _proposal_confidence(proposal) -> float:
    return _safe_float(
        proposal.get("confidence_score")
        or proposal.get("adjusted_confidence")
        or proposal.get("confidence")
    )


def _hard_learning_block(symbol, learning_guidance):
    symbol = str(symbol or "").upper()
    blocked = {str(item).upper() for item in (learning_guidance.get("blocked_symbols") or [])}
    if symbol in blocked:
        return True, "learning_symbol_blacklisted"
    cooldown = dict(learning_guidance.get("symbol_cooldown") or {}).get(symbol) or {}
    if cooldown.get("active") and cooldown.get("reason") == "exchange_liquidation":
        if _learning_relaxed():
            return False, None
        return True, "learning_liquidation_cooldown"
    return False, None


def _symbol_lesson_gate(symbol, proposal, learning_guidance):
    symbol = str(symbol or "").upper()
    lesson = dict((learning_guidance.get("symbol_lessons") or {}).get(symbol) or {})
    if not lesson:
        return False, None
    confidence = _safe_float(proposal.get("confidence_score") or proposal.get("confidence"))
    min_confidence = _safe_float(lesson.get("min_confidence"), MIN_TRADE_CONFIDENCE)
    if confidence and confidence < min_confidence:
        return True, "learning_symbol_lesson_low_confidence"
    leverage = _safe_float(proposal.get("leverage") or proposal.get("final_leverage"))
    cap = lesson.get("leverage_cap")
    if cap is not None and leverage and leverage > _safe_float(cap):
        return True, "learning_symbol_lesson_leverage_cap"
    return False, None


def _quality_gate_block(proposal, growth_directives, recent_trades):
    if not QUALITY_GATE_ENABLED:
        return False, None
    trades = list(recent_trades or [])[:40]
    closes = [item for item in trades if str(item.get("event") or "").upper() == "CLOSE"]
    if REVENUE_GROWTH_MODE and len(closes) < 3:
        return False, None
    if len(trades) < 8:
        return False, None
    wins = sum(1 for item in trades if _safe_float(item.get("pnl")) > 0)
    win_rate = wins / max(len(trades), 1)
    confidence = _safe_float(proposal.get("confidence_score") or proposal.get("confidence"))
    min_conf = _safe_float(growth_directives.get("min_trade_confidence"), MIN_TRADE_CONFIDENCE)
    target_wr = _safe_float(growth_directives.get("min_win_rate"), TARGET_WIN_RATE)
    if win_rate < target_wr * 0.85 and confidence < min_conf:
        return True, "quality_gate_low_confidence_after_weak_window"
    if confidence and confidence < min_conf:
        return True, "quality_gate_min_confidence"
    return False, None


def _safe_int(value):
    try:
        return int(value or 0)
    except Exception:
        return 0


def _parse_timestamp(value):
    if not value:
        return None
    for parser in (
        lambda raw: datetime.fromisoformat(str(raw)),
        lambda raw: datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            return parser(value)
        except Exception:
            continue
    return None


class BacktestValidationEngine:
    def __init__(self, runtime_store):
        self.runtime_store = runtime_store

    def evaluate(self, proposal, market_context=None, growth_directives=None):
        fleet = str(proposal.get("fleet") or "").upper()
        symbol = str(proposal.get("symbol") or "")
        strategy_key = proposal.get("strategy_key") or "unknown_strategy"
        market_type = proposal.get("market_type") or "futures"
        growth_directives = growth_directives or {}
        min_win_rate = float(growth_directives.get("min_win_rate", BACKTEST_MIN_WIN_RATE) or BACKTEST_MIN_WIN_RATE)
        results = self.runtime_store.recent_trade_results(limit=240)
        scoped = [
            item
            for item in results
            if str(item.get("fleet") or "").upper() == fleet
            and str(item.get("market_type") or "") == market_type
            and (not symbol or str(item.get("symbol") or "") == symbol)
        ]
        strategy_scoped = [item for item in scoped if (item.get("strategy_key") or "unknown_strategy") == strategy_key]
        target = strategy_scoped or scoped
        trade_count = len(target)
        if trade_count == 0:
            return {
                "stage": "backtest",
                "approved": True,
                "score": 0.6,
                "reason": "no_history_bootstrap_allowed",
                "trade_count": 0,
                "win_rate": 0.5,
                "avg_pnl": 0.0,
                "recent_losses": 0,
            }

        wins = sum(1 for item in target if _safe_float(item.get("pnl")) > 0)
        win_rate = wins / max(trade_count, 1)
        avg_pnl = sum(_safe_float(item.get("pnl")) for item in target) / max(trade_count, 1)
        recent_losses = 0
        for item in target[:BACKTEST_MAX_ALLOWED_RECENT_LOSSES]:
            if _safe_float(item.get("pnl")) < 0:
                recent_losses += 1
            else:
                break

        approved = True
        reason = "historical_edge_ok"
        score = 0.55 + (win_rate - 0.5) * 0.6
        confidence = _proposal_confidence(proposal)
        if trade_count >= BACKTEST_MIN_SAMPLE_SIZE:
            if win_rate < min_win_rate and avg_pnl <= BACKTEST_MAX_NEGATIVE_AVG_PNL:
                severe_edge = win_rate < (0.22 if REVENUE_GROWTH_MODE else min_win_rate * 0.5)
                if REVENUE_GROWTH_MODE and confidence >= BACKTEST_CONFIDENT_OVERRIDE and not severe_edge:
                    approved = True
                    reason = "historical_edge_caution"
                    score = max(score, 0.5)
                else:
                    approved = False
                    reason = "historical_edge_too_weak"
                    score = 0.2
            elif recent_losses >= BACKTEST_MAX_ALLOWED_RECENT_LOSSES:
                if REVENUE_GROWTH_MODE and confidence >= BACKTEST_CONFIDENT_OVERRIDE:
                    approved = True
                    reason = "recent_loss_streak_caution"
                    score = max(score, 0.48)
                else:
                    approved = False
                    reason = "recent_loss_streak"
                    score = 0.15
        else:
            reason = "history_sample_small"
            score = max(score, 0.53)

        return {
            "stage": "backtest",
            "approved": approved,
            "score": round(max(0.0, min(1.0, score)), 4),
            "reason": reason,
            "trade_count": trade_count,
            "win_rate": round(win_rate, 4),
            "avg_pnl": round(avg_pnl, 4),
            "recent_losses": recent_losses,
        }


class SimulationValidationEngine:
    def evaluate(self, proposal, market_context=None, truth_status=None):
        market_context = market_context or {}
        truth_status = truth_status or {}
        market_regime = str(market_context.get("market_regime") or "normal").lower()
        spread_bps = _safe_float(market_context.get("spread_bps"))
        top5_notional = _safe_float(market_context.get("top5_cross_notional"))
        liquidity_status = str(market_context.get("liquidity_status") or "healthy").lower()
        worst_slippage_bps = _safe_float(market_context.get("worst_slippage_bps"))
        funding_abs = _safe_float(market_context.get("funding_abs") or abs(_safe_float(market_context.get("funding_rate"))))
        basis_abs_bps = abs(_safe_float(market_context.get("basis_bps")))
        liquidation_distance_pct = _safe_float(market_context.get("liquidation_distance_pct"))
        liquidation_risk = str(market_context.get("liquidation_risk") or "none").lower()
        oi_notional_status = str(market_context.get("oi_notional_status") or "healthy").lower()
        truth_fresh = bool(truth_status.get("fresh_for_ai"))

        approved = True
        reason = "execution_conditions_ok"
        score = 0.7

        if not truth_fresh:
            approved = False
            reason = "truth_layer_not_fresh"
            score = 0.0
        elif market_regime in SIMULATION_BLOCKED_REGIMES:
            approved = False
            reason = f"market_regime_blocked:{market_regime}"
            score = 0.1
        elif liquidity_status != "healthy" or top5_notional < SIMULATION_MIN_TOP5_NOTIONAL:
            approved = False
            reason = "insufficient_liquidity"
            score = 0.18
        elif spread_bps >= SIMULATION_MAX_SPREAD_BPS:
            approved = False
            reason = "spread_too_wide"
            score = 0.22
        elif worst_slippage_bps >= SIMULATION_MAX_SLIPPAGE_BPS:
            approved = False
            reason = "slippage_too_high"
            score = 0.14
        elif funding_abs >= SIMULATION_MAX_FUNDING_ABS:
            approved = False
            reason = "funding_dislocation"
            score = 0.12
        elif basis_abs_bps >= SIMULATION_MAX_BASIS_ABS_BPS:
            fleet = str(proposal.get("fleet") or "").upper()
            if _bold_testnet_enabled() and fleet == "RADAR":
                approved = True
                reason = "caution:basis_dislocation_bold_radar"
                score = 0.45
            else:
                approved = False
                reason = "basis_dislocation"
                score = 0.12
        elif liquidation_risk == "critical" or (
            liquidation_distance_pct and liquidation_distance_pct <= LIQUIDATION_CRITICAL_DISTANCE_PCT
        ):
            approved = False
            reason = "liquidation_pressure_too_high"
            score = 0.08
        elif market_regime in {"thin_liquidity", "wide_spread", "low_open_interest"}:
            approved = True
            reason = f"caution:{market_regime}"
            score = 0.5
        elif market_regime in {"basis_dislocation", "funding_dislocation", "high_slippage", "liquidation_risk"}:
            approved = True
            reason = f"caution:{market_regime}"
            score = 0.42
        elif oi_notional_status != "healthy":
            approved = True
            reason = "caution:low_open_interest_notional"
            score = 0.48

        return {
            "stage": "simulation",
            "approved": approved,
            "score": round(max(0.0, min(1.0, score)), 4),
            "reason": reason,
            "market_regime": market_regime,
            "spread_bps": round(spread_bps, 4),
            "top5_cross_notional": round(top5_notional, 4),
            "liquidity_status": liquidity_status,
            "worst_slippage_bps": round(worst_slippage_bps, 4),
            "funding_abs": round(funding_abs, 8),
            "basis_abs_bps": round(basis_abs_bps, 4),
            "liquidation_risk": liquidation_risk,
            "oi_notional_status": oi_notional_status,
            "truth_fresh": truth_fresh,
        }


class PaperTradeValidationEngine:
    def __init__(self, runtime_store):
        self.runtime_store = runtime_store

    def evaluate(self, proposal, recent_orders=None, recent_trades=None):
        fleet = str(proposal.get("fleet") or "").upper()
        symbol = str(proposal.get("symbol") or "")
        recent_orders = list(recent_orders or [])
        recent_trades = list(recent_trades or [])
        recent_validation_events = self.runtime_store.recent_trade_validation_events(limit=160)
        window_start = datetime.now() - timedelta(seconds=PAPER_VALIDATION_WINDOW_SECONDS)

        recent_blocks = 0
        for item in recent_validation_events:
            ts = _parse_timestamp(item.get("timestamp"))
            if ts and ts < window_start:
                continue
            if str(item.get("fleet") or "").upper() != fleet:
                continue
            if symbol and str(item.get("symbol") or "") != symbol:
                continue
            if not item.get("approved"):
                recent_blocks += 1

        execution_errors = 0
        scoped_orders = []
        for item in recent_orders:
            if str(item.get("fleet") or "").upper() != fleet:
                continue
            if symbol and str(item.get("symbol") or "") != symbol:
                continue
            scoped_orders.append(item)
            if str(item.get("status") or "").upper() in {"ERROR", "REJECTED", "FAILED", "EXPIRED"}:
                execution_errors += 1

        recent_loss_trades = 0
        recent_closes = 0
        for item in recent_trades:
            if str(item.get("fleet") or "").upper() != fleet:
                continue
            if symbol and str(item.get("symbol") or "") != symbol:
                continue
            if str(item.get("event") or "").upper() == "CLOSE":
                recent_closes += 1
            if _safe_float(item.get("pnl")) < 0:
                recent_loss_trades += 1

        approved = True
        reason = "paper_execution_ok"
        score = 0.68
        block_limit = PAPER_MAX_RECENT_VALIDATION_BLOCKS
        if PAPER_BOOTSTRAP_SKIP_BLOCKS and recent_closes == 0:
            block_limit = max(block_limit, block_limit * 3)
        if recent_blocks >= block_limit:
            if REVENUE_GROWTH_MODE:
                approved = True
                reason = "recent_validation_blocks_caution"
                score = 0.42
            else:
                approved = False
                reason = "recent_validation_blocks_too_many"
                score = 0.1
        elif execution_errors >= PAPER_MAX_RECENT_EXECUTION_ERRORS:
            approved = False
            reason = "recent_execution_errors_too_many"
            score = 0.16
        elif recent_loss_trades >= 4 and execution_errors >= 1:
            approved = False
            reason = "execution_quality_deteriorating"
            score = 0.24

        return {
            "stage": "paper_trade",
            "approved": approved,
            "score": round(max(0.0, min(1.0, score)), 4),
            "reason": reason,
            "recent_validation_blocks": recent_blocks,
            "recent_execution_errors": execution_errors,
            "recent_loss_trades": recent_loss_trades,
            "observed_order_count": len(scoped_orders),
        }


class PortfolioValidationEngine:
    def evaluate(self, proposal, portfolio_status=None):
        proposal = dict(proposal or {})
        portfolio_status = portfolio_status or {}
        market_type = str(proposal.get("market_type") or "futures").lower()
        fleet = str(proposal.get("fleet") or "").upper()
        if market_type != "futures":
            return {
                "stage": "portfolio",
                "approved": True,
                "score": 0.72,
                "reason": "spot_notional_governance_not_required",
            }

        restrictions = dict((portfolio_status.get("fleet_restrictions") or {}).get(fleet, {}))
        reserve_action = str(portfolio_status.get("reserve_action") or "hold").lower()
        utilization = _safe_float(portfolio_status.get("notional_utilization"))
        same_side_concentration = _safe_float(portfolio_status.get("same_side_concentration"))
        correlation_concentration = _safe_float(portfolio_status.get("correlation_concentration"))
        hedge_recommendations = list(portfolio_status.get("hedge_recommendations") or [])

        approved = True
        reason = "portfolio_governance_ok"
        score = 0.7
        same_side_limit = 0.95 if _bold_testnet_enabled() else (0.88 if REVENUE_GROWTH_MODE else 0.78)
        if restrictions and not restrictions.get("allowed_new_entries", True):
            approved = False
            reason = "portfolio_governor_block"
            score = 0.05
        elif reserve_action == "increase_reserve" and utilization >= 1.0:
            approved = False
            reason = "portfolio_reserve_increase_block"
            score = 0.12
        elif same_side_concentration >= same_side_limit:
            approved = False
            reason = "same_side_concentration_too_high"
            score = 0.16
        elif correlation_concentration >= 0.62:
            approved = False
            reason = "correlation_concentration_too_high"
            score = 0.18
        elif hedge_recommendations:
            approved = True
            reason = "caution:hedge_recommended"
            score = 0.48

        relax_portfolio = _bold_testnet_enabled() or REVENUE_GROWTH_MODE
        if relax_portfolio and not approved:
            fleet_exposure = dict((portfolio_status.get("fleet_exposures") or {}).get(fleet, {}))
            fleet_notional = _safe_float(fleet_exposure.get("notional"))
            utilization = _safe_float(portfolio_status.get("notional_utilization"))
            proposal_side = str(proposal.get("side") or "BUY").upper()
            dominant_side = str(portfolio_status.get("dominant_side") or "").upper()
            hedge_side = "BUY" if dominant_side == "SHORT" else "SELL"
            if proposal_side == hedge_side and reason == "same_side_concentration_too_high":
                approved = True
                reason = "bold_testnet_hedge_allowed"
                score = max(score, 0.55)
            elif (fleet_notional <= 0 or utilization < 0.12) and reason in {
                "same_side_concentration_too_high",
                "correlated_group_concentration_too_high",
                "portfolio_reserve_increase_block",
            }:
                approved = True
                reason = "bold_testnet_fleet_diversification_allowed"
                score = max(score, 0.52)

        return {
            "stage": "portfolio",
            "approved": approved,
            "score": round(max(0.0, min(1.0, score)), 4),
            "reason": reason,
            "reserve_action": reserve_action,
            "notional_utilization": round(utilization, 4),
            "same_side_concentration": round(same_side_concentration, 4),
            "correlation_concentration": round(correlation_concentration, 4),
            "hedge_recommendation_count": len(hedge_recommendations),
        }


class TradeValidationPipeline:
    def __init__(self, runtime_store, learning_feedback=None, decision_quality_engine=None):
        self.runtime_store = runtime_store
        self.learning_feedback = learning_feedback
        self.backtest_engine = BacktestValidationEngine(runtime_store)
        self.simulation_engine = SimulationValidationEngine()
        self.paper_engine = PaperTradeValidationEngine(runtime_store)
        self.portfolio_engine = PortfolioValidationEngine()
        self.decision_quality_engine = decision_quality_engine or DecisionQualityValidationEngine()

    def evaluate(
        self,
        proposal,
        market_context=None,
        truth_status=None,
        recent_orders=None,
        recent_trades=None,
        portfolio_status=None,
        growth_context=None,
    ):
        proposal = dict(proposal or {})
        market_context = market_context or {}
        truth_status = truth_status or {}
        if str(proposal.get("market_type") or "futures").lower() == "futures":
            route_ok, route_reason = validate_futures_open_route(
                proposal.get("fleet"),
                proposal.get("symbol") or proposal.get("symbol_override"),
            )
            if not route_ok:
                return {
                    "approved": False,
                    "reason": route_reason,
                    "approval_score": 0.0,
                    "stages": {
                        "fleet_routing": {
                            "stage": "fleet_routing",
                            "approved": False,
                            "score": 0.0,
                            "reason": route_reason,
                        }
                    },
                    "reject_layer": "fleet_routing",
                }
        portfolio_status = portfolio_status or {}
        growth_context = growth_context or {}
        growth_directives = dict(growth_context.get("growth_directives") or {})
        min_approval_score = float(growth_directives.get("min_approval_score", VALIDATION_MIN_APPROVAL_SCORE) or VALIDATION_MIN_APPROVAL_SCORE)
        learning_guidance = {}
        if self.learning_feedback:
            learning_guidance = self.learning_feedback.get_strategy_guidance(
                proposal.get("fleet"),
                proposal.get("strategy_key"),
                market_context.get("market_regime"),
                market_context=market_context,
            )
        backtest = self.backtest_engine.evaluate(proposal, market_context=market_context, growth_directives=growth_directives)
        simulation = self.simulation_engine.evaluate(proposal, market_context=market_context, truth_status=truth_status)
        paper_trade = self.paper_engine.evaluate(proposal, recent_orders=recent_orders, recent_trades=recent_trades)
        portfolio = self.portfolio_engine.evaluate(proposal, portfolio_status=portfolio_status)
        decision_quality = self.decision_quality_engine.evaluate(
            proposal,
            market_context=market_context,
            growth_context=growth_context,
        )
        stages = {
            "backtest": backtest,
            "simulation": simulation,
            "paper_trade": paper_trade,
            "portfolio": portfolio,
            "decision_quality": decision_quality,
        }
        approved = all(stage.get("approved") for stage in stages.values())
        approval_score = round(
            (
                _safe_float(backtest.get("score"))
                + _safe_float(simulation.get("score"))
                + _safe_float(paper_trade.get("score"))
                + _safe_float(portfolio.get("score"))
                + _safe_float(decision_quality.get("score"))
            ) / 5.0,
            4,
        )
        learning_block_reason = None
        relaxed_learning = _learning_relaxed()
        symbol = str(proposal.get("symbol") or "").upper()
        hard_block, hard_reason = _hard_learning_block(symbol, learning_guidance)
        lesson_block, lesson_reason = _symbol_lesson_gate(symbol, proposal, learning_guidance)
        quality_block, quality_reason = _quality_gate_block(
            proposal,
            growth_directives,
            recent_trades,
        )
        if hard_block:
            approved = False
            learning_block_reason = hard_reason
        elif lesson_block:
            approved = False
            learning_block_reason = lesson_reason
        elif quality_block:
            approved = False
            learning_block_reason = quality_reason
        elif learning_guidance.get("pause_new_entries") and not relaxed_learning:
            approved = False
            learning_block_reason = "learning_pause_due_to_recent_losses"
        elif learning_guidance.get("regime_blocked") and not relaxed_learning:
            approved = False
            learning_block_reason = "learning_regime_blocked"
        else:
            symbol_cooldown = dict(learning_guidance.get("symbol_cooldown", {}) or {})
            cooldown_active = bool((symbol_cooldown.get(symbol) or {}).get("active"))
            if cooldown_active and not relaxed_learning:
                approved = False
                learning_block_reason = "learning_symbol_cooldown"
            elif cooldown_active and relaxed_learning and _proposal_confidence(proposal) < BACKTEST_CONFIDENT_OVERRIDE:
                approved = False
                learning_block_reason = "learning_symbol_cooldown"
            elif not relaxed_learning:
                failure_flags = set(learning_guidance.get("failure_focus_flags", []) or [])
                if "low_liquidity" in failure_flags and str(market_context.get("liquidity_status") or "healthy").lower() != "healthy":
                    approved = False
                    learning_block_reason = "learning_low_liquidity_block"
                elif "news_conflict" in failure_flags and bool(market_context.get("news_conflict")):
                    approved = False
                    learning_block_reason = "learning_news_conflict_block"
                elif "whale_conflict" in failure_flags and bool(market_context.get("whale_conflict")):
                    approved = False
                    learning_block_reason = "learning_whale_conflict_block"
        approval_score = round(
            max(
                0.0,
                approval_score
                - float(learning_guidance.get("confidence_penalty", 0.0) or 0.0) * 0.5
                - (1.0 - float(learning_guidance.get("position_size_multiplier", 1.0) or 1.0)) * 0.2,
            ),
            4,
        )
        if approval_score < min_approval_score:
            approved = False

        stage_reasons = [stage.get("reason") for stage in stages.values() if not stage.get("approved")]
        primary_reason = learning_block_reason or (stage_reasons[0] if stage_reasons else "validated_for_execution")
        result = {
            "timestamp": proposal.get("timestamp") or _now(),
            "fleet": proposal.get("fleet"),
            "symbol": proposal.get("symbol"),
            "market_type": proposal.get("market_type", "futures"),
            "strategy_key": proposal.get("strategy_key"),
            "approved": approved,
            "approval_score": approval_score,
            "reason": primary_reason,
            "stages": stages,
            "learning_guidance": learning_guidance,
        }
        self.runtime_store.append_trade_validation_event(result)
        return result

    def build_status_snapshot(self, limit=120):
        items = self.runtime_store.recent_trade_validation_events(limit=limit)
        approved_count = sum(1 for item in items if item.get("approved"))
        blocked_count = sum(1 for item in items if not item.get("approved"))
        by_fleet = Counter(str(item.get("fleet") or "UNKNOWN").upper() for item in items)
        return {
            "event_count": len(items),
            "approved_count": approved_count,
            "blocked_count": blocked_count,
            "last_event": items[0] if items else None,
            "by_fleet": dict(by_fleet),
        }
