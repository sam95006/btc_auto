"""Strategy router — blocks UNCERTAIN regime; supports formal + experimental strategies."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow.contracts import (
    IntelligenceSnapshot,
    MarketObservation,
    MarketQualitySnapshot,
    MarketRegime,
    Regime,
    StrategyContext,
)

FORMAL_STRATEGIES = frozenset(
    {
        "trend_following",
        "pullback",
        "breakout",
        "momentum",
        "vwap_mean_reversion",
        "liquidity_sweep",
        "absorption_cvd_divergence",
        "funding_oi_contrarian",
    }
)

EXPERIMENTAL_STRATEGIES = frozenset(
    {
        "dynamic_grid",
        "pairs_trading",
        "funding_delta_neutral",
    }
)

REGIME_STRATEGY_MAP: dict[str, list[str]] = {
    Regime.TRENDING_UP.value: ["trend_following", "pullback", "momentum"],
    Regime.TRENDING_DOWN.value: ["trend_following", "pullback", "momentum"],
    Regime.RANGE.value: ["vwap_mean_reversion", "liquidity_sweep"],
    Regime.HIGH_VOLATILITY.value: ["breakout", "liquidity_sweep"],
    Regime.LOW_VOLATILITY.value: ["vwap_mean_reversion", "pullback"],
    Regime.BREAKOUT.value: ["breakout", "momentum"],
    Regime.REVERSAL.value: ["absorption_cvd_divergence", "pullback"],
    Regime.EVENT_RISK.value: ["funding_oi_contrarian"],
}


class StrategyRouter:
    """Route strategy from observation, quality, regime, intelligence."""

    def route(
        self,
        strategy_id: str,
        observation: MarketObservation | dict[str, Any] | None,
        quality: MarketQualitySnapshot | dict[str, Any] | None,
        regime: MarketRegime | dict[str, Any] | None,
        intelligence: IntelligenceSnapshot | dict[str, Any] | None = None,
    ) -> StrategyContext:
        regime_val = _field(regime, "regime", Regime.UNCERTAIN.value)
        missing: list[str] = []
        blocks: list[str] = []
        if regime_val == Regime.UNCERTAIN.value:
            blocks.append("regime_uncertain")
        if observation is None:
            missing.append("observation")
        if quality is None:
            missing.append("quality")
        sid = strategy_id.lower().replace(" ", "_").replace("/", "_")
        if sid in EXPERIMENTAL_STRATEGIES:
            status = "EXPERIMENTAL"
        elif sid in FORMAL_STRATEGIES:
            status = "ACTIVE" if not blocks and not missing else "BLOCKED"
        else:
            blocks.append(f"unknown_strategy:{sid}")
            status = "BLOCKED"
        allowed = REGIME_STRATEGY_MAP.get(regime_val, [])
        fit = 0.0
        if sid in allowed and regime_val != Regime.UNCERTAIN.value:
            fit = 0.7
        elif sid in allowed:
            fit = 0.3
        if blocks or missing:
            status = "BLOCKED"
            fit = None
        return StrategyContext(
            symbol=_field(observation, "symbol", ""),
            strategy_id=sid,
            strategy_fit=fit,
            strategy_status=status,
            entry_prerequisites=[f"regime:{regime_val}"] if regime_val != Regime.UNCERTAIN.value else [],
            invalidation="regime_change_or_data_loss",
            required_evidence=["observation", "quality", "regime"],
            missing_evidence=missing,
            block_reasons=blocks,
        )

    def list_for_regime(self, regime: str) -> list[str]:
        if regime == Regime.UNCERTAIN.value:
            return []
        return list(REGIME_STRATEGY_MAP.get(regime, []))


def _field(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
