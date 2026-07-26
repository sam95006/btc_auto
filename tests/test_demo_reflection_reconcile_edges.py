"""Additional Track 8 taxonomy + Track 5 reconciliation edge cases."""
from __future__ import annotations

from backend.nexus_research.demo_execution.reconciler import DemoOrderReconciler
from backend.nexus_research.demo_execution.state_machine import DemoOrderState, DemoOrderStateMachine
from backend.nexus_research.demo_learning.reflection import (
    REQUIRED_REFLECTION_TAXONOMY,
    DemoTradeOutcome,
    EntryQuality,
    ErrorType,
    ExecutionQualityReport,
    MarketSnapshot,
    ReflectionClassifier,
    RiskCompliance,
)


class TestRequiredReflectionTaxonomy:
    def test_all_required_codes_exist(self):
        present = {e.value for e in ErrorType}
        missing = REQUIRED_REFLECTION_TAXONOMY - present
        assert missing == set()

    def test_required_count_at_least_19(self):
        assert len(REQUIRED_REFLECTION_TAXONOMY) >= 19


class TestExtendedClassifier:
    def test_fee_drag(self):
        outcome = DemoTradeOutcome(pnl=-2.0, fees_paid=1.5, qty=0.01, entry_price=100.0)
        errors = ReflectionClassifier().classify(outcome)
        assert ErrorType.FEE_DRAG in errors

    def test_slippage_excessive(self):
        eq = EntryQuality(entry_price=100.0, optimal_entry_price=99.5, slippage_bps=25.0, timing_score=0.8)
        report = ExecutionQualityReport(trade_id="t1", entry_quality=eq)
        outcome = DemoTradeOutcome(pnl=-5.0, execution_report=report)
        errors = ReflectionClassifier().classify(outcome)
        assert ErrorType.SLIPPAGE_EXCESSIVE in errors

    def test_leverage_too_high(self):
        rc = RiskCompliance(leverage_compliant=False, within_risk_budget=True)
        report = ExecutionQualityReport(trade_id="t1", risk_compliance=rc)
        outcome = DemoTradeOutcome(pnl=-5.0, execution_report=report)
        errors = ReflectionClassifier().classify(outcome)
        assert ErrorType.LEVERAGE_TOO_HIGH in errors

    def test_ambiguous_timeout_lesson_even_if_flat(self):
        outcome = DemoTradeOutcome(pnl=0.0, lessons=["AMBIGUOUS_TIMEOUT after send"])
        errors = ReflectionClassifier().classify(outcome)
        assert ErrorType.AMBIGUOUS_TIMEOUT in errors

    def test_funding_drag(self):
        market = MarketSnapshot(symbol="BTCUSDT", price=100_000.0, timestamp_ms=1, funding_rate=0.01)
        outcome = DemoTradeOutcome(
            pnl=-1.0,
            qty=1.0,
            entry_price=100.0,
            entry_market=market,
        )
        errors = ReflectionClassifier().classify(outcome)
        assert ErrorType.FUNDING_DRAG in errors


class TestReconciliationEdgeCases:
    def _to_filled(self) -> DemoOrderStateMachine:
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)
        sm.transition(DemoOrderState.ACKNOWLEDGED)
        sm.transition(DemoOrderState.FILLED)
        return sm

    def test_ambiguous_blocks_match(self):
        sm = DemoOrderStateMachine()
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION)
        sm.transition(DemoOrderState.AUTHORIZED)
        sm.transition(DemoOrderState.SEND_STARTED)
        sm.transition(DemoOrderState.AMBIGUOUS, reason="timeout after send")
        result = DemoOrderReconciler().reconcile("oid-1", sm, exchange_state="FILLED")
        assert result.ok is False
        assert result.status == "MISMATCH"

    def test_quantity_mismatch(self):
        sm = self._to_filled()
        result = DemoOrderReconciler().reconcile(
            "oid-2",
            sm,
            exchange_state="FILLED",
            exchange_qty=0.02,
            internal_qty=0.01,
            exchange_symbol="BTCUSDT",
            internal_symbol="BTCUSDT",
        )
        assert result.ok is False
        assert "QUANTITY_MISMATCH" in [r.value for r in result.reasons]

    def test_symbol_mismatch(self):
        sm = self._to_filled()
        result = DemoOrderReconciler().reconcile(
            "oid-3",
            sm,
            exchange_state="FILLED",
            exchange_qty=0.01,
            internal_qty=0.01,
            exchange_symbol="ETHUSDT",
            internal_symbol="BTCUSDT",
        )
        assert result.ok is False
        assert "SYMBOL_MISMATCH" in [r.value for r in result.reasons]

    def test_clean_match(self):
        sm = self._to_filled()
        result = DemoOrderReconciler().reconcile(
            "oid-4",
            sm,
            exchange_state="FILLED",
            exchange_qty=0.01,
            internal_qty=0.01,
            exchange_symbol="BTCUSDT",
            internal_symbol="BTCUSDT",
        )
        assert result.ok is True
        assert result.status == "MATCH"
        assert result.to_dict()["orderSent"] is False
