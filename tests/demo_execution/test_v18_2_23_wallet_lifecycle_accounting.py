# -*- coding: utf-8 -*-
"""V18.2.23 — wallet lifecycle accounting Decimal recon + provenance."""
from backend.nexus_demo_execution.wallet_lifecycle_accounting import (
    build_lifecycle_accounting_record,
    classify_pnl_provenance,
    reconcile_wallet_before_after,
)


def test_reconcile_pass_full_precision():
    out = reconcile_wallet_before_after(
        wallet_before="1000.12345678",
        wallet_after="999.62345678",
        exchange_realized_pnl="-0.5",
        fees="0.5",
        funding="0",
    )
    assert out["WALLET_RECONCILIATION_PASS"] is True
    assert out["status"] == "WALLET_RECONCILIATION_PASS"
    assert out["actual_wallet_delta"] == "-0.5"
    assert out["fabricated_accounting"] is False


def test_reconcile_fee_inclusive_closed_pnl_pass():
    out = reconcile_wallet_before_after(
        wallet_before="5027.85184994",
        wallet_after="5027.78143134",
        exchange_realized_pnl="-0.0704186",
        fees="0.0704186",
        funding="0",
    )
    assert out["WALLET_RECONCILIATION_PASS"] is True
    assert out["expectation_model"] == "realized_only_fee_inclusive"
    assert out["actual_wallet_delta"] == "-0.0704186"


def test_reconcile_mismatch_tiny_delta_not_hidden():
    out = reconcile_wallet_before_after(
        wallet_before="100",
        wallet_after="100.00000003",
        exchange_realized_pnl="0",
        fees="0",
        funding="0",
        tolerance="0.00000001",
    )
    assert out["WALLET_RECONCILIATION_PASS"] is False
    assert "00000003" in out["actual_wallet_delta"] or out["actual_wallet_delta"].endswith("3")


def test_historical_not_reconstructable():
    rec = build_lifecycle_accounting_record(
        lifecycle={
            "symbol": "BTCUSDT",
            "bybit_orderId": "abc",
            "bybit_executionId": "def",
            "position_zero": True,
            "pnl_pct": -0.03,
            "transport_tag": "REAL",
        },
        account_identity={
            "exchange_domain": "api-demo.bybit.com",
            "api_key_fingerprint": "deadbeef",
            "wallet_context": "UNIFIED",
            "settle_coin": "USDT",
        },
        wallet_before=None,
        historical=True,
    )
    assert rec["accounting_status"] == "WALLET_DELTA_NOT_RECONSTRUCTABLE"
    assert rec["ACCOUNTING_COMPLETE"] is False
    assert rec["fabricated_accounting"] is False


def test_pnl_provenance_exchange_authoritative():
    p = classify_pnl_provenance(
        exchange_closed_pnl="-1.25",
        exchange_exec_fee="0.05",
        internal_pnl=-0.03,
        has_exchange_fill=True,
    )
    assert p["pnl_provenance"] in {"EXCHANGE_REALIZED_PNL", "MIXED"}
    assert p["real_loss_supported_by_exchange"] is True
