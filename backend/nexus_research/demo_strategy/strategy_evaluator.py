"""Demo strategy — strategy evaluator with mandatory Risk Critic.

Evaluates BTCUSDT/ETHUSDT/SOLUSDT long/short composite scores.
Risk Critic is MANDATORY — if it vetoes, allow_trade=false regardless of score.
Gates are NEVER lowered to force candidates through.

Pure local computation. No orders. No secrets.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_strategy.candidate_ranking import (
    STRATEGY_CANDIDATE_RANKING,
    StrategyCandidate,
    get_candidates_for_symbol,
)
from backend.nexus_research.demo_strategy.market_features import (
    MarketFeatures,
    extract_features,
)

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Risk Critic thresholds (never lowered) ────────────────────────────────────
_CRITIC_GATES: dict[str, Any] = {
    "rsi_overbought": 78.0,
    "rsi_oversold": 22.0,
    "max_spread_bps": 12.0,
    "max_freshness_ms": 120_000,
    "max_atr_pct_volatile": 5.0,
    "min_volume_24h_usd": 500_000_000.0,
    "funding_crowding_pct": 0.08,
}


@dataclass
class EvaluationResult:
    """Output of strategy evaluation for one symbol+direction."""

    symbol: str
    direction: str
    composite_score: float
    allow_trade: bool
    block_reasons: list[str] = field(default_factory=list)
    risk_critic_pass: bool = True
    gate_checks: dict[str, str] = field(default_factory=dict)
    features_used: dict[str, Any] = field(default_factory=dict)
    evaluated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "compositeScore": self.composite_score,
            "allowTrade": self.allow_trade,
            "blockReasons": self.block_reasons,
            "riskCriticPass": self.risk_critic_pass,
            "gateChecks": self.gate_checks,
            "featuresUsed": self.features_used,
            "evaluatedAtMs": self.evaluated_at_ms,
            "researchOnly": True,
        }


def _compute_composite_score(features: MarketFeatures, direction: str) -> float:
    """Weighted composite: trend 35%, momentum 25%, RSI 20%, volume/OI 10%, funding 10%."""
    trend = features.trend_score
    momentum = features.momentum_score

    if direction == "SHORT":
        trend = -trend
        momentum = -momentum

    trend_norm = (trend + 100.0) / 200.0 * 100.0
    momentum_norm = (momentum + 100.0) / 200.0 * 100.0

    rsi_raw = features.rsi_14 if features.rsi_14 is not None else 50.0
    if direction == "LONG":
        rsi_component = max(0.0, min(100.0, 100.0 - abs(rsi_raw - 45.0) * 2.0))
    else:
        rsi_component = max(0.0, min(100.0, 100.0 - abs(rsi_raw - 55.0) * 2.0))

    vol_component = 50.0
    if features.volume_24h_usd is not None:
        if features.volume_24h_usd > 10_000_000_000:
            vol_component = 80.0
        elif features.volume_24h_usd > 1_000_000_000:
            vol_component = 60.0

    funding_component = 50.0
    if features.funding_rate_8h_pct is not None:
        fr = features.funding_rate_8h_pct
        if direction == "LONG" and fr < 0.02:
            funding_component = 70.0
        elif direction == "SHORT" and fr > 0.02:
            funding_component = 70.0
        elif abs(fr) > 0.05:
            funding_component = 30.0

    composite = (
        trend_norm * 0.35
        + momentum_norm * 0.25
        + rsi_component * 0.20
        + vol_component * 0.10
        + funding_component * 0.10
    )
    return round(max(0.0, min(100.0, composite)), 2)


def _run_risk_critic(
    features: MarketFeatures,
    direction: str,
    gates: dict[str, Any] | None = None,
) -> tuple[bool, list[str], dict[str, str]]:
    """Mandatory Risk Critic. Returns (pass, block_reasons, gate_checks)."""
    g = gates or _CRITIC_GATES
    reasons: list[str] = []
    checks: dict[str, str] = {}

    if features.rsi_14 is not None:
        if direction == "LONG" and features.rsi_14 > g["rsi_overbought"]:
            reasons.append(f"RSI {features.rsi_14:.1f} overbought for LONG (>{g['rsi_overbought']})")
            checks["rsi"] = "BLOCK"
        elif direction == "SHORT" and features.rsi_14 < g["rsi_oversold"]:
            reasons.append(f"RSI {features.rsi_14:.1f} oversold for SHORT (<{g['rsi_oversold']})")
            checks["rsi"] = "BLOCK"
        else:
            checks["rsi"] = "OK"
    else:
        checks["rsi"] = "MISSING"
        reasons.append("RSI data missing — critic requires RSI")

    if features.spread_bps is not None:
        if features.spread_bps > g["max_spread_bps"]:
            reasons.append(f"Spread {features.spread_bps:.1f}bps > max {g['max_spread_bps']}bps")
            checks["spread"] = "BLOCK"
        else:
            checks["spread"] = "OK"
    else:
        checks["spread"] = "MISSING"
        reasons.append("Spread data missing — critic requires spread")

    if features.freshness_ms > g["max_freshness_ms"]:
        reasons.append(
            f"Data age {features.freshness_ms}ms > max {g['max_freshness_ms']}ms"
        )
        checks["freshness"] = "BLOCK"
    else:
        checks["freshness"] = "OK"

    if features.atr_pct is not None and features.atr_pct > g["max_atr_pct_volatile"]:
        reasons.append(
            f"ATR {features.atr_pct:.1f}% exceeds volatility gate {g['max_atr_pct_volatile']}%"
        )
        checks["volatility"] = "BLOCK"
    else:
        checks["volatility"] = "OK"

    if features.volume_24h_usd is not None:
        if features.volume_24h_usd < g["min_volume_24h_usd"]:
            reasons.append(
                f"Volume ${features.volume_24h_usd:,.0f} < min ${g['min_volume_24h_usd']:,.0f}"
            )
            checks["volume"] = "BLOCK"
        else:
            checks["volume"] = "OK"
    else:
        checks["volume"] = "MISSING"
        reasons.append("Volume data missing — critic requires volume")

    if features.funding_rate_8h_pct is not None:
        if abs(features.funding_rate_8h_pct) > g["funding_crowding_pct"]:
            reasons.append(
                f"Funding {features.funding_rate_8h_pct:.4f}% crowded "
                f"(|rate| > {g['funding_crowding_pct']}%)"
            )
            checks["funding_crowding"] = "BLOCK"
        else:
            checks["funding_crowding"] = "OK"
    else:
        checks["funding_crowding"] = "SKIP"

    critic_pass = len(reasons) == 0
    return critic_pass, reasons, checks


def evaluate(
    features: MarketFeatures,
    direction: str,
    *,
    candidate_config: StrategyCandidate | None = None,
    critic_gates: dict[str, Any] | None = None,
) -> EvaluationResult:
    """Evaluate a single symbol+direction.

    Risk Critic is mandatory. If critic blocks, allow_trade=false
    regardless of composite score.
    """
    if candidate_config is None:
        candidates = get_candidates_for_symbol(features.symbol)
        candidate_config = next(
            (c for c in candidates if c.direction in (direction, "BOTH")),
            None,
        )

    composite = _compute_composite_score(features, direction)
    critic_pass, block_reasons, gate_checks = _run_risk_critic(
        features, direction, critic_gates
    )

    min_score = candidate_config.min_score if candidate_config else 60.0

    if composite < min_score:
        block_reasons.insert(
            0, f"Composite score {composite:.2f} < min {min_score:.1f}"
        )

    if candidate_config is None:
        block_reasons.insert(
            0,
            f"No candidate config for {features.symbol} direction={direction}",
        )
    elif candidate_config.direction not in (direction, "BOTH"):
        block_reasons.insert(
            0,
            f"Direction {direction} not allowed for {features.symbol} "
            f"(allowed: {candidate_config.direction})",
        )

    allow_trade = critic_pass and composite >= min_score and len(block_reasons) == 0

    return EvaluationResult(
        symbol=features.symbol,
        direction=direction,
        composite_score=composite,
        allow_trade=allow_trade,
        block_reasons=block_reasons,
        risk_critic_pass=critic_pass,
        gate_checks=gate_checks,
        features_used=features.to_dict(),
    )


def evaluate_all(
    market_data: dict[str, dict[str, Any]] | None = None,
    *,
    source: str = "fixture",
    critic_gates: dict[str, Any] | None = None,
) -> list[EvaluationResult]:
    """Evaluate all ranked candidates. Returns results sorted by composite score desc."""
    from backend.nexus_research.demo_strategy.market_features import (
        FIXTURE_BTCUSDT,
        FIXTURE_ETHUSDT,
        FIXTURE_SOLUSDT,
    )

    defaults = {
        "BTCUSDT": FIXTURE_BTCUSDT,
        "ETHUSDT": FIXTURE_ETHUSDT,
        "SOLUSDT": FIXTURE_SOLUSDT,
    }
    data = market_data or defaults

    results: list[EvaluationResult] = []
    for candidate in STRATEGY_CANDIDATE_RANKING:
        raw = data.get(candidate.symbol)
        if raw is None:
            continue
        features = extract_features(raw, source=source)

        directions = ["LONG", "SHORT"] if candidate.direction == "BOTH" else [candidate.direction]
        for d in directions:
            results.append(
                evaluate(features, d, candidate_config=candidate, critic_gates=critic_gates)
            )

    results.sort(key=lambda r: r.composite_score, reverse=True)
    return results
