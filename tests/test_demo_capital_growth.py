"""Tests for TRACK 7 — Capital Growth Controller."""
from __future__ import annotations

import pytest

from backend.nexus_research.demo_learning.capital_growth import (
    CapitalGrowthController,
    DemotionGate,
    DemotionTrigger,
    DrawdownDeleveraging,
    EquityHighWaterMark,
    GrowthState,
    PerformanceWindow,
    PromotionGate,
    PromotionGateResult,
)
from backend.nexus_research.demo_strategy.risk_tiers import RiskTierName


class TestPerformanceWindow:
    def _make_window(self, pnls: list[float]) -> PerformanceWindow:
        w = PerformanceWindow()
        for pnl in pnls:
            w.add_trade({"pnl": pnl})
        return w

    def test_empty_window(self):
        w = PerformanceWindow()
        assert w.count == 0
        assert w.win_rate == 0.0
        assert w.expectancy == 0.0

    def test_win_rate_calculation(self):
        w = self._make_window([10, -5, 20, -3, 15])
        assert w.count == 5
        assert w.wins == 3
        assert w.losses == 2
        assert w.win_rate == pytest.approx(0.6)

    def test_profit_factor(self):
        w = self._make_window([10, -5, 20, -3])
        assert w.profit_factor == pytest.approx(30 / 8, abs=0.01)

    def test_expectancy(self):
        w = self._make_window([10, -5, 20, -3, 15])
        assert w.expectancy == pytest.approx(37 / 5)

    def test_max_consecutive_losses(self):
        w = self._make_window([10, -1, -2, -3, 5, -1, -2])
        assert w.max_consecutive_losses == 3

    def test_window_size_trimming(self):
        w = PerformanceWindow(window_size=5)
        for i in range(10):
            w.add_trade({"pnl": i})
        assert w.count == 5

    def test_to_dict_keys(self):
        w = self._make_window([10, -5])
        d = w.to_dict()
        assert "count" in d
        assert "winRate" in d
        assert "profitFactor" in d


class TestEquityHighWaterMark:
    def test_initial_hwm(self):
        hwm = EquityHighWaterMark()
        assert hwm.hwm == 0.0
        assert hwm.drawdown_pct == 0.0

    def test_new_hwm_set(self):
        hwm = EquityHighWaterMark()
        assert hwm.update(1000) is True
        assert hwm.hwm == 1000

    def test_no_new_hwm(self):
        hwm = EquityHighWaterMark(hwm=1000, current_equity=1000)
        assert hwm.update(900) is False
        assert hwm.hwm == 1000

    def test_drawdown_calculation(self):
        hwm = EquityHighWaterMark(hwm=1000, current_equity=900)
        assert hwm.drawdown_pct == pytest.approx(10.0)

    def test_is_at_hwm(self):
        hwm = EquityHighWaterMark(hwm=1000, current_equity=1000)
        assert hwm.is_at_hwm is True
        hwm.update(950)
        assert hwm.is_at_hwm is False


class TestDrawdownDeleveraging:
    def test_no_drawdown(self):
        dd = DrawdownDeleveraging()
        assert dd.compute_multiplier(0.0) == 1.0

    def test_5pct_drawdown(self):
        dd = DrawdownDeleveraging()
        assert dd.compute_multiplier(5.0) == 0.75

    def test_10pct_drawdown(self):
        dd = DrawdownDeleveraging()
        assert dd.compute_multiplier(10.0) == 0.50

    def test_15pct_drawdown(self):
        dd = DrawdownDeleveraging()
        assert dd.compute_multiplier(15.0) == 0.25

    def test_20pct_drawdown_halt(self):
        dd = DrawdownDeleveraging()
        assert dd.compute_multiplier(20.0) == 0.0
        assert dd.should_halt(20.0) is True

    def test_below_threshold(self):
        dd = DrawdownDeleveraging()
        assert dd.compute_multiplier(4.9) == 1.0
        assert dd.should_halt(4.9) is False


class TestPromotionGate:
    def _good_window(self) -> PerformanceWindow:
        w = PerformanceWindow()
        for i in range(12):
            pnl = 10.0 if i % 2 == 0 or i < 8 else -5.0
            w.add_trade({"pnl": pnl})
        return w

    def _good_hwm(self) -> EquityHighWaterMark:
        hwm = EquityHighWaterMark()
        hwm.update(1100)
        return hwm

    def test_promotion_all_criteria_met(self):
        gate = PromotionGate()
        w = PerformanceWindow()
        # 7 wins, 5 losses → 58.3% win rate, PF=2.8, expectancy>0
        for i in range(12):
            w.add_trade({"pnl": 10.0 if i < 7 else -5.0})

        hwm = EquityHighWaterMark()
        hwm.update(1100)

        result = gate.evaluate(RiskTierName.VALIDATION, w, hwm, incidents=0)
        assert result.result == PromotionGateResult.PROMOTED
        assert result.target_tier == RiskTierName.BASE

    def test_promotion_blocked_at_max_tier(self):
        gate = PromotionGate()
        w = PerformanceWindow()
        for _ in range(12):
            w.add_trade({"pnl": 8.0})
        hwm = EquityHighWaterMark()
        hwm.update(1100)

        result = gate.evaluate(RiskTierName.ACCELERATED, w, hwm)
        assert result.result == PromotionGateResult.BLOCKED

    def test_promotion_not_ready_insufficient_sample(self):
        gate = PromotionGate()
        w = PerformanceWindow()
        for _ in range(5):
            w.add_trade({"pnl": 10.0})
        hwm = EquityHighWaterMark()
        hwm.update(1100)

        result = gate.evaluate(RiskTierName.VALIDATION, w, hwm)
        assert result.result == PromotionGateResult.NOT_READY
        assert any("sample" in r.lower() for r in result.reasons)

    def test_promotion_not_ready_negative_expectancy(self):
        gate = PromotionGate()
        w = PerformanceWindow()
        for _ in range(12):
            w.add_trade({"pnl": -2.0})
        hwm = EquityHighWaterMark()
        hwm.update(1100)

        result = gate.evaluate(RiskTierName.VALIDATION, w, hwm)
        assert result.result == PromotionGateResult.NOT_READY

    def test_promotion_not_ready_low_win_rate(self):
        gate = PromotionGate()
        w = PerformanceWindow()
        for i in range(12):
            w.add_trade({"pnl": 50.0 if i < 4 else -5.0})
        hwm = EquityHighWaterMark()
        hwm.update(1100)

        result = gate.evaluate(RiskTierName.VALIDATION, w, hwm)
        assert result.result == PromotionGateResult.NOT_READY

    def test_promotion_not_ready_with_incidents(self):
        gate = PromotionGate()
        w = PerformanceWindow()
        for _ in range(12):
            w.add_trade({"pnl": 8.0})
        hwm = EquityHighWaterMark()
        hwm.update(1100)

        result = gate.evaluate(RiskTierName.VALIDATION, w, hwm, incidents=1)
        assert result.result == PromotionGateResult.NOT_READY

    def test_promotion_not_ready_not_at_hwm(self):
        gate = PromotionGate()
        w = PerformanceWindow()
        for _ in range(12):
            w.add_trade({"pnl": 8.0})
        hwm = EquityHighWaterMark(hwm=1200, current_equity=1100)

        result = gate.evaluate(RiskTierName.VALIDATION, w, hwm)
        assert result.result == PromotionGateResult.NOT_READY


class TestDemotionGate:
    def test_demotion_consecutive_losses(self):
        gate = DemotionGate()
        w = PerformanceWindow()
        for _ in range(5):
            w.add_trade({"pnl": -10.0})
        hwm = EquityHighWaterMark(hwm=1000, current_equity=950)

        result = gate.evaluate(RiskTierName.BASE, w, hwm)
        assert result.demoted is True
        assert DemotionTrigger.CONSECUTIVE_LOSSES in result.triggers
        assert result.target_tier == RiskTierName.VALIDATION

    def test_demotion_negative_expectancy(self):
        gate = DemotionGate()
        w = PerformanceWindow()
        for i in range(6):
            w.add_trade({"pnl": 2.0 if i == 0 else -5.0})
        hwm = EquityHighWaterMark(hwm=1000, current_equity=970)

        result = gate.evaluate(RiskTierName.GROWTH, w, hwm)
        assert result.demoted is True
        assert DemotionTrigger.NEGATIVE_EXPECTANCY in result.triggers

    def test_demotion_drawdown_breach(self):
        gate = DemotionGate()
        w = PerformanceWindow()
        w.add_trade({"pnl": 5.0})
        hwm = EquityHighWaterMark(hwm=1000, current_equity=880)

        result = gate.evaluate(RiskTierName.BASE, w, hwm)
        assert result.demoted is True
        assert DemotionTrigger.DRAWDOWN_BREACH in result.triggers

    def test_demotion_api_incident(self):
        gate = DemotionGate()
        w = PerformanceWindow()
        w.add_trade({"pnl": 5.0})
        hwm = EquityHighWaterMark(hwm=1000, current_equity=1000)

        result = gate.evaluate(RiskTierName.BASE, w, hwm, api_incidents=1)
        assert result.demoted is True
        assert DemotionTrigger.API_INCIDENT in result.triggers

    def test_demotion_duplicate_detection(self):
        gate = DemotionGate()
        w = PerformanceWindow()
        w.add_trade({"pnl": 5.0})
        hwm = EquityHighWaterMark(hwm=1000, current_equity=1000)

        result = gate.evaluate(RiskTierName.BASE, w, hwm, duplicate_detections=1)
        assert result.demoted is True
        assert DemotionTrigger.DUPLICATE_DETECTION in result.triggers

    def test_demotion_recon_mismatch(self):
        gate = DemotionGate()
        w = PerformanceWindow()
        w.add_trade({"pnl": 5.0})
        hwm = EquityHighWaterMark(hwm=1000, current_equity=1000)

        result = gate.evaluate(RiskTierName.BASE, w, hwm, recon_mismatches=1)
        assert result.demoted is True
        assert DemotionTrigger.RECONCILIATION_MISMATCH in result.triggers

    def test_no_demotion_at_minimum_tier(self):
        gate = DemotionGate()
        w = PerformanceWindow()
        for _ in range(5):
            w.add_trade({"pnl": -10.0})
        hwm = EquityHighWaterMark(hwm=1000, current_equity=800)

        result = gate.evaluate(RiskTierName.VALIDATION, w, hwm)
        assert result.demoted is False

    def test_no_demotion_healthy_state(self):
        gate = DemotionGate()
        w = PerformanceWindow()
        for _ in range(5):
            w.add_trade({"pnl": 10.0})
        hwm = EquityHighWaterMark(hwm=1000, current_equity=1000)

        result = gate.evaluate(RiskTierName.BASE, w, hwm)
        assert result.demoted is False


class TestCapitalGrowthController:
    def test_initial_state(self):
        ctrl = CapitalGrowthController()
        assert ctrl.state.current_tier == RiskTierName.VALIDATION
        assert ctrl.drawdown_multiplier == 1.0

    def test_record_trade(self):
        ctrl = CapitalGrowthController()
        ctrl.record_trade({"pnl": 10.0})
        assert ctrl.state.window.count == 1

    def test_update_equity_new_hwm(self):
        ctrl = CapitalGrowthController()
        assert ctrl.update_equity(1000) is True
        assert ctrl.state.hwm.hwm == 1000

    def test_update_equity_no_hwm(self):
        ctrl = CapitalGrowthController()
        ctrl.update_equity(1000)
        assert ctrl.update_equity(900) is False

    def test_record_incident(self):
        ctrl = CapitalGrowthController()
        ctrl.record_incident(api=True)
        assert ctrl.state.api_incidents == 1
        assert ctrl.state.incidents_in_window == 1

    def test_evaluate_hold(self):
        ctrl = CapitalGrowthController()
        ctrl.update_equity(1000)
        result = ctrl.evaluate()
        assert result["action"] == "HOLD"

    def test_evaluate_promotion(self):
        ctrl = CapitalGrowthController()
        ctrl.update_equity(1100)
        # 7 wins, 5 losses → 58.3% win rate within 55-65% band
        for i in range(12):
            ctrl.record_trade({"pnl": 10.0 if i < 7 else -5.0})

        result = ctrl.evaluate()
        assert result["action"] == "PROMOTED"
        assert ctrl.state.current_tier == RiskTierName.BASE

    def test_evaluate_demotion(self):
        state = GrowthState(current_tier=RiskTierName.BASE)
        ctrl = CapitalGrowthController(state=state)
        ctrl.update_equity(1000)
        for _ in range(5):
            ctrl.record_trade({"pnl": -20.0})

        result = ctrl.evaluate()
        assert result["action"] == "DEMOTED"
        assert ctrl.state.current_tier == RiskTierName.VALIDATION

    def test_demotion_faster_than_promotion(self):
        state = GrowthState(current_tier=RiskTierName.BASE)
        ctrl = CapitalGrowthController(state=state)
        ctrl.update_equity(1000)
        ctrl.record_trade({"pnl": -10.0})
        ctrl.record_trade({"pnl": -10.0})
        ctrl.record_trade({"pnl": -10.0})

        result = ctrl.evaluate()
        assert result["action"] == "DEMOTED"

    def test_should_halt_trading(self):
        ctrl = CapitalGrowthController()
        ctrl.update_equity(1000)
        ctrl.update_equity(790)
        assert ctrl.should_halt_trading() is True

    def test_effective_risk_pct_with_drawdown(self):
        ctrl = CapitalGrowthController()
        ctrl.update_equity(1000)
        ctrl.update_equity(940)  # 6% drawdown → 0.75 multiplier
        assert ctrl.drawdown_multiplier == 0.75
        assert ctrl.effective_risk_pct < ctrl.current_tier.max_risk_pct
