from collections import Counter, defaultdict
from datetime import datetime


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class AdvisoryServices:
    def build_news_understanding(self, normalized_events, truth_layer_status, market_context):
        normalized_events = list(normalized_events or [])
        market_context = market_context or {}
        truth_layer_status = truth_layer_status or {}
        bucket_counts = Counter(event.get("bucket", "crypto") for event in normalized_events)
        major_events = [event for event in normalized_events if event.get("major")]
        highest_risk = sorted(
            normalized_events,
            key=lambda item: (item.get("impact") == "HIGH", item.get("quality_score", 0.0)),
            reverse=True,
        )[:5]
        return {
            "generated_at": _now(),
            "event_count": len(normalized_events),
            "bucket_counts": dict(bucket_counts),
            "major_event_count": len(major_events),
            "highest_risk_events": highest_risk,
            "truth_ready": bool(truth_layer_status.get("fresh_for_ai")),
            "degraded_contexts": list(truth_layer_status.get("degraded_market_contexts", []) or []),
            "market_regimes": {fleet: context.get("market_regime", "normal") for fleet, context in market_context.items()},
        }

    def build_round_table_advisory(self, meetings, normalized_events, truth_layer_status, portfolio_status=None, station_learning_exchange=None):
        latest_meeting = (meetings or [{}])[0] if meetings else {}
        portfolio_status = portfolio_status or {}
        station_learning_exchange = station_learning_exchange or {}
        enabled = []
        disabled = []
        for reason in truth_layer_status.get("stale_reasons", []) or []:
            if "futures" in reason:
                disabled.extend(["BTC", "ETH", "SOL", "PEPE"])
            elif "spot" in reason:
                disabled.append("HQ")
        if truth_layer_status.get("futures_ready_for_ai"):
            enabled.extend(["BTC", "ETH", "SOL", "PEPE"])
        if truth_layer_status.get("spot_ready_for_ai"):
            enabled.append("HQ")
        return {
            "generated_at": _now(),
            "meeting_reference": latest_meeting.get("meeting_id") or latest_meeting.get("time") or "",
            "machine_summary": latest_meeting.get("summary") or "",
            "risk_level": "HIGH" if any(event.get("major") for event in normalized_events or []) else "NORMAL",
            "enabled_desks": sorted(set(enabled)),
            "disabled_desks": sorted(set(disabled)),
            "fleet_restrictions": dict(portfolio_status.get("fleet_restrictions", {})),
            "capital_adjustments": dict(portfolio_status.get("capital_adjustments", {})),
            "station_shares": list(station_learning_exchange.get("station_shares", []) or []),
            "cross_station_lessons": list(station_learning_exchange.get("cross_station_lessons", []) or []),
            "reason": "truth_layer_gated_round_table_summary",
        }

    def build_radar_advisory(self, normalized_events, market_context, truth_layer_status):
        normalized_events = list(normalized_events or [])
        market_context = market_context or {}
        truth_layer_status = truth_layer_status or {}
        liquidity_alerts = []
        watch_symbols = []
        whale_conflict = False
        news_conflict = False
        for fleet, context in market_context.items():
            if context.get("spread_status") in {"wide", "stressed"}:
                liquidity_alerts.append(f"{fleet}:spread_{context.get('spread_status')}")
            if context.get("liquidity_status") in {"thin", "fragile"}:
                liquidity_alerts.append(f"{fleet}:liquidity_{context.get('liquidity_status')}")
            if context.get("market_regime") in {"wide_spread", "thin_liquidity", "low_open_interest"}:
                watch_symbols.append(fleet)
            whale_bias = str(context.get("whale_bias", "NEUTRAL")).upper()
            if whale_bias == "BEARISH" and context.get("market_regime") not in {"breakdown", "trend_down"}:
                whale_conflict = True
            if float(context.get("news_score", 0.0) or 0.0) < -0.45:
                news_conflict = True
        return {
            "generated_at": _now(),
            "market_pressure": "degraded" if truth_layer_status.get("degraded_market_contexts") else "normal",
            "liquidity_alerts": sorted(set(liquidity_alerts)),
            "whale_conflict": whale_conflict,
            "news_conflict": news_conflict,
            "watch_symbols": sorted(set(watch_symbols)),
            "probe_recommendation": "defer" if not truth_layer_status.get("fresh_for_ai") else "monitor",
        }

    def build_reflection_advisory(self, trade_results, recommendations, calibration_snapshot=None):
        trade_results = list(trade_results or [])
        recommendations = list(recommendations or [])
        calibration_snapshot = calibration_snapshot or {}
        losses = [item for item in trade_results if item.get("win_loss") == "LOSS"]
        failure_counts = Counter(item.get("failure_reason", "unknown") for item in losses)
        by_fleet = defaultdict(list)
        for item in recommendations:
            by_fleet[item.get("fleet", "UNKNOWN")].append(item)
        latest = {}
        for fleet, items in by_fleet.items():
            latest[fleet] = items[0]
        return {
            "generated_at": _now(),
            "trade_result_count": len(trade_results),
            "loss_count": len(losses),
            "failure_pattern_counts": dict(failure_counts),
            "latest_recommendations_by_fleet": latest,
            "calibration_snapshot": calibration_snapshot,
        }

    def build_multi_agent_proposals(self, normalized_events, market_context, truth_layer_status, portfolio_status=None, radar_scan=None):
        proposals = []
        truth_layer_status = truth_layer_status or {}
        normalized_events = list(normalized_events or [])
        market_context = market_context or {}
        portfolio_status = portfolio_status or {}
        radar_candidates = {item.get("symbol"): item for item in (radar_scan or {}).get("candidates", [])}
        restrictions = dict(portfolio_status.get("fleet_restrictions", {}))
        capital_adjustments = dict(portfolio_status.get("capital_adjustments", {}))
        for fleet, context in market_context.items():
            regime = context.get("market_regime", "normal")
            symbol = context.get("symbol")
            sentiment_score = sum(
                1
                for event in normalized_events
                if fleet in (event.get("targets") or []) and event.get("sentiment") == "POSITIVE"
            ) - sum(
                1
                for event in normalized_events
                if fleet in (event.get("targets") or []) and event.get("sentiment") == "NEGATIVE"
            )
            fleet_restriction = restrictions.get(fleet, {})
            capital_plan = capital_adjustments.get(fleet, {})
            radar_candidate = radar_candidates.get(symbol, {})
            recommended_action = "defer" if sentiment_score < 0 else "monitor"
            if radar_candidate and radar_candidate.get("candidate_score", 0) > 0:
                recommended_action = f"watch_{str(radar_candidate.get('candidate_side', 'long')).lower()}"
            proposals.append(
                {
                    "agent": fleet,
                    "proposal_type": "observe" if not truth_layer_status.get("futures_ready_for_ai") else "trade_review",
                    "priority": "high" if regime in {"wide_spread", "thin_liquidity", "low_open_interest"} else "normal",
                    "market_regime": regime,
                    "symbol": symbol,
                    "event_sentiment_score": sentiment_score,
                    "recommended_action": recommended_action,
                    "requires_hq_review": sentiment_score < 0 or regime != "normal" or not fleet_restriction.get("allowed_new_entries", True),
                    "fleet_restriction": fleet_restriction,
                    "capital_plan": capital_plan,
                    "radar_candidate": radar_candidate,
                }
            )
        return {
            "generated_at": _now(),
            "world_channel": proposals,
            "internal_channels": {
                fleet: [proposal for proposal in proposals if proposal["agent"] == fleet]
                for fleet in market_context.keys()
            },
        }

    def build_station_learning_exchange(
        self,
        meetings,
        normalized_events,
        market_context,
        learning_status,
        radar_scan,
        portfolio_status,
    ):
        meetings = list(meetings or [])
        normalized_events = list(normalized_events or [])
        market_context = market_context or {}
        learning_status = learning_status or {}
        radar_scan = radar_scan or {}
        portfolio_status = portfolio_status or {}
        calibration = (learning_status.get("calibration_snapshot") or {}).get("fleet_adjustments", {})
        latest_meeting = meetings[0] if meetings else {}
        highest_risk_events = sorted(
            normalized_events,
            key=lambda item: (item.get("impact") == "HIGH", float(item.get("quality_score", 0.0) or 0.0)),
            reverse=True,
        )[:4]

        station_shares = [
            {
                "station": "HQ",
                "focus": "portfolio_governance",
                "summary": "Portfolio exposure review and capital arbitration.",
                "details": {
                    "reserve_action": portfolio_status.get("reserve_action", "hold"),
                    "notional_utilization": portfolio_status.get("notional_utilization", 0.0),
                    "same_side_concentration": portfolio_status.get("same_side_concentration", 0.0),
                    "correlation_concentration": portfolio_status.get("correlation_concentration", 0.0),
                    "hedge_recommendations": list(portfolio_status.get("hedge_recommendations", []) or []),
                },
            },
            {
                "station": "NEWS",
                "focus": "major_events",
                "summary": "Latest high-impact market events shared across desks.",
                "details": {
                    "event_count": len(highest_risk_events),
                    "events": highest_risk_events,
                },
            },
            {
                "station": "RADAR",
                "focus": "market_scan",
                "summary": "Whole-market scan for candidates and whale-style order-book pressure.",
                "details": {
                    "candidates": list((radar_scan.get("candidates") or [])[:5]),
                    "whale_watch": list((radar_scan.get("whale_watch") or [])[:5]),
                },
            },
        ]

        for fleet, context in market_context.items():
            adjustment = calibration.get(fleet, {})
            station_shares.append(
                {
                    "station": fleet,
                    "focus": "fleet_local_brain",
                    "summary": f"{fleet} desk review for {context.get('symbol', fleet)}.",
                    "details": {
                        "symbol": context.get("symbol"),
                        "market_regime": context.get("market_regime", "normal"),
                        "funding_risk": context.get("funding_risk", "normal"),
                        "slippage_risk": context.get("slippage_risk", "normal"),
                        "liquidation_risk": context.get("liquidation_risk", "none"),
                        "failure_focus": adjustment.get("failure_focus", []),
                        "confidence_penalty": adjustment.get("confidence_penalty", 0.0),
                        "leverage_cap": adjustment.get("leverage_cap"),
                    },
                }
            )

        cross_station_lessons = []
        for fleet, adjustment in calibration.items():
            if adjustment.get("failure_focus"):
                cross_station_lessons.append(
                    {
                        "source_station": fleet,
                        "lesson_type": "loss_avoidance",
                        "headline": f"{fleet} recent loss patterns shared across desks.",
                        "lesson_points": list(adjustment.get("failure_focus", [])),
                    }
                )
        if portfolio_status.get("reserve_action") == "increase_reserve":
            cross_station_lessons.append(
                {
                    "source_station": "HQ",
                    "lesson_type": "portfolio_risk",
                    "headline": "Reduce gross exposure until concentration normalizes.",
                    "lesson_points": list(
                        {
                            "same_side_concentration",
                            "portfolio_utilization",
                        }
                    ),
                }
            )
        if portfolio_status.get("hedge_recommendations"):
            cross_station_lessons.append(
                {
                    "source_station": "HQ",
                    "lesson_type": "hedge_governance",
                    "headline": "Portfolio Brain suggests hedge monitoring due to concentration.",
                    "lesson_points": [item.get("reason", "portfolio_hedge_needed") for item in portfolio_status.get("hedge_recommendations", [])],
                }
            )

        opportunity_board = []
        for candidate in (radar_scan.get("candidates") or [])[:5]:
            opportunity_board.append(
                {
                    "symbol": candidate.get("symbol"),
                    "candidate_side": candidate.get("candidate_side"),
                    "candidate_score": candidate.get("candidate_score"),
                    "reason": candidate.get("reason"),
                }
            )

        return {
            "generated_at": _now(),
            "meeting_reference": latest_meeting.get("meeting_id") or latest_meeting.get("time") or "",
            "station_shares": station_shares,
            "cross_station_lessons": cross_station_lessons,
            "opportunity_board": opportunity_board,
        }
