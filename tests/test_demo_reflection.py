"""Tests for TRACK 8 — Reflection & Closed-Loop Learning."""
from __future__ import annotations

import pytest

from backend.nexus_research.demo_learning.reflection import (
    DecisionSnapshot,
    DemoTradeOutcome,
    EntryQuality,
    ErrorType,
    ExecutionQualityReport,
    ExitQuality,
    MarketSnapshot,
    OOSValidationRequest,
    PatchPromotionGate,
    PatchProposal,
    PatchStatus,
    ReflectionClassifier,
    ReflectionPipeline,
    ReplayRequest,
    RiskCompliance,
    WalkForwardRequest,
)


class TestErrorTaxonomy:
    def test_all_error_types_have_values(self):
        assert len(ErrorType) >= 19
        assert ErrorType.MARKET_DIRECTION_ERROR.value == "MARKET_DIRECTION_ERROR"
        assert ErrorType.NO_ERROR.value == "NO_ERROR"
        assert ErrorType.UNCLASSIFIED.value == "UNCLASSIFIED"

    def test_error_types_are_strings(self):
        for et in ErrorType:
            assert isinstance(et.value, str)


class TestMarketSnapshot:
    def test_to_dict(self):
        ms = MarketSnapshot(
            symbol="BTCUSDT",
            price=95000.0,
            timestamp_ms=1000000,
            trend_bias="BULLISH",
            regime="TRENDING",
        )
        d = ms.to_dict()
        assert d["symbol"] == "BTCUSDT"
        assert d["trendBias"] == "BULLISH"
        assert d["regime"] == "TRENDING"


class TestDecisionSnapshot:
    def test_to_dict_with_market(self):
        market = MarketSnapshot(symbol="BTCUSDT", price=95000.0, timestamp_ms=1000)
        ds = DecisionSnapshot(
            action="ENTER_LONG",
            market=market,
            confidence=0.75,
            reasoning="Strong trend continuation",
        )
        d = ds.to_dict()
        assert d["action"] == "ENTER_LONG"
        assert d["confidence"] == 0.75
        assert d["market"] is not None


class TestEntryQuality:
    def test_efficiency_perfect(self):
        eq = EntryQuality(entry_price=100.0, optimal_entry_price=100.0)
        assert eq.entry_efficiency == pytest.approx(1.0)

    def test_efficiency_partial(self):
        eq = EntryQuality(entry_price=101.0, optimal_entry_price=100.0)
        assert 0.0 < eq.entry_efficiency < 1.0

    def test_to_dict(self):
        eq = EntryQuality(
            entry_price=100.0,
            optimal_entry_price=99.5,
            slippage_bps=5.0,
            timing_score=0.8,
        )
        d = eq.to_dict()
        assert "entryEfficiency" in d
        assert d["slippageBps"] == 5.0


class TestExitQuality:
    def test_to_dict(self):
        xq = ExitQuality(
            exit_price=105.0,
            optimal_exit_price=107.0,
            exit_reason="TAKE_PROFIT",
            profit_captured_pct=70.0,
        )
        d = xq.to_dict()
        assert d["exitReason"] == "TAKE_PROFIT"
        assert d["profitCapturedPct"] == 70.0


class TestRiskCompliance:
    def test_compliant(self):
        rc = RiskCompliance(
            within_risk_budget=True,
            actual_risk_pct=0.5,
            allowed_risk_pct=0.75,
        )
        assert len(rc.violations) == 0

    def test_non_compliant(self):
        rc = RiskCompliance(
            within_risk_budget=False,
            actual_risk_pct=1.0,
            allowed_risk_pct=0.5,
            violations=["Risk budget exceeded"],
        )
        d = rc.to_dict()
        assert d["withinRiskBudget"] is False
        assert len(d["violations"]) == 1


class TestDemoTradeOutcome:
    def test_basic_outcome(self):
        outcome = DemoTradeOutcome(
            symbol="BTCUSDT",
            direction="LONG",
            entry_price=95000,
            exit_price=96000,
            qty=0.001,
            pnl=1.0,
            pnl_pct=1.05,
        )
        d = outcome.to_dict()
        assert d["symbol"] == "BTCUSDT"
        assert d["pnl"] == 1.0

    def test_outcome_with_errors(self):
        outcome = DemoTradeOutcome(
            symbol="BTCUSDT",
            direction="SHORT",
            pnl=-5.0,
            error_classifications=[ErrorType.MARKET_DIRECTION_ERROR],
        )
        d = outcome.to_dict()
        assert "MARKET_DIRECTION_ERROR" in d["errorClassifications"]


class TestReflectionClassifier:
    def test_winning_trade_no_error(self):
        classifier = ReflectionClassifier()
        outcome = DemoTradeOutcome(pnl=10.0)
        errors = classifier.classify(outcome)
        assert errors == [ErrorType.NO_ERROR]

    def test_market_direction_error_long(self):
        classifier = ReflectionClassifier()
        outcome = DemoTradeOutcome(
            direction="LONG",
            pnl=-5.0,
            entry_market=MarketSnapshot(
                symbol="BTCUSDT", price=95000, timestamp_ms=1000,
                trend_bias="BEARISH",
            ),
            exit_market=MarketSnapshot(
                symbol="BTCUSDT", price=94000, timestamp_ms=2000,
                trend_bias="BEARISH",
            ),
        )
        errors = classifier.classify(outcome)
        assert ErrorType.MARKET_DIRECTION_ERROR in errors

    def test_market_direction_error_short(self):
        classifier = ReflectionClassifier()
        outcome = DemoTradeOutcome(
            direction="SHORT",
            pnl=-5.0,
            entry_market=MarketSnapshot(
                symbol="BTCUSDT", price=95000, timestamp_ms=1000,
                trend_bias="BULLISH",
            ),
            exit_market=MarketSnapshot(
                symbol="BTCUSDT", price=96000, timestamp_ms=2000,
                trend_bias="BULLISH",
            ),
        )
        errors = classifier.classify(outcome)
        assert ErrorType.MARKET_DIRECTION_ERROR in errors

    def test_regime_misclassification(self):
        classifier = ReflectionClassifier()
        outcome = DemoTradeOutcome(
            direction="LONG",
            pnl=-5.0,
            entry_market=MarketSnapshot(
                symbol="BTCUSDT", price=95000, timestamp_ms=1000,
                regime="UNKNOWN",
            ),
            exit_market=MarketSnapshot(
                symbol="BTCUSDT", price=94000, timestamp_ms=2000,
            ),
        )
        errors = classifier.classify(outcome)
        assert ErrorType.REGIME_MISCLASSIFICATION in errors

    def test_stop_too_tight(self):
        classifier = ReflectionClassifier()
        outcome = DemoTradeOutcome(
            direction="LONG",
            pnl=-5.0,
            execution_report=ExecutionQualityReport(
                trade_id="t1",
                entry_quality=EntryQuality(
                    entry_price=100, optimal_entry_price=100, timing_score=0.8,
                ),
                exit_quality=ExitQuality(
                    exit_price=99, optimal_exit_price=105,
                    exit_reason="STOP_HIT", profit_captured_pct=-60,
                ),
            ),
        )
        errors = classifier.classify(outcome)
        assert ErrorType.STOP_TOO_TIGHT in errors

    def test_position_too_large(self):
        classifier = ReflectionClassifier()
        outcome = DemoTradeOutcome(
            direction="LONG",
            pnl=-5.0,
            execution_report=ExecutionQualityReport(
                trade_id="t1",
                risk_compliance=RiskCompliance(
                    within_risk_budget=False,
                    actual_risk_pct=1.5,
                    allowed_risk_pct=0.5,
                ),
            ),
        )
        errors = classifier.classify(outcome)
        assert ErrorType.POSITION_TOO_LARGE in errors

    def test_unclassified_when_no_match(self):
        classifier = ReflectionClassifier()
        outcome = DemoTradeOutcome(direction="LONG", pnl=-5.0)
        errors = classifier.classify(outcome)
        assert ErrorType.UNCLASSIFIED in errors


class TestPatchProposal:
    def test_initial_status_is_candidate(self):
        patch = PatchProposal()
        assert patch.status == PatchStatus.CANDIDATE

    def test_to_dict(self):
        patch = PatchProposal(
            description="Test patch",
            parameter_changes={"stop_buffer_multiplier": 1.2},
            confidence=0.5,
        )
        d = patch.to_dict()
        assert d["status"] == "CANDIDATE"
        assert d["confidence"] == 0.5


class TestPatchPromotionGate:
    def test_promotion_all_conditions_met(self):
        gate = PatchPromotionGate()
        patch = PatchProposal(status=PatchStatus.CANDIDATE)

        result = gate.evaluate(
            patch,
            backtest_improved=True,
            walkforward_confirmed=True,
            oos_no_degradation=True,
        )
        assert result.status == PatchStatus.MANUAL_REVIEW

    def test_promotion_missing_backtest(self):
        gate = PatchPromotionGate()
        patch = PatchProposal(status=PatchStatus.CANDIDATE)

        result = gate.evaluate(
            patch,
            backtest_improved=False,
            walkforward_confirmed=True,
            oos_no_degradation=True,
        )
        assert result.status == PatchStatus.CANDIDATE

    def test_promotion_missing_walkforward(self):
        gate = PatchPromotionGate()
        patch = PatchProposal(status=PatchStatus.CANDIDATE)

        result = gate.evaluate(
            patch,
            backtest_improved=True,
            walkforward_confirmed=False,
            oos_no_degradation=True,
        )
        assert result.status == PatchStatus.CANDIDATE

    def test_promotion_missing_oos(self):
        gate = PatchPromotionGate()
        patch = PatchProposal(status=PatchStatus.CANDIDATE)

        result = gate.evaluate(
            patch,
            backtest_improved=True,
            walkforward_confirmed=True,
            oos_no_degradation=False,
        )
        assert result.status == PatchStatus.CANDIDATE

    def test_promotion_not_from_non_candidate(self):
        gate = PatchPromotionGate()
        patch = PatchProposal(status=PatchStatus.APPROVED)

        result = gate.evaluate(
            patch,
            backtest_improved=True,
            walkforward_confirmed=True,
            oos_no_degradation=True,
        )
        assert result.status == PatchStatus.APPROVED  # unchanged


class TestReflectionPipeline:
    def test_reflect_winning_trade(self):
        pipeline = ReflectionPipeline()
        outcome = DemoTradeOutcome(pnl=10.0, symbol="BTCUSDT", direction="LONG")
        result = pipeline.reflect(outcome)

        assert result["errors"] == ["NO_ERROR"]
        assert result["patch"] is None

    def test_reflect_losing_trade_generates_patch(self):
        pipeline = ReflectionPipeline()
        outcome = DemoTradeOutcome(pnl=-5.0, symbol="BTCUSDT", direction="LONG")
        result = pipeline.reflect(outcome)

        assert "UNCLASSIFIED" in result["errors"]
        assert result["patch"] is not None
        assert result["patch"]["status"] == "CANDIDATE"

    def test_reflect_stores_outcomes(self):
        pipeline = ReflectionPipeline()
        pipeline.reflect(DemoTradeOutcome(pnl=10.0))
        pipeline.reflect(DemoTradeOutcome(pnl=-5.0))
        assert len(pipeline.get_outcomes()) == 2

    def test_promote_patch(self):
        pipeline = ReflectionPipeline()
        outcome = DemoTradeOutcome(pnl=-5.0, symbol="BTCUSDT", direction="LONG")
        result = pipeline.reflect(outcome)

        patch_id = result["patch"]["patchId"]
        promoted = pipeline.promote_patch(
            patch_id,
            backtest_improved=True,
            walkforward_confirmed=True,
            oos_no_degradation=True,
        )
        assert promoted is not None
        assert promoted.status == PatchStatus.MANUAL_REVIEW

    def test_promote_patch_not_found(self):
        pipeline = ReflectionPipeline()
        result = pipeline.promote_patch("nonexistent-id")
        assert result is None

    def test_get_patches_by_status(self):
        pipeline = ReflectionPipeline()
        pipeline.reflect(DemoTradeOutcome(pnl=-5.0, direction="LONG"))
        pipeline.reflect(DemoTradeOutcome(pnl=-3.0, direction="SHORT"))

        candidates = pipeline.get_patches(PatchStatus.CANDIDATE)
        assert len(candidates) == 2

        reviewed = pipeline.get_patches(PatchStatus.MANUAL_REVIEW)
        assert len(reviewed) == 0

    def test_never_auto_applies_to_live(self):
        pipeline = ReflectionPipeline()
        outcome = DemoTradeOutcome(pnl=-5.0, direction="LONG")
        result = pipeline.reflect(outcome)

        patch_id = result["patch"]["patchId"]
        promoted = pipeline.promote_patch(
            patch_id,
            backtest_improved=True,
            walkforward_confirmed=True,
            oos_no_degradation=True,
        )
        assert promoted.status == PatchStatus.MANUAL_REVIEW
        assert promoted.status != PatchStatus.APPLIED


class TestReplayWalkForwardOOS:
    """Verify stubs are properly structured."""

    def test_replay_request_stub(self):
        req = ReplayRequest(trade_id="t1", patch_id="p1")
        d = req.to_dict()
        assert d["status"] == "PENDING"
        assert d["tradeId"] == "t1"

    def test_walkforward_request_stub(self):
        req = WalkForwardRequest(patch_id="p1", window_count=5)
        d = req.to_dict()
        assert d["status"] == "PENDING"
        assert d["windowCount"] == 5

    def test_oos_request_stub(self):
        req = OOSValidationRequest(patch_id="p1", oos_period_days=30)
        d = req.to_dict()
        assert d["status"] == "PENDING"
        assert d["oosPeriodDays"] == 30
