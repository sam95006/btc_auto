"""Public market data pipeline — rate limit, timeout, retry, backoff, circuit breaker."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_global_shadow.universe import ProviderCircuitBreaker, RateLimitState
from backend.nexus_real_shadow.market_data import MarketDataBundle, MarketDataCoordinator
from backend.nexus_real_shadow.provider import BybitPublicHttpClient


def _estimate_liquidity_score(raw: dict[str, Any]) -> float | None:
    turnover = raw.get("turnover_24h")
    spread = raw.get("spread_bps")
    if turnover is None:
        return None
    base = min(100.0, (float(turnover) / 1_000_000) * 0.8)
    if spread is not None:
        base = max(0.0, base - float(spread) * 0.5)
    return round(base, 2)


def _estimate_slippage_bps(raw: dict[str, Any]) -> float | None:
    spread = raw.get("spread_bps")
    if spread is None:
        return None
    return round(float(spread) * 0.25, 4)


def enrich_market_dict(merged: dict[str, Any]) -> dict[str, Any]:
    """Add derived quality fields; never substitute fake zeros for missing fee/funding."""
    out = dict(merged)
    if out.get("liquidity_score") is None:
        out["liquidity_score"] = _estimate_liquidity_score(out)
    if out.get("estimated_slippage") is None:
        slip = _estimate_slippage_bps(out)
        if slip is not None:
            out["estimated_slippage"] = slip / 10_000
    out.setdefault("price_freshness", out.get("freshness") or "MISSING")
    out.setdefault("orderbook_freshness", out.get("orderbook_freshness") or "MISSING")
    out.setdefault("provider_quality", "OK" if out.get("last_price") is not None else "DEGRADED")
    return out


@dataclass
class PublicMarketPipeline:
    """Coordinator with rate limit, circuit breaker, and optional live provider."""

    use_fixtures: bool = True
    client: BybitPublicHttpClient | None = None
    coordinator: MarketDataCoordinator | None = None
    rate_limit: RateLimitState = field(default_factory=RateLimitState)
    circuit_breaker: ProviderCircuitBreaker = field(default_factory=ProviderCircuitBreaker)
    fetch_count: int = 0

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = BybitPublicHttpClient(use_fixtures=self.use_fixtures)
        if self.coordinator is None:
            self.coordinator = MarketDataCoordinator(use_fixtures=self.use_fixtures)

    def fetch_symbol(self, symbol: str) -> MarketDataBundle:
        if self.circuit_breaker.open:
            return MarketDataBundle(symbol=symbol, status="CIRCUIT_OPEN")
        if not self.rate_limit.allow():
            return MarketDataBundle(symbol=symbol, status="RATE_LIMITED")
        self.fetch_count += 1
        try:
            bundle = self.coordinator.fetch_symbol(symbol)
            self.circuit_breaker.record_success()
            return bundle
        except Exception as exc:
            self.circuit_breaker.record_failure(str(exc))
            return MarketDataBundle(symbol=symbol, status="UNAVAILABLE")

    def fetch_many(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for sym in symbols:
            bundle = self.fetch_symbol(sym)
            merged = enrich_market_dict(bundle.merged_quality_input())
            merged["symbol"] = sym
            merged["status"] = bundle.status
            out[sym] = merged
        return out

    def pipeline_stats(self) -> dict[str, Any]:
        return {
            "fetch_count": self.fetch_count,
            "circuit_open": self.circuit_breaker.open,
            "rate_limit_calls": len(self.rate_limit.calls),
            "http_stats": self.client.stats() if self.client else {},
        }


# Backward-compatible alias
MarketDataPipeline = PublicMarketPipeline

__all__ = [
    "PublicMarketPipeline",
    "MarketDataPipeline",
    "MarketDataCoordinator",
    "MarketDataBundle",
    "enrich_market_dict",
]
