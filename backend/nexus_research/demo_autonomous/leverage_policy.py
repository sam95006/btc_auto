"""Confidence + tier + equity-aware leverage policy for Bybit Demo."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_research.demo_autonomous.universe import LiquidityTier

MIN_CONFIDENCE = 65.0
MIN_LIQ_BUFFER_PCT = 2.0


@dataclass(frozen=True)
class LeverageRange:
    low: int
    mid: int
    high: int
    absolute_max: int


TIER_RANGES: dict[LiquidityTier, LeverageRange] = {
    LiquidityTier.TIER_A_MAJOR: LeverageRange(25, 30, 35, 50),
    LiquidityTier.TIER_B_LARGE: LeverageRange(20, 25, 30, 35),
    LiquidityTier.TIER_C_MID: LeverageRange(10, 15, 20, 25),
    LiquidityTier.TIER_D_SMALL_HIGH_RISK: LeverageRange(5, 10, 15, 20),
}


@dataclass
class LeverageDecision:
    selected: int
    allowed_range: tuple[int, int]
    instrument_max: float
    tier: str
    confidence: float
    liquidation_distance_pct: float
    stop_to_liq_buffer_pct: float
    allow: bool
    block_reasons: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "allowedRange": list(self.allowed_range),
            "instrumentMax": self.instrument_max,
            "tier": self.tier,
            "confidence": self.confidence,
            "liquidationDistancePct": self.liquidation_distance_pct,
            "stopToLiqBufferPct": self.stop_to_liq_buffer_pct,
            "allow": self.allow,
            "blockReasons": list(self.block_reasons),
            "notes": list(self.notes),
        }


def _approx_liq_distance_pct(leverage: int) -> float:
    # Conservative isolated approximation: ~100/leverage percent before fees/MM.
    if leverage <= 0:
        return 0.0
    return 100.0 / float(leverage)


class ConfidenceLeveragePolicy:
    def select(
        self,
        *,
        tier: LiquidityTier,
        confidence: float,
        stop_distance_pct: float,
        instrument_max_leverage: float,
        atr_pct: float = 0.0,
        spread_bps: float = 0.0,
        consecutive_losses: int = 0,
        drawdown_pct: float = 0.0,
    ) -> LeverageDecision:
        notes: list[str] = []
        blocks: list[str] = []
        if tier == LiquidityTier.BLOCKED:
            return LeverageDecision(
                0, (0, 0), instrument_max_leverage, tier.value, confidence, 0.0, 0.0,
                False, ["tier_blocked"], notes,
            )
        if confidence < MIN_CONFIDENCE:
            return LeverageDecision(
                0, (0, 0), instrument_max_leverage, tier.value, confidence, 0.0, 0.0,
                False, [f"confidence<{MIN_CONFIDENCE}"], notes,
            )

        rng = TIER_RANGES[tier]
        if confidence < 72:
            target = rng.low
            band = (rng.low, rng.mid)
        elif confidence < 80:
            target = rng.mid
            band = (rng.low, rng.high)
        elif confidence < 88:
            target = rng.high
            band = (rng.mid, rng.high)
        else:
            # Still capped; do not auto-take absolute max without buffers.
            target = rng.high
            band = (rng.mid, min(rng.absolute_max, int(instrument_max_leverage) or rng.absolute_max))
            notes.append("high_confidence_still_capped")

        if consecutive_losses >= 2:
            target = max(rng.low, target - 5)
            notes.append("delever_consecutive_losses")
        if drawdown_pct >= 2.0:
            target = rng.low
            notes.append("delever_drawdown")
        if atr_pct >= 5.0 and tier in (LiquidityTier.TIER_C_MID, LiquidityTier.TIER_D_SMALL_HIGH_RISK):
            target = min(target, rng.low)
            notes.append("vol_cap")
        if spread_bps >= 20:
            target = min(target, rng.low)
            notes.append("spread_cap")

        inst_max = int(instrument_max_leverage) if instrument_max_leverage > 0 else rng.absolute_max
        absolute = min(rng.absolute_max, inst_max)
        selected = min(max(target, 1), absolute)

        # Ensure stop stays safely inside liquidation distance.
        liq_dist = _approx_liq_distance_pct(selected)
        buffer = liq_dist - stop_distance_pct
        while selected > 1 and buffer < MIN_LIQ_BUFFER_PCT:
            selected -= 1
            liq_dist = _approx_liq_distance_pct(selected)
            buffer = liq_dist - stop_distance_pct
            notes.append("reduced_for_liq_buffer")

        if selected < rng.low:
            notes.append(f"below_tier_base:{rng.low}")

        if buffer < MIN_LIQ_BUFFER_PCT:
            blocks.append(f"stop_too_near_liq:buffer={buffer:.3f}")

        # Small-coin hard cap
        if tier == LiquidityTier.TIER_D_SMALL_HIGH_RISK and selected > 20:
            selected = 20
            notes.append("small_coin_cap_20x")

        allow = len(blocks) == 0 and selected >= 1
        return LeverageDecision(
            selected=selected if allow else 0,
            allowed_range=(band[0], min(band[1], absolute)),
            instrument_max=instrument_max_leverage,
            tier=tier.value,
            confidence=confidence,
            liquidation_distance_pct=liq_dist,
            stop_to_liq_buffer_pct=buffer,
            allow=allow,
            block_reasons=blocks,
            notes=notes,
        )


class EquityAwareLeverageSelector(ConfidenceLeveragePolicy):
    """Alias with explicit equity awareness hook (risk budget still decides loss)."""

    def select_for_equity(self, *, equity: float, **kwargs: Any) -> LeverageDecision:
        # Larger equity does not force lower leverage; notes only.
        decision = self.select(**kwargs)
        if equity >= 50_000:
            decision.notes.append("large_equity_stricter_liquidity_share_required")
        return decision
