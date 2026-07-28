"""Global market intelligence composer."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow import BENCHMARK_SYMBOLS
from backend.nexus_global_shadow.contracts import (
    IntelligenceSnapshot,
    MarketObservation,
    MarketQualitySnapshot,
    MarketRegime,
    Regime,
)


class GlobalMarketIntelligenceComposer:
    """Compose intelligence snapshot; news UNAVAILABLE when absent."""

    def compose(
        self,
        symbol: str,
        observation: MarketObservation | dict[str, Any] | None,
        quality: MarketQualitySnapshot | dict[str, Any] | None,
        regime: MarketRegime | dict[str, Any] | None,
        *,
        news_items: list[dict[str, Any]] | None = None,
        benchmark_observations: dict[str, dict[str, Any]] | None = None,
        market_breadth: dict[str, Any] | None = None,
    ) -> IntelligenceSnapshot:
        obs = _to_dict(observation)
        qual = _to_dict(quality)
        reg = _to_dict(regime)
        missing: list[str] = []
        supporting: list[str] = []
        contradicting: list[str] = []
        if not obs:
            missing.append("observation")
        if not qual:
            missing.append("quality")
        last_price = obs.get("last_price") if obs else None
        momentum = obs.get("momentum") if obs else None
        volatility = obs.get("volatility") if obs else None
        if last_price is None:
            missing.append("last_price")
        news_avail = "AVAILABLE" if news_items else "UNAVAILABLE"
        benchmark_ctx: dict[str, Any] = {"mode": "BENCHMARK_ONLY", "symbols": list(BENCHMARK_SYMBOLS)}
        if benchmark_observations:
            for bsym in ("BTCUSDT", "ETHUSDT"):
                if bsym in benchmark_observations:
                    benchmark_ctx[bsym] = {
                        "last_price": benchmark_observations[bsym].get("last_price"),
                        "momentum": benchmark_observations[bsym].get("momentum"),
                    }
        if momentum is not None and momentum > 0:
            supporting.append("positive_momentum")
        elif momentum is not None and momentum < 0:
            contradicting.append("negative_momentum")
        return IntelligenceSnapshot(
            symbol=symbol,
            price_structure="UNKNOWN" if last_price is None else "AVAILABLE",
            momentum=momentum,
            volatility=volatility,
            volume=obs.get("volume_24h") if obs else None,
            liquidity=obs.get("liquidity_score") if obs else None,
            spread=qual.get("spread_bps") if qual else None,
            depth=(qual.get("bid_depth") if qual else None),
            orderbook_imbalance=qual.get("depth_imbalance") if qual else None,
            funding=obs.get("funding_rate") if obs else qual.get("funding_rate") if qual else None,
            open_interest=obs.get("open_interest") if obs else qual.get("open_interest") if qual else None,
            liquidation_context="MISSING",
            long_short_ratio=None,
            market_quality=str(qual.get("quality") or "UNKNOWN") if qual else "UNKNOWN",
            cross_market_context={},
            benchmark_context=benchmark_ctx,
            market_breadth=market_breadth or {},
            news_context_availability=news_avail,
            event_risk="UNKNOWN",
            provider_quality=str(qual.get("provider_quality") or "UNKNOWN") if qual else "UNKNOWN",
            data_anomalies=list(qual.get("anomaly_flags") or []) if qual else [],
            regime=str(reg.get("regime") or Regime.UNCERTAIN.value),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            freshness=str(obs.get("freshness") or "UNKNOWN") if obs else "MISSING",
            quality=str(qual.get("quality") or "UNKNOWN") if qual else "UNKNOWN",
            trace={"composer": "GlobalMarketIntelligenceComposer"},
        )


def _to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return {}
