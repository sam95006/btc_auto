"""Rule-based 0-100 confidence matrix: technical 30 + on-chain 40 + macro 30."""

from __future__ import annotations

from typing import Any, Dict, Optional

from config.confidence_matrix_config import CONFIDENCE_MATRIX_ENABLED, POSTMORTEM_MACRO_PENALTY
from config.regime_config import REGIME_LABELS


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


class ConfidenceMatrixEngine:
    MAX_TECHNICAL = 30.0
    MAX_ONCHAIN = 40.0
    MAX_MACRO = 30.0

    def __init__(self, *, enabled: bool = None):
        self.enabled = CONFIDENCE_MATRIX_ENABLED if enabled is None else bool(enabled)

    def score(
        self,
        proposal: Dict[str, Any],
        market_context: Optional[Dict[str, Any]] = None,
        regime_state: Optional[Dict[str, Any]] = None,
        macro_penalty: float = 0.0,
    ) -> Dict[str, Any]:
        proposal = dict(proposal or {})
        ctx = dict(market_context or {})
        regime_state = dict(regime_state or {})
        side = str(proposal.get("side") or "BUY").upper()

        technical, tech_breakdown = self._score_technical(ctx, side)
        onchain, chain_breakdown = self._score_onchain(ctx, side)
        macro, macro_breakdown = self._score_macro(ctx, side, regime_state, macro_penalty)

        total = _clamp_score(technical + onchain + macro)
        return {
            "confidence_score": round(total, 2),
            "technical_score": round(technical, 2),
            "onchain_score": round(onchain, 2),
            "macro_score": round(macro, 2),
            "breakdown": {
                "technical": tech_breakdown,
                "onchain": chain_breakdown,
                "macro": macro_breakdown,
            },
            "regime_label": regime_state.get("label"),
            "macro_penalty_applied": round(float(macro_penalty or 0.0), 2),
        }

    def _score_technical(self, ctx: Dict[str, Any], side: str):
        breakdown = {}
        score = 0.0
        trend = str(ctx.get("trend_bias") or "neutral").lower()
        fast_bias = str(ctx.get("technical_5m_bias") or ctx.get("fast_trend_bias") or trend).lower()
        if side == "BUY" and trend in {"bullish"} and fast_bias in {"bullish", trend}:
            score += 12.0
            breakdown["mtf_bull_align"] = 12
        elif side == "SELL" and trend in {"bearish"} and fast_bias in {"bearish", trend}:
            score += 12.0
            breakdown["mtf_bear_align"] = 12
        else:
            breakdown["mtf_align"] = 0

        ema_cross = str(ctx.get("ema_cross") or "")
        if side == "BUY" and ema_cross in {"bullish_cross", "bullish"}:
            score += 8.0
            breakdown["ema"] = 8
        elif side == "SELL" and ema_cross in {"bearish_cross", "bearish"}:
            score += 8.0
            breakdown["ema"] = 8

        rsi = _safe_float(ctx.get("rsi_14"), 50.0)
        if 32.0 <= rsi <= 68.0:
            score += 5.0
            breakdown["rsi_neutral"] = 5
        if ctx.get("volume_confirmed"):
            score += 5.0
            breakdown["volume"] = 5

        return min(self.MAX_TECHNICAL, score), breakdown

    def _score_onchain(self, ctx: Dict[str, Any], side: str):
        breakdown = {}
        score = 0.0
        if ctx.get("coingecko_liquidity_ok", True):
            score += 10.0
            breakdown["liquidity"] = 10
        if not ctx.get("external_oi_stress"):
            score += 10.0
            breakdown["oi_ok"] = 10
        if not ctx.get("external_whale_dump_alert"):
            score += 10.0
            breakdown["no_whale_dump"] = 10

        funding = _safe_float(ctx.get("funding_rate"))
        if side == "BUY" and funding <= 0:
            score += 10.0
            breakdown["funding_long_edge"] = 10
        elif side == "SELL" and funding >= 0:
            score += 10.0
            breakdown["funding_short_edge"] = 10
        elif abs(funding) < 0.0005:
            score += 5.0
            breakdown["funding_neutral"] = 5

        return min(self.MAX_ONCHAIN, score), breakdown

    def _score_macro(
        self,
        ctx: Dict[str, Any],
        side: str,
        regime_state: Dict[str, Any],
        macro_penalty: float,
    ):
        breakdown = {}
        label = str(regime_state.get("label") or ctx.get("market_regime_ai") or "CHOP_RNG").upper()
        if label not in REGIME_LABELS:
            label = "CHOP_RNG"

        if label == "HIGH_RISK_MACRO":
            base = 2.0
        elif label == "TREND_BULL":
            base = 26.0 if side == "BUY" else 12.0
        else:
            base = 12.0

        penalty = min(POSTMORTEM_MACRO_PENALTY, max(0.0, float(macro_penalty or 0.0)))
        score = max(0.0, base - penalty)
        breakdown["regime_base"] = base
        breakdown["postmortem_penalty"] = penalty
        breakdown["label"] = label
        return min(self.MAX_MACRO, score), breakdown
