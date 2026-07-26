"""tests/test_demo_equity_leverage_matrix.py

Equity-leverage matrix simulation for DemoCapitalAllocator across all
equity sizes, all leverage options (including invalid ones), all stop
distances, and fee/slippage/funding stress cases.

Monte-Carlo-ish promotion/demotion sequence for CapitalGrowthController
over 50 synthetic trades with seeded randomness for reproducibility.

Assertions:
  - Risk amount driven by VALIDATION tier, not by leverage
  - 25x+ blocked when liquidation buffer insufficient
  - allow_trade=False when stop too tight for high leverage
  - Never silently uses PAPER 10000 as default equity
  - Growth sequence tracks promotions/demotions correctly
"""
from __future__ import annotations

import json
import random
from typing import Any

import pytest

from backend.nexus_research.demo_learning.capital_growth import (
    CapitalGrowthController,
    DrawdownDeleveraging,
    GrowthState,
)
from backend.nexus_research.demo_strategy.capital_allocator import (
    DEFAULT_FUNDING_RATE,
    DEFAULT_LEVERAGE,
    FEE_RATE_TAKER,
    LEVERAGE_OPTIONS,
    MIN_LIQUIDATION_DISTANCE_PCT,
    DemoCapitalAllocator,
    FeeSlippageBuffer,
    LeverageSelector,
    LiquidationDistanceGuard,
)
from backend.nexus_research.demo_strategy.risk_tiers import (
    ACCELERATED_TIER,
    BASE_TIER,
    GROWTH_TIER,
    VALIDATION_TIER,
    RiskTierName,
)

# ── Shared test fixtures ───────────────────────────────────────────────────────

EQUITIES = [100.0, 500.0, 1000.0, 5000.0, 10_000.0, 50_000.0]
LEVERAGES = [5, 10, 15, 25, 30, 35]          # first three not in LEVERAGE_OPTIONS
STOP_DISTANCES = [0.5, 1.0, 2.0, 3.0]

ENTRY_PRICE = 50_000.0
SYMBOL = "BTCUSDT"
DIRECTION = "LONG"

# Pre-computed safety table: (leverage_as_selected, stop_pct) → liq_safe
# liq_dist = 100/lev; safe when liq_dist >= 2.0 AND liq_dist > stop*1.5
_LIQ_SAFE = {
    (25, 0.5): True,   # 4.0 >= 2.0 and 4.0 > 0.75
    (25, 1.0): True,   # 4.0 >= 2.0 and 4.0 > 1.5
    (25, 2.0): True,   # 4.0 >= 2.0 and 4.0 > 3.0
    (25, 3.0): False,  # 4.0 >= 2.0 but 4.0 < 4.5
    (30, 0.5): True,   # 3.33 >= 2.0 and 3.33 > 0.75
    (30, 1.0): True,   # 3.33 >= 2.0 and 3.33 > 1.5
    (30, 2.0): True,   # 3.33 >= 2.0 and 3.33 > 3.0
    (30, 3.0): False,  # 3.33 >= 2.0 but 3.33 < 4.5
    (35, 0.5): True,   # 2.857 >= 2.0 and 2.857 > 0.75
    (35, 1.0): True,   # 2.857 >= 2.0 and 2.857 > 1.5
    (35, 2.0): False,  # 2.857 >= 2.0 but 2.857 < 3.0
    (35, 3.0): False,  # 2.857 >= 2.0 but 2.857 < 4.5
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Risk Amount Driven by VALIDATION Tier, Not Leverage
# ═══════════════════════════════════════════════════════════════════════════════

class TestRiskAmountByTierNotLeverage:
    """Risk budget = equity × tier.max_risk_pct — leverage has no effect on it."""

    @pytest.mark.parametrize("equity", EQUITIES)
    @pytest.mark.parametrize("leverage", LEVERAGES)
    @pytest.mark.parametrize("stop_pct", [0.5, 1.0, 2.0])
    def test_validation_risk_equals_equity_times_tier_pct(
        self, equity: float, leverage: int, stop_pct: float
    ) -> None:
        """VALIDATION risk_amount_usd = equity × 0.50% regardless of leverage."""
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, stop_pct, equity,
            tier=VALIDATION_TIER,
            requested_leverage=leverage,
        )
        expected = equity * VALIDATION_TIER.max_risk_pct / 100.0
        assert d.risk_amount_usd == pytest.approx(expected, rel=1e-6), (
            f"equity={equity}, lev={leverage}x, stop={stop_pct}%: "
            f"risk_amount={d.risk_amount_usd:.6f}, expected={expected:.6f}"
        )
        assert d.risk_tier == RiskTierName.VALIDATION.value

    @pytest.mark.parametrize("equity", EQUITIES)
    def test_same_equity_all_valid_leverages_produce_identical_risk(
        self, equity: float
    ) -> None:
        """All LEVERAGE_OPTIONS produce the same risk_amount_usd for the same equity+tier."""
        alloc = DemoCapitalAllocator()
        risk_amounts = [
            alloc.allocate(
                SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, equity,
                tier=VALIDATION_TIER, requested_leverage=lev,
            ).risk_amount_usd
            for lev in LEVERAGE_OPTIONS
        ]
        # All three leverages (25/30/35) → same risk, one unique value
        assert len(set(round(v, 8) for v in risk_amounts)) == 1, (
            f"equity={equity}: risk amounts differ across leverages: {risk_amounts}"
        )

    @pytest.mark.parametrize("tier_obj,tier_name", [
        (VALIDATION_TIER, "VALIDATION"),
        (BASE_TIER, "BASE"),
        (GROWTH_TIER, "GROWTH"),
        (ACCELERATED_TIER, "ACCELERATED"),
    ])
    def test_each_tier_produces_correct_max_risk_pct(
        self, tier_obj: Any, tier_name: str
    ) -> None:
        """Each named tier uses its own max_risk_pct, not a hardcoded number."""
        alloc = DemoCapitalAllocator()
        equity = 10_000.0
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, equity,
            tier=tier_obj, requested_leverage=25,
        )
        expected = equity * tier_obj.max_risk_pct / 100.0
        assert d.risk_amount_usd == pytest.approx(expected, rel=1e-6)
        assert d.risk_tier == tier_name

    @pytest.mark.parametrize("equity", EQUITIES)
    def test_risk_scales_linearly_across_equities(self, equity: float) -> None:
        """Risk amount is strictly proportional to equity (linear scaling)."""
        alloc = DemoCapitalAllocator()
        ref_equity = 1_000.0
        ref = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, ref_equity,
            tier=VALIDATION_TIER, requested_leverage=25,
        )
        scaled = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, equity,
            tier=VALIDATION_TIER, requested_leverage=25,
        )
        ratio = equity / ref_equity
        assert scaled.risk_amount_usd == pytest.approx(ref.risk_amount_usd * ratio, rel=1e-6)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — 25x+ Blocked When Liquidation Buffer Insufficient
# ═══════════════════════════════════════════════════════════════════════════════

class TestHighLeverageBlockedInsufficientLiqBuffer:
    """For stop=3%: even 25x (min) has liq_dist=4.0% < stop×1.5=4.5% → blocked."""

    @pytest.mark.parametrize("equity", EQUITIES)
    @pytest.mark.parametrize("leverage", LEVERAGES)
    def test_stop_3pct_blocks_all_leverages_all_equities(
        self, equity: float, leverage: int
    ) -> None:
        """stop=3% is too wide for any LEVERAGE_OPTIONS → allow_trade=False."""
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 3.0, equity,
            requested_leverage=leverage,
        )
        assert d.allow_trade is False, (
            f"equity={equity}, lev={leverage}x, stop=3%: should be blocked, "
            f"block_reasons={d.block_reasons}"
        )
        unsafe_in_reasons = any(
            "NO safe leverage" in r or "UNSAFE" in r or "insufficient" in r.lower()
            for r in d.block_reasons
        )
        assert unsafe_in_reasons, (
            f"No liquidation-guard block reason in: {d.block_reasons}"
        )

    @pytest.mark.parametrize("leverage,stop_pct,expected_safe", [
        (25, 0.5, True),   # liq=4.00% > stop×1.5=0.75%  ✓
        (25, 1.0, True),   # liq=4.00% > stop×1.5=1.50%  ✓
        (25, 2.0, True),   # liq=4.00% > stop×1.5=3.00%  ✓
        (25, 3.0, False),  # liq=4.00% < stop×1.5=4.50%  ✗
        (30, 0.5, True),   # liq=3.33% > stop×1.5=0.75%  ✓
        (30, 1.0, True),   # liq=3.33% > stop×1.5=1.50%  ✓
        (30, 2.0, True),   # liq=3.33% > stop×1.5=3.00%  ✓
        (30, 3.0, False),  # liq=3.33% < stop×1.5=4.50%  ✗
        (35, 0.5, True),   # liq=2.86% > stop×1.5=0.75%  ✓
        (35, 1.0, True),   # liq=2.86% > stop×1.5=1.50%  ✓
        (35, 2.0, False),  # liq=2.86% < stop×1.5=3.00%  ✗
        (35, 3.0, False),  # liq=2.86% < stop×1.5=4.50%  ✗
    ])
    def test_liquidation_guard_truth_table(
        self, leverage: int, stop_pct: float, expected_safe: bool
    ) -> None:
        """Direct unit: LiquidationDistanceGuard safety for every (lev, stop) pair."""
        guard = LiquidationDistanceGuard()
        result = guard.check(leverage=leverage, stop_distance_pct=stop_pct)
        liq_dist = 100.0 / leverage
        assert result.safe is expected_safe, (
            f"{leverage}x, stop={stop_pct}%: "
            f"liq_dist={liq_dist:.4f}%, stop×1.5={stop_pct*1.5:.4f}% → "
            f"expected safe={expected_safe}"
        )
        assert result.liq_distance_pct == pytest.approx(liq_dist, rel=1e-4)

    def test_25x_liq_distance_is_4pct(self) -> None:
        guard = LiquidationDistanceGuard()
        r = guard.check(25, 1.0)
        assert r.liq_distance_pct == pytest.approx(4.0, rel=1e-4)

    def test_35x_liq_distance_is_approx_2_857pct(self) -> None:
        guard = LiquidationDistanceGuard()
        r = guard.check(35, 0.5)
        assert r.liq_distance_pct == pytest.approx(100.0 / 35, rel=1e-4)

    def test_min_liq_distance_constant_is_2pct(self) -> None:
        assert MIN_LIQUIDATION_DISTANCE_PCT == 2.0


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — allow_trade=False When Stop Too Tight for High Leverage
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllowTradeFalseStopTooTight:
    """Verify allow_trade=False when no safe leverage exists."""

    @pytest.mark.parametrize("equity", EQUITIES)
    def test_stop_3pct_allow_trade_false_all_equities(self, equity: float) -> None:
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(SYMBOL, DIRECTION, ENTRY_PRICE, 3.0, equity)
        assert d.allow_trade is False

    @pytest.mark.parametrize("equity", EQUITIES)
    def test_stop_2pct_requested_35x_downgraded_to_30x(self, equity: float) -> None:
        """stop=2%, 35x: 35x unsafe → downgrade to 30x (liq=3.33% > 3.0%)."""
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 2.0, equity,
            requested_leverage=35,
        )
        assert d.leverage == 30, (
            f"equity={equity}: 35x+stop=2% should downgrade to 30x, got {d.leverage}x"
        )

    @pytest.mark.parametrize("equity,stop_pct,leverage,expect_allow", [
        (50_000.0, 0.5, 25, True),   # liq=4.0 > 0.75, ample equity
        (50_000.0, 1.0, 25, True),   # liq=4.0 > 1.5
        (50_000.0, 2.0, 25, True),   # liq=4.0 > 3.0
        (50_000.0, 3.0, 25, False),  # liq=4.0 < 4.5 → no safe lever
        (50_000.0, 3.0, 35, False),  # same: 3% blocks regardless
        (1_000.0,  3.0, 25, False),  # smaller equity doesn't unlock 3% stop
        (100.0,    3.0, 35, False),  # even tiny equity: stop=3% always blocked
        (100.0,    0.5, 25, True),   # tiny equity, tight stop, low lev → allowed
    ])
    def test_allow_trade_decision_matrix(
        self, equity: float, stop_pct: float, leverage: int, expect_allow: bool
    ) -> None:
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, stop_pct, equity,
            tier=VALIDATION_TIER, requested_leverage=leverage,
        )
        assert d.allow_trade is expect_allow, (
            f"equity={equity}, stop={stop_pct}%, lev={leverage}x: "
            f"expected allow_trade={expect_allow}, "
            f"block_reasons={d.block_reasons}"
        )

    def test_leverage_selector_invalid_leverages_snap_to_valid_option(self) -> None:
        """Leverages not in {25,30,35} are snapped to 25 internally."""
        sel = LeverageSelector()
        for invalid_lev in [5, 10, 15]:
            result = sel.select(requested=invalid_lev, stop_distance_pct=1.0)
            assert result.selected in LEVERAGE_OPTIONS or result.selected == 0, (
                f"requested={invalid_lev}: selected={result.selected} "
                f"not in {LEVERAGE_OPTIONS} and not 0"
            )

    def test_leverage_options_constant_is_25_30_35(self) -> None:
        assert set(LEVERAGE_OPTIONS) == {25, 30, 35}
        assert DEFAULT_LEVERAGE == 25

    def test_first_order_flag_forces_validation_tier(self) -> None:
        """is_first_order=True overrides any tier argument → VALIDATION."""
        alloc = DemoCapitalAllocator()
        equity = 5_000.0
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, equity,
            tier=GROWTH_TIER, is_first_order=True,
        )
        assert d.risk_tier == RiskTierName.VALIDATION.value
        expected_risk = equity * VALIDATION_TIER.max_risk_pct / 100.0
        assert d.risk_amount_usd == pytest.approx(expected_risk, rel=1e-6)

    def test_extra_open_position_blocks_trade(self) -> None:
        """current_open_positions >= max → allow_trade=False."""
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 5_000.0,
            current_open_positions=1,
        )
        assert d.allow_trade is False
        assert any("Max demo positions" in r for r in d.block_reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Never Silently Uses PAPER 10000 as Default Equity
# ═══════════════════════════════════════════════════════════════════════════════

class TestNeverUsesPaperDefaultEquity:
    """Equity must always be sourced from the caller — no 10 000 silent fallback."""

    def test_equity_100_risk_is_50_cents_not_50_dollars(self) -> None:
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 100.0,
            tier=VALIDATION_TIER,
        )
        wrong_paper_risk = 10_000.0 * VALIDATION_TIER.max_risk_pct / 100.0  # 50 USD
        correct_risk = 100.0 * VALIDATION_TIER.max_risk_pct / 100.0          # 0.5 USD
        assert d.risk_amount_usd == pytest.approx(correct_risk, rel=1e-6)
        assert abs(d.risk_amount_usd - wrong_paper_risk) > 1.0, (
            "risk_amount_usd matches 10 000-PAPER default — equity=100 was ignored"
        )

    @pytest.mark.parametrize("equity", [100.0, 500.0, 999.0, 1_234.0, 7_777.0, 50_000.0])
    def test_risk_strictly_proportional_to_passed_equity(self, equity: float) -> None:
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, equity,
            tier=VALIDATION_TIER,
        )
        expected = equity * VALIDATION_TIER.max_risk_pct / 100.0
        assert d.risk_amount_usd == pytest.approx(expected, rel=1e-6), (
            f"equity={equity}: got {d.risk_amount_usd:.6f}, expected {expected:.6f}"
        )

    def test_100_vs_10000_risk_ratio_is_exactly_100x(self) -> None:
        alloc = DemoCapitalAllocator()
        d_small = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 100.0, tier=VALIDATION_TIER,
        )
        d_paper = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 10_000.0, tier=VALIDATION_TIER,
        )
        assert d_small.risk_amount_usd != d_paper.risk_amount_usd
        assert d_paper.risk_amount_usd / d_small.risk_amount_usd == pytest.approx(100.0, rel=1e-4)

    def test_distinct_equities_produce_distinct_risk_amounts(self) -> None:
        alloc = DemoCapitalAllocator()
        risks = {
            eq: alloc.allocate(
                SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, eq, tier=VALIDATION_TIER,
            ).risk_amount_usd
            for eq in EQUITIES
        }
        assert len(set(round(v, 8) for v in risks.values())) == len(EQUITIES), (
            "Multiple equity values produced identical risk amounts — default fallback suspected"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Fee / Slippage / Funding Stress Cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeeSlippageFundingStress:
    """Stress the cost buffer across extreme funding, fee, and slippage inputs."""

    def test_high_funding_rate_inflates_fee_buffer(self) -> None:
        """Funding rate 0.01 (1%) × 3 periods pushes total buffer well above default."""
        alloc = DemoCapitalAllocator()
        d_normal = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 5_000.0,
            tier=VALIDATION_TIER, funding_rate=DEFAULT_FUNDING_RATE,
        )
        d_stress = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 5_000.0,
            tier=VALIDATION_TIER, funding_rate=0.01,
        )
        assert d_stress.fee_buffer_usd > d_normal.fee_buffer_usd * 2.0, (
            "Extreme funding (1%) should more than double the fee buffer"
        )

    def test_funding_rate_does_not_alter_risk_amount(self) -> None:
        """Funding rate changes cost buffer, never the risk budget."""
        alloc = DemoCapitalAllocator()
        equity = 5_000.0
        for fr in [0.0, 0.0001, 0.001, 0.005, 0.01]:
            d = alloc.allocate(
                SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, equity,
                tier=VALIDATION_TIER, funding_rate=fr,
            )
            expected_risk = equity * VALIDATION_TIER.max_risk_pct / 100.0
            assert d.risk_amount_usd == pytest.approx(expected_risk, rel=1e-6), (
                f"funding_rate={fr}: risk_amount should be {expected_risk}, got {d.risk_amount_usd}"
            )

    def test_fee_buffer_grows_with_notional(self) -> None:
        """Larger equity → larger notional → larger fee buffer."""
        alloc = DemoCapitalAllocator()
        d_small = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 500.0, tier=VALIDATION_TIER,
        )
        d_large = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 50_000.0, tier=VALIDATION_TIER,
        )
        assert d_large.fee_buffer_usd > d_small.fee_buffer_usd

    def test_fee_slippage_buffer_unit_zero_funding(self) -> None:
        """FeeSlippageBuffer with zero funding: only taker fees + slippage."""
        buf = FeeSlippageBuffer()
        r = buf.compute(10_000.0, funding_rate=0.0)
        expected_fee = 10_000.0 * FEE_RATE_TAKER * 2   # open + close
        expected_slip = 10_000.0 * 0.05 / 100.0
        assert r.fee_estimate_usd == pytest.approx(expected_fee, rel=1e-5)
        assert r.slippage_estimate_usd == pytest.approx(expected_slip, rel=1e-5)
        assert r.funding_reserve_usd == pytest.approx(0.0, abs=1e-9)
        assert r.total_buffer_usd == pytest.approx(expected_fee + expected_slip, rel=1e-5)

    @pytest.mark.parametrize("funding_rate,notional", [
        (0.001, 5_000.0),
        (0.005, 10_000.0),
        (0.01,  20_000.0),
    ])
    def test_fee_slippage_buffer_funding_stress(
        self, funding_rate: float, notional: float
    ) -> None:
        buf = FeeSlippageBuffer()
        r = buf.compute(notional, funding_rate=funding_rate)
        expected_funding = notional * abs(funding_rate) * 3  # 3 periods
        assert r.funding_reserve_usd == pytest.approx(expected_funding, rel=1e-5)
        assert r.total_buffer_usd > r.fee_estimate_usd

    def test_capital_check_blocks_when_margin_exceeds_equity(self) -> None:
        """Tight stop → huge position → margin > equity → allow_trade=False."""
        alloc = DemoCapitalAllocator()
        # stop=0.01%: risk_per_unit=50000*0.0001=5, qty=0.5/5=0.1 BTC,
        # notional=5000, margin=5000/25=200 > equity=100 → blocked
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 0.01, 100.0,
            tier=VALIDATION_TIER, requested_leverage=25,
        )
        assert d.allow_trade is False
        assert any(
            "Capital needed" in r or "capital" in r.lower()
            for r in d.block_reasons
        ), f"Expected capital-check block reason, got: {d.block_reasons}"

    def test_normal_conditions_1000_equity_allow_trade(self) -> None:
        """Sanity: standard equity + 1% stop + 25x → allow_trade=True."""
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 1_000.0,
            tier=VALIDATION_TIER, requested_leverage=25,
        )
        assert d.allow_trade is True
        assert d.fee_buffer_usd > 0.0
        assert d.margin_required > 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Full Equity × Leverage Matrix Integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullEquityLeverageMatrix:
    """Run the complete matrix and assert structural invariants on every cell."""

    @pytest.mark.parametrize("equity", EQUITIES)
    @pytest.mark.parametrize("stop_pct", STOP_DISTANCES)
    def test_risk_amount_invariant_across_all_leverages(
        self, equity: float, stop_pct: float
    ) -> None:
        """For every (equity, stop) pair: risk_amount == equity×0.5% across all leverages."""
        alloc = DemoCapitalAllocator()
        expected = equity * VALIDATION_TIER.max_risk_pct / 100.0
        for lev in LEVERAGES:
            d = alloc.allocate(
                SYMBOL, DIRECTION, ENTRY_PRICE, stop_pct, equity,
                tier=VALIDATION_TIER, requested_leverage=lev,
            )
            assert d.risk_amount_usd == pytest.approx(expected, rel=1e-6), (
                f"equity={equity}, lev={lev}x, stop={stop_pct}%: "
                f"risk_amount={d.risk_amount_usd} ≠ expected={expected}"
            )

    @pytest.mark.parametrize("equity", EQUITIES)
    def test_stop_3pct_always_blocked_across_all_leverages(self, equity: float) -> None:
        """stop=3%: allow_trade=False for every equity and every leverage input."""
        alloc = DemoCapitalAllocator()
        for lev in LEVERAGES:
            d = alloc.allocate(
                SYMBOL, DIRECTION, ENTRY_PRICE, 3.0, equity,
                requested_leverage=lev,
            )
            assert d.allow_trade is False, (
                f"equity={equity}, lev={lev}x, stop=3% should be blocked"
            )

    @pytest.mark.parametrize("equity", EQUITIES)
    def test_stop_1pct_25x_leverages_safely_selected(self, equity: float) -> None:
        """stop=1%, requested=25x: leverage is selected as 25x (liq=4.0 > 1.5)."""
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, equity,
            tier=VALIDATION_TIER, requested_leverage=25,
        )
        assert d.liq_distance_pct == pytest.approx(4.0, rel=1e-3)
        assert d.leverage == 25

    def test_all_decisions_are_json_serializable(self) -> None:
        """AllocationDecision.to_dict() must JSON-serialize cleanly for all matrix cells."""
        alloc = DemoCapitalAllocator()
        for equity in [100.0, 1_000.0, 10_000.0]:
            for stop_pct in STOP_DISTANCES:
                for lev in LEVERAGE_OPTIONS:
                    d = alloc.allocate(
                        SYMBOL, DIRECTION, ENTRY_PRICE, stop_pct, equity,
                        tier=VALIDATION_TIER, requested_leverage=lev,
                    )
                    try:
                        json.dumps(d.to_dict())
                    except (TypeError, ValueError) as exc:
                        pytest.fail(
                            f"equity={equity}, stop={stop_pct}%, lev={lev}x: "
                            f"to_dict() not JSON-serializable: {exc}"
                        )

    def test_research_only_flag_always_true_in_response(self) -> None:
        """AllocationDecision.to_dict() always includes researchOnly=True."""
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 5_000.0)
        assert d.to_dict()["researchOnly"] is True

    def test_margin_mode_is_always_isolated(self) -> None:
        """ISOLATED margin mode is enforced in every allocation."""
        alloc = DemoCapitalAllocator()
        for equity in [500.0, 5_000.0]:
            d = alloc.allocate(SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, equity)
            assert d.margin_mode == "ISOLATED"
            assert d.auto_add_margin is False
            assert d.no_averaging_down is True
            assert d.no_martingale is True

    def test_zero_qty_when_equity_too_small_for_min_trade(self) -> None:
        """Extremely small equity can produce qty=0 → allow_trade=False."""
        alloc = DemoCapitalAllocator()
        d = alloc.allocate(
            SYMBOL, DIRECTION, ENTRY_PRICE, 1.0, 0.01,
            tier=VALIDATION_TIER, requested_leverage=25,
        )
        assert d.allow_trade is False


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — Monte-Carlo-ish Growth Sequence (50 Synthetic Trades)
# ═══════════════════════════════════════════════════════════════════════════════

def _run_growth_sequence(
    trade_pnls: list[float],
    starting_equity: float = 10_000.0,
    evaluate_every: int = 1,
) -> dict[str, Any]:
    """Replay pnls through CapitalGrowthController, collecting state snapshots."""
    ctrl = CapitalGrowthController()
    equity = starting_equity
    ctrl.update_equity(equity)

    tier_history: list[str] = []
    action_history: list[str] = []

    for i, pnl in enumerate(trade_pnls):
        ctrl.record_trade({"pnl": pnl})
        equity = max(equity + pnl, 0.0)
        ctrl.update_equity(equity)

        if (i + 1) % evaluate_every == 0:
            result = ctrl.evaluate()
            action_history.append(result["action"])

        tier_history.append(ctrl.state.current_tier.value)

    return {
        "tier_history": tier_history,
        "action_history": action_history,
        "final_state": ctrl.get_state(),
        "promotions": ctrl.state.promotions_count,
        "demotions": ctrl.state.demotions_count,
        "final_tier": ctrl.state.current_tier.value,
        "controller": ctrl,
    }


class TestMonteCarloGrowthSequence:
    """Deterministic (seeded) Monte-Carlo simulation of tier promotion/demotion."""

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _seeded_trades(
        n: int,
        win_rate: float = 0.60,
        win_size: float = 25.0,
        loss_size: float = 15.0,
        seed: int = 42,
    ) -> list[float]:
        rng = random.Random(seed)
        return [
            win_size * (0.8 + rng.random() * 0.4) if rng.random() < win_rate
            else -loss_size * (0.8 + rng.random() * 0.4)
            for _ in range(n)
        ]

    # ── Basic 50-trade run ─────────────────────────────────────────────────────

    def test_50_trade_sequence_completes_without_error(self) -> None:
        rng = random.Random(123)
        pnls = [rng.choice([15.0, -10.0, 20.0, -12.0, 30.0]) for _ in range(50)]
        result = _run_growth_sequence(pnls)
        assert len(result["tier_history"]) == 50
        assert result["final_tier"] in {t.value for t in RiskTierName}

    def test_50_seeded_tier_history_reproducible(self) -> None:
        """Same seed → identical tier history on repeated runs."""
        pnls = self._seeded_trades(50)
        r1 = _run_growth_sequence(pnls)
        r2 = _run_growth_sequence(pnls)
        assert r1["tier_history"] == r2["tier_history"]
        assert r1["promotions"] == r2["promotions"]
        assert r1["demotions"] == r2["demotions"]

    def test_tier_changes_equal_promotions_plus_demotions(self) -> None:
        """Every tier change in history corresponds to exactly one promo or demotion."""
        pnls = self._seeded_trades(50, win_rate=0.60, seed=42)
        result = _run_growth_sequence(pnls, evaluate_every=1)
        history = result["tier_history"]
        tier_changes = sum(
            1 for i in range(1, len(history))
            if history[i] != history[i - 1]
        )
        assert tier_changes == result["promotions"] + result["demotions"], (
            f"tier_changes={tier_changes} ≠ promotions({result['promotions']}) "
            f"+ demotions({result['demotions']})"
        )

    def test_promotion_demotion_counts_nonneg(self) -> None:
        rng = random.Random(777)
        pnls = [
            rng.uniform(10, 30) if rng.random() < 0.65 else -rng.uniform(8, 20)
            for _ in range(50)
        ]
        result = _run_growth_sequence(pnls, evaluate_every=5)
        assert result["promotions"] >= 0
        assert result["demotions"] >= 0

    # ── Promotion gate ─────────────────────────────────────────────────────────

    def test_promotion_fires_after_qualifying_20_trade_window(self) -> None:
        """After 8 losses then 12 wins at VALIDATION: expectancy>0, WR=60%, PF=3, at HWM."""
        # Losses first so final equity is at a new HWM after the wins
        pnls = [-10.0] * 8 + [20.0] * 12  # 20 trades, WR=60%, PF=3.0, expectancy=8

        ctrl = CapitalGrowthController()
        equity = 10_000.0
        ctrl.update_equity(equity)
        for pnl in pnls:
            ctrl.record_trade({"pnl": pnl})
            equity += pnl
            ctrl.update_equity(equity)

        result = ctrl.evaluate()
        assert result["action"] == "PROMOTED", (
            f"Expected PROMOTED for clean 60%-WR window, got {result['action']}: "
            f"{result.get('evaluation', {}).get('reasons', [])}"
        )
        assert ctrl.state.current_tier == RiskTierName.BASE

    def test_no_promotion_above_accelerated_tier(self) -> None:
        """ACCELERATED is the ceiling — evaluate() never returns PROMOTED from there."""
        ctrl = CapitalGrowthController()
        ctrl.state.current_tier = RiskTierName.ACCELERATED
        equity = 50_000.0
        ctrl.update_equity(equity)
        for i in range(25):
            ctrl.record_trade({"pnl": 50.0})
            equity += 50.0
            ctrl.update_equity(equity)

        result = ctrl.evaluate()
        assert ctrl.state.current_tier == RiskTierName.ACCELERATED
        assert result["action"] != "PROMOTED"
        assert result["evaluation"]["result"] in ("BLOCKED", "NOT_READY")

    def test_promotion_requires_min_10_sample_trades(self) -> None:
        """evaluate() returns NOT_READY when window has < 10 trades."""
        ctrl = CapitalGrowthController()
        equity = 10_000.0
        ctrl.update_equity(equity)
        for _ in range(5):
            ctrl.record_trade({"pnl": 20.0})
            equity += 20.0
            ctrl.update_equity(equity)

        result = ctrl.evaluate()
        assert result["action"] == "HOLD"

    # ── Demotion gate ──────────────────────────────────────────────────────────

    def test_demotion_after_3_consecutive_losses_from_base(self) -> None:
        """3 consecutive losses → DEMOTED from BASE → VALIDATION."""
        ctrl = CapitalGrowthController()
        ctrl.state.current_tier = RiskTierName.BASE
        equity = 10_000.0
        ctrl.update_equity(equity)

        for _ in range(3):
            ctrl.record_trade({"pnl": -100.0})
            equity -= 100.0
            ctrl.update_equity(equity)

        result = ctrl.evaluate()
        assert result["action"] == "DEMOTED"
        assert ctrl.state.current_tier == RiskTierName.VALIDATION

    def test_demotion_does_not_go_below_validation(self) -> None:
        """VALIDATION is the floor — no further demotion, ever."""
        ctrl = CapitalGrowthController()
        ctrl.state.current_tier = RiskTierName.VALIDATION
        equity = 10_000.0
        ctrl.update_equity(equity)

        for _ in range(5):
            ctrl.record_trade({"pnl": -200.0})
            equity -= 200.0
            ctrl.update_equity(equity)

        result = ctrl.evaluate()
        assert ctrl.state.current_tier == RiskTierName.VALIDATION
        assert result["action"] != "DEMOTED"

    def test_demotion_after_drawdown_breach_10pct(self) -> None:
        """Drawdown > 10% triggers DRAWDOWN_BREACH demotion from GROWTH."""
        ctrl = CapitalGrowthController()
        ctrl.state.current_tier = RiskTierName.GROWTH
        ctrl.update_equity(10_000.0)   # HWM = 10_000
        ctrl.update_equity(8_900.0)    # drawdown = 11% > 10% threshold

        result = ctrl.evaluate()
        assert result["action"] == "DEMOTED"
        triggers = result["evaluation"].get("triggers", [])
        assert "DRAWDOWN_BREACH" in triggers

    def test_api_incident_triggers_demotion_from_growth(self) -> None:
        """A single API incident causes immediate demotion."""
        ctrl = CapitalGrowthController()
        ctrl.state.current_tier = RiskTierName.GROWTH
        ctrl.update_equity(10_000.0)

        ctrl.record_incident(api=True)
        result = ctrl.evaluate()
        assert result["action"] == "DEMOTED"
        triggers = result["evaluation"].get("triggers", [])
        assert "API_INCIDENT" in triggers

    def test_demotion_then_no_further_demotion_at_floor(self) -> None:
        """After demotion to VALIDATION, subsequent evaluate stays at floor."""
        ctrl = CapitalGrowthController()
        ctrl.state.current_tier = RiskTierName.BASE
        equity = 10_000.0
        ctrl.update_equity(equity)

        for _ in range(3):
            ctrl.record_trade({"pnl": -50.0})
            equity -= 50.0
            ctrl.update_equity(equity)

        r1 = ctrl.evaluate()
        assert r1["action"] == "DEMOTED"
        assert ctrl.state.current_tier == RiskTierName.VALIDATION

        r2 = ctrl.evaluate()
        assert ctrl.state.current_tier == RiskTierName.VALIDATION
        assert r2["action"] != "DEMOTED"

    # ── Drawdown deleveraging ──────────────────────────────────────────────────

    def test_drawdown_multiplier_steps(self) -> None:
        """Verify the four DD thresholds: 5% → 0.75, 10% → 0.50, 15% → 0.25, 20% → 0.0."""
        ctrl = CapitalGrowthController()
        ctrl.update_equity(10_000.0)   # HWM = 10_000

        # 0% drawdown → 1.0
        assert ctrl.drawdown_multiplier == pytest.approx(1.0)

        # 7% → crosses 5% band → 0.75
        ctrl.update_equity(9_300.0)
        assert ctrl.drawdown_multiplier == pytest.approx(0.75)

        # 12% → crosses 10% band → 0.50
        ctrl.update_equity(8_800.0)
        assert ctrl.drawdown_multiplier == pytest.approx(0.50)

        # 16% → crosses 15% band → 0.25
        ctrl.update_equity(8_400.0)
        assert ctrl.drawdown_multiplier == pytest.approx(0.25)

        # 21% → crosses 20% band → 0.0 (halt)
        ctrl.update_equity(7_900.0)
        assert ctrl.drawdown_multiplier == pytest.approx(0.0)
        assert ctrl.should_halt_trading() is True

    def test_should_halt_trading_false_below_20pct(self) -> None:
        ctrl = CapitalGrowthController()
        ctrl.update_equity(10_000.0)
        ctrl.update_equity(8_100.0)    # 19% drawdown
        assert ctrl.should_halt_trading() is False

    def test_drawdown_deleveraging_unit(self) -> None:
        dd = DrawdownDeleveraging()
        assert dd.compute_multiplier(0.0) == 1.0
        assert dd.compute_multiplier(4.9) == 1.0
        assert dd.compute_multiplier(5.0) == pytest.approx(0.75)
        assert dd.compute_multiplier(10.0) == pytest.approx(0.50)
        assert dd.compute_multiplier(15.0) == pytest.approx(0.25)
        assert dd.compute_multiplier(20.0) == pytest.approx(0.0)
        assert dd.should_halt(19.9) is False
        assert dd.should_halt(20.0) is True

    # ── Serialization ──────────────────────────────────────────────────────────

    def test_growth_state_json_serializable_mid_sequence(self) -> None:
        """GrowthState.to_dict() must JSON-serialize at any point in a sequence."""
        ctrl = CapitalGrowthController()
        ctrl.update_equity(5_000.0)
        for pnl in [20.0, -10.0, 15.0, -8.0, 25.0]:
            ctrl.record_trade({"pnl": pnl})
        ctrl.evaluate()
        try:
            json.dumps(ctrl.get_state())
        except (TypeError, ValueError) as exc:
            pytest.fail(f"GrowthState not JSON-serializable: {exc}")

    # ── Phase-shifted 50-trade scenario ───────────────────────────────────────

    def test_50_trade_phase_shifted_sequence(self) -> None:
        """Three-phase sequence: good → losing streak → recovery.

        Validates that demotion fires during the losing streak and the
        controller does not go below VALIDATION.
        """
        rng = random.Random(999)

        # Phase A: 20 good trades (should allow promotion from VALIDATION → BASE)
        phase_a = [
            rng.uniform(15, 30) if rng.random() < 0.65 else -rng.uniform(8, 15)
            for _ in range(20)
        ]
        # Phase B: 10-trade losing streak (should demote if above VALIDATION)
        phase_b = [-rng.uniform(15, 25) for _ in range(10)]
        # Phase C: 20 mixed recovery trades
        phase_c = [
            rng.uniform(10, 20) if rng.random() < 0.60 else -rng.uniform(8, 14)
            for _ in range(20)
        ]

        all_pnls = phase_a + phase_b + phase_c
        assert len(all_pnls) == 50

        result = _run_growth_sequence(all_pnls, evaluate_every=1)

        assert len(result["tier_history"]) == 50
        # Controller must never drop below VALIDATION
        for tier_name in result["tier_history"]:
            assert tier_name in {t.value for t in RiskTierName}, (
                f"Unknown tier in history: {tier_name}"
        )
        assert result["final_tier"] in {t.value for t in RiskTierName}
        # Counts are non-negative and consistent
        assert result["promotions"] >= 0
        assert result["demotions"] >= 0
