from __future__ import annotations

from datetime import datetime

from config.portfolio_config import (
    FLEET_BASE_CAPITAL_MULTIPLIER,
    FLEET_CORRELATION_GROUPS,
    FLEET_THEME_TAGS,
    HEDGE_TRIGGER_CONCENTRATION,
    HEDGE_TRIGGER_UTILIZATION,
    MAX_SAME_SIDE_SHARE,
    MAX_CORRELATED_GROUP_SHARE,
    MAX_SINGLE_FLEET_SHARE,
    MAX_TOTAL_NOTIONAL_UTILIZATION,
    REGIME_CAPITAL_MULTIPLIER,
    WARNING_TOTAL_NOTIONAL_UTILIZATION,
)


from backend.trading.exchange_capital_view import futures_equity_from_account


def _safe_float(value):
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class PortfolioGovernor:
    def evaluate(self, futures_account, market_context, radar_scan=None, learning_snapshot=None):
        futures_account = futures_account or {}
        market_context = market_context or {}
        radar_scan = radar_scan or {}
        learning_snapshot = learning_snapshot or {}

        positions = list(futures_account.get("positions", []) or [])
        treasury_margin = futures_equity_from_account(futures_account)
        margin_balance = max(treasury_margin, _safe_float(futures_account.get("margin_total")), 1.0)
        exposures = {}
        total_notional = 0.0
        side_totals = {"LONG": 0.0, "SHORT": 0.0}
        correlation_groups = {}
        theme_exposures = {}

        for position in positions:
            fleet = str(position.get("fleet") or "UNKNOWN").upper()
            side = str(position.get("side") or "HOLD").upper()
            mark_price = _safe_float(position.get("mark_price"))
            quantity = abs(_safe_float(position.get("quantity")))
            notional = quantity * mark_price
            total_notional += notional
            side_totals["LONG" if side == "BUY" else "SHORT"] += notional
            correlation_group = FLEET_CORRELATION_GROUPS.get(fleet, "other")
            correlation_groups[correlation_group] = correlation_groups.get(correlation_group, 0.0) + notional
            for theme in FLEET_THEME_TAGS.get(fleet, ()):
                theme_exposures[theme] = theme_exposures.get(theme, 0.0) + notional
            exposures[fleet] = {
                "symbol": position.get("symbol"),
                "side": side,
                "notional": round(notional, 4),
                "share_of_margin": round(notional / margin_balance, 4) if margin_balance else 0.0,
                "unrealized_pnl": round(_safe_float(position.get("unrealized_pnl")), 4),
            }

        utilization = total_notional / margin_balance if margin_balance else 0.0
        side_concentration = max(side_totals.values()) / total_notional if total_notional > 0 else 0.0
        correlation_concentration = (
            max(correlation_groups.values()) / total_notional if total_notional > 0 and correlation_groups else 0.0
        )
        reserve_action = "hold"
        if utilization >= MAX_TOTAL_NOTIONAL_UTILIZATION or side_concentration >= MAX_SAME_SIDE_SHARE:
            reserve_action = "increase_reserve"
        elif utilization >= WARNING_TOTAL_NOTIONAL_UTILIZATION:
            reserve_action = "caution"

        fleet_restrictions = {}
        capital_adjustments = {}
        candidate_bias = {item.get("symbol"): item for item in (radar_scan.get("candidates") or [])}
        fleet_learning = ((learning_snapshot.get("fleet_adjustments") or learning_snapshot.get("calibration_snapshot", {}).get("fleet_adjustments") or {}))

        for fleet, context in market_context.items():
            regime = str(context.get("market_regime") or "normal")
            base_multiplier = FLEET_BASE_CAPITAL_MULTIPLIER.get(fleet, 1.0)
            regime_multiplier = REGIME_CAPITAL_MULTIPLIER.get(regime, 0.75)
            exposure_share = _safe_float((exposures.get(fleet) or {}).get("share_of_margin"))
            learning = fleet_learning.get(fleet, {})
            aggression_multiplier = _safe_float(learning.get("aggression_multiplier") or 1.0)
            leverage_cap = learning.get("leverage_cap")

            allowed = True
            reasons = []
            if exposure_share >= MAX_SINGLE_FLEET_SHARE:
                allowed = False
                reasons.append("single_fleet_exposure_limit")
            if regime in {"liquidation_risk", "high_slippage", "thin_liquidity"}:
                reasons.append(f"market_regime_{regime}")
            if utilization >= MAX_TOTAL_NOTIONAL_UTILIZATION:
                reasons.append("portfolio_utilization_too_high")
            if side_concentration >= MAX_SAME_SIDE_SHARE:
                reasons.append("same_side_concentration_too_high")
            if correlation_concentration >= MAX_CORRELATED_GROUP_SHARE:
                reasons.append("correlated_group_concentration_too_high")

            symbol = context.get("symbol")
            radar_candidate = candidate_bias.get(symbol, {})
            if radar_candidate:
                reasons.append(f"radar_candidate_{radar_candidate.get('candidate_side', 'watch').lower()}")

            recommended_multiplier = round(
                max(0.3, min(1.0, base_multiplier * regime_multiplier * max(0.5, aggression_multiplier))),
                4,
            )
            capital_adjustments[fleet] = {
                "capital_multiplier": recommended_multiplier,
                "max_new_notional_share": round(min(MAX_SINGLE_FLEET_SHARE, recommended_multiplier * MAX_SINGLE_FLEET_SHARE), 4),
                "leverage_cap": leverage_cap,
                "reason": reasons or ["normal"],
            }
            fleet_restrictions[fleet] = {
                "allowed_new_entries": allowed and regime not in {"liquidation_risk", "thin_liquidity"},
                "reasons": reasons,
                "market_regime": regime,
                "symbol": symbol,
            }

        hedge_recommendations = []
        if side_concentration >= HEDGE_TRIGGER_CONCENTRATION or utilization >= HEDGE_TRIGGER_UTILIZATION:
            dominant_side = "LONG" if side_totals["LONG"] >= side_totals["SHORT"] else "SHORT"
            hedge_side = "SHORT" if dominant_side == "LONG" else "LONG"
            if correlation_groups:
                dominant_group = max(correlation_groups.items(), key=lambda item: item[1])[0]
                hedge_symbol = "BTCUSDT" if dominant_group in {"alts", "memes"} else "ETHUSDT"
            else:
                dominant_group = "other"
                hedge_symbol = "BTCUSDT"
            hedge_recommendations.append(
                {
                    "action": "add_hedge_watch",
                    "hedge_symbol": hedge_symbol,
                    "hedge_side": hedge_side,
                    "reason": "portfolio_concentration_or_utilization_high",
                    "dominant_side": dominant_side,
                    "dominant_group": dominant_group,
                }
            )

        return {
            "generated_at": _now(),
            "margin_balance": round(margin_balance, 4),
            "total_open_notional": round(total_notional, 4),
            "notional_utilization": round(utilization, 4),
            "same_side_concentration": round(side_concentration, 4),
            "correlation_concentration": round(correlation_concentration, 4),
            "reserve_action": reserve_action,
            "side_totals": {key: round(value, 4) for key, value in side_totals.items()},
            "correlation_groups": {key: round(value, 4) for key, value in correlation_groups.items()},
            "theme_exposures": {key: round(value, 4) for key, value in theme_exposures.items()},
            "fleet_exposures": exposures,
            "fleet_restrictions": fleet_restrictions,
            "capital_adjustments": capital_adjustments,
            "hedge_recommendations": hedge_recommendations,
        }
