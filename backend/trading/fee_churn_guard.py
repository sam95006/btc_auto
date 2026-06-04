from __future__ import annotations

import time
from datetime import datetime

from config.fee_churn_config import (
    AI_EXIT_MIN_ABS_PNL_USD,
    AI_LIQ_EXIT_REQUIRES_CRITICAL,
    FEE_CHURN_GUARD_ENABLED,
    FEE_EDGE_MULTIPLIER,
    FUTURES_TAKER_FEE_BPS,
    MIN_HOLD_SECONDS_BEFORE_EXIT,
    MIN_MARGIN_USD,
    MIN_NOTIONAL_USD,
    MIN_SECONDS_BETWEEN_PARTIALS,
    MIN_SYMBOL_REOPEN_SECONDS,
    R_EXIT_MIN_NET_PROFIT_USD,
)
from config.ai_flexible_eval_config import AI_FLEX_EXIT_MIN_CONFIDENCE
from config.sandbox_exit_config import (
    SANDBOX_MIN_HOLD_SECONDS,
    SANDBOX_MIN_PARTIAL_PROFIT_USD,
    SANDBOX_RELAX_EXIT_GUARDS,
)
from backend.trading.sandbox_mode import sandbox_active
from config.micro_validation_config import is_micro_fee_churn_exception


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


def _position_age_seconds(position) -> float:
    opened = str(position.get("opened_at") or "").strip()
    if not opened:
        return 999999.0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return max(0.0, time.time() - datetime.strptime(opened[:19], fmt).timestamp())
        except Exception:
            continue
    return 999999.0


def estimate_round_trip_fee_usd(margin, leverage):
    margin = max(_safe_float(margin), 0.0)
    leverage = max(_safe_float(leverage, 1.0), 1.0)
    notional = margin * leverage
    return notional * (FUTURES_TAKER_FEE_BPS / 10000.0) * 2.0


class FeeChurnGuard:
    """Block micro-trades where round-trip fees exceed realistic edge."""

    def __init__(self):
        self._last_close_at: dict[str, float] = {}
        self._last_partial_at: dict[str, float] = {}

    def _min_hold_seconds(self) -> float:
        if sandbox_active() and SANDBOX_RELAX_EXIT_GUARDS:
            return float(SANDBOX_MIN_HOLD_SECONDS)
        return float(MIN_HOLD_SECONDS_BEFORE_EXIT)

    def _min_partial_profit_usd(self, margin, leverage) -> float:
        if sandbox_active() and SANDBOX_RELAX_EXIT_GUARDS:
            return max(
                float(SANDBOX_MIN_PARTIAL_PROFIT_USD),
                estimate_round_trip_fee_usd(margin, leverage) * 1.2,
            )
        return max(
            R_EXIT_MIN_NET_PROFIT_USD,
            estimate_round_trip_fee_usd(margin, leverage) * FEE_EDGE_MULTIPLIER,
        )

    def allow_open(self, proposal) -> tuple[bool, str | None]:
        if not FEE_CHURN_GUARD_ENABLED:
            return True, None
        proposal = dict(proposal or {})
        if is_micro_fee_churn_exception(proposal):
            return True, None
        symbol = str(proposal.get("symbol") or proposal.get("symbol_override") or "").upper()
        margin = _safe_float(proposal.get("margin"))
        leverage = max(_safe_float(proposal.get("leverage"), 1.0), 1.0)
        if margin < MIN_MARGIN_USD:
            return False, "fee_churn_margin_too_small"
        notional = margin * leverage
        if notional < MIN_NOTIONAL_USD:
            return False, "fee_churn_notional_too_small"
        last_close = float(self._last_close_at.get(symbol, 0.0) or 0.0)
        if symbol and last_close and (time.time() - last_close) < MIN_SYMBOL_REOPEN_SECONDS:
            return False, "fee_churn_symbol_reopen_cooldown"
        min_edge = max(
            estimate_round_trip_fee_usd(margin, leverage) * FEE_EDGE_MULTIPLIER,
            R_EXIT_MIN_NET_PROFIT_USD * 0.5,
        )
        confidence = _safe_float(
            proposal.get("adjusted_confidence")
            or proposal.get("confidence_score")
            or proposal.get("confidence")
        )
        implied_edge = margin * max(0.04, confidence * 0.12)
        if implied_edge < min_edge:
            return False, "fee_churn_expected_edge_too_small"
        return True, None

    def allow_ai_exit(self, position, action) -> tuple[bool, str | None]:
        if not FEE_CHURN_GUARD_ENABLED:
            return True, None
        position = dict(position or {})
        action = dict(action or {})
        reason = str(action.get("reason") or "")
        unrealized = _safe_float(position.get("unrealized_pnl"))
        age = _position_age_seconds(position)
        if str(action.get("source") or "") in {
            "ai_flex_exit",
            "ai_flex_auto_profit",
            "pure_ai_safety",
            "pure_ai_hard_exit",
        }:
            if str(action.get("source") or "") == "pure_ai_hard_exit" or str(action.get("urgency") or "") == "critical":
                return True, None
            confidence = _safe_float(action.get("confidence"))
            if confidence >= AI_FLEX_EXIT_MIN_CONFIDENCE:
                return True, None
        if age < self._min_hold_seconds():
            return False, "fee_churn_min_hold_not_met"
        if reason == "liquidation_pressure":
            liq_risk = str((action.get("market_context") or {}).get("liquidation_risk") or "").lower()
            if AI_LIQ_EXIT_REQUIRES_CRITICAL and liq_risk != "critical":
                return False, "fee_churn_liq_not_critical"
        if abs(unrealized) < AI_EXIT_MIN_ABS_PNL_USD and reason in {
            "liquidation_pressure",
            "profit_lock_near_liquidation_band",
        }:
            return False, "fee_churn_ai_exit_pnl_too_small"
        return True, None

    def allow_r_partial(self, position, unrealized_pnl) -> tuple[bool, str | None]:
        if not FEE_CHURN_GUARD_ENABLED:
            return True, None
        position = dict(position or {})
        unrealized = _safe_float(unrealized_pnl)
        if unrealized <= 0:
            return False, "fee_churn_partial_requires_profit"
        age = _position_age_seconds(position)
        if age < self._min_hold_seconds():
            return False, "fee_churn_min_hold_not_met"
        pos_id = str(position.get("id") or "")
        last_partial = float(self._last_partial_at.get(pos_id, 0.0) or 0.0)
        if pos_id and last_partial and (time.time() - last_partial) < MIN_SECONDS_BETWEEN_PARTIALS:
            return False, "fee_churn_partial_cooldown"
        margin = _safe_float(position.get("margin"))
        leverage = max(_safe_float(position.get("leverage"), 1.0), 1.0)
        min_profit = self._min_partial_profit_usd(margin, leverage)
        if unrealized < min_profit:
            return False, "fee_churn_partial_profit_below_fees"
        return True, None

    def mark_symbol_closed(self, symbol):
        symbol = str(symbol or "").upper()
        if symbol:
            self._last_close_at[symbol] = time.time()

    def mark_partial_exit(self, position_id):
        pos_id = str(position_id or "")
        if pos_id:
            self._last_partial_at[pos_id] = time.time()


_DEFAULT_GUARD = FeeChurnGuard()


def get_fee_churn_guard() -> FeeChurnGuard:
    return _DEFAULT_GUARD
