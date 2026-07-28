"""Market regime router — UNCERTAIN when evidence missing (no guessing)."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow.contracts import MarketObservation, MarketRegime, Regime, now_ms


class RegimeRouter:
    """Deterministic regime classification from observations."""

    def classify(
        self,
        observation: MarketObservation | dict[str, Any] | None,
        *,
        prior_regime: str | None = None,
    ) -> MarketRegime:
        if observation is None:
            return self._uncertain(["observation"], prior_regime, "no_observation")
        obs = observation if isinstance(observation, dict) else observation.to_dict()
        missing: list[str] = []
        momentum = obs.get("momentum")
        volatility = obs.get("volatility")
        spread = obs.get("spread_bps")
        last_price = obs.get("last_price")
        if last_price is None:
            missing.append("last_price")
        if momentum is None:
            missing.append("momentum")
        if volatility is None:
            missing.append("volatility")
        if missing:
            return self._uncertain(missing, prior_regime, "missing_evidence")
        assert momentum is not None and volatility is not None
        supporting: list[str] = []
        contradicting: list[str] = []
        regime = Regime.UNCERTAIN
        if abs(momentum) < 0.05 and volatility < 0.02:
            regime = Regime.RANGE
            supporting.append("low_momentum_low_vol")
        elif momentum > 0.15 and volatility < 0.05:
            regime = Regime.TRENDING_UP
            supporting.append("positive_momentum")
        elif momentum < -0.15 and volatility < 0.05:
            regime = Regime.TRENDING_DOWN
            supporting.append("negative_momentum")
        elif volatility >= 0.08:
            regime = Regime.HIGH_VOLATILITY
            supporting.append("high_volatility")
        elif volatility <= 0.01:
            regime = Regime.LOW_VOLATILITY
            supporting.append("low_volatility")
        elif abs(momentum) > 0.25:
            regime = Regime.BREAKOUT
            supporting.append("momentum_breakout")
        elif momentum * (momentum if prior_regime else 1) < 0:
            regime = Regime.REVERSAL
            supporting.append("momentum_reversal")
        if spread is not None and spread > 50:
            regime = Regime.EVENT_RISK
            supporting.append("wide_spread")
        if regime == Regime.UNCERTAIN:
            return self._uncertain(["ambiguous_signals"], prior_regime, "ambiguous")
        conf = min(0.95, 0.5 + abs(float(momentum)) + float(volatility) * 0.5)
        return MarketRegime(
            symbol=str(obs.get("symbol") or ""),
            regime=regime.value,
            confidence=round(conf, 4),
            confidence_calibration="HEURISTIC",
            supporting_factors=supporting,
            contradicting_factors=contradicting,
            missing_evidence=[],
            data_quality="OK",
            freshness=str(obs.get("freshness") or "FRESH"),
            transition_from=prior_regime,
            transition_reason="regime_update" if prior_regime else None,
        )

    def _uncertain(
        self,
        missing: list[str],
        prior: str | None,
        reason: str,
    ) -> MarketRegime:
        return MarketRegime(
            regime=Regime.UNCERTAIN.value,
            confidence=None,
            confidence_calibration="UNCALIBRATED",
            missing_evidence=missing,
            data_quality="UNKNOWN",
            freshness="UNKNOWN",
            transition_from=prior,
            fallback_reason=reason,
        )
