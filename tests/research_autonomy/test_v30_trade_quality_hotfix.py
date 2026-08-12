"""V30 live trade quality hotfix — completion contract, reflection, re-entry guard."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_research_ai_autonomy.same_setup_reentry_guard import (
    closure_record_from_finalize,
    evaluate_same_setup_reentry,
)
from backend.nexus_research_ai_autonomy.trade_completion_v30 import (
    build_setup_signature,
    build_trade_complete_contract,
    run_production_reflection,
)
from backend.nexus_research_ai_autonomy.v30_production_cycle import run_dry_flat_cycle


def test_trade_complete_contract_fields():
    life = {
        "position_zero": True,
        "closed": True,
        "accounting_status": "ACCOUNTING_COMPLETE",
        "ACCOUNTING_COMPLETE": True,
        "exit_reason": "STOP_LOSS",
        "hold_sec": 120.0,
        "process_class": "GOOD_PROCESS_LOSS",
        "wallet_reconciliation": {"WALLET_RECONCILIATION_PASS": True},
        "exact_pnl_accounting": {"calculated_net_pnl": -1.2},
        "path_excursion": {"mfe_usdt": 0.5, "mae_usdt": -1.5},
        "exit_quality": {"exit_quality_class": "STOP_HIT"},
    }
    c = build_trade_complete_contract(lifecycle=life)
    assert c["closed"] is True
    assert c["position_closed"] is True
    assert c["ACCOUNTING_COMPLETE"] is True
    assert c["net_realized"] == -1.2
    assert c["MFE"] == 0.5
    assert c["MAE"] == -1.5


def test_reflection_on_loss():
    life = {
        "symbol": "VELVETUSDT",
        "side": "LONG",
        "process_class": "GOOD_PROCESS_LOSS",
        "exit_reason": "STOP_LOSS",
        "strategy_family": "TREND",
        "regime_at_entry": "TREND_UP",
        "exact_pnl_accounting": {"calculated_net_pnl": -1.0, "total_fees": 0.76},
        "path_excursion": {"mfe_usdt": 0.0, "mae_usdt": -1.0},
        "exit_quality": {"exit_quality_class": "STOP_HIT"},
        "process_evidence": {},
    }
    refl = run_production_reflection(life)
    assert refl["reflection_required"] is True
    assert refl["reflection_created"] is True
    assert refl.get("qualities", {}).get("direction_quality")


def test_same_setup_reentry_blocks_repeat_loss(tmp_path: Path):
    sig = build_setup_signature(symbol="VELVETUSDT", side="LONG")
    closure = {
        "schema": "v30_trade_closure_v1",
        "setup_signature": sig,
        "symbol": "VELVETUSDT",
        "side": "LONG",
        "ACCOUNTING_COMPLETE": True,
        "reflection_required": True,
        "reflection_created": True,
        "Reflection_created": True,
        "exit_reason": "STOP_LOSS",
        "net_realized": -1.0,
        "entry_price": 0.55,
        "exit_price": 0.548,
        "regime": "TREND_UP",
        "momentum_at_entry": 0.02,
    }
    path = tmp_path / "last_trade_closure.json"
    path.write_text(json.dumps(closure), encoding="utf-8")
    gate = evaluate_same_setup_reentry(
        symbol="VELVETUSDT",
        side="LONG",
        setup_signature=sig,
        closure_path=path,
        current_price=0.5481,
        current_regime="TREND_UP",
        current_momentum=0.02,
    )
    assert gate["pass"] is False
    assert gate["same_setup_signature"] is True


def test_dry_scan_48_symbols():
    out = run_dry_flat_cycle(exchange_write=False)
    assert out.get("ok") is True
    assert out.get("market_scan_complete") is True
    assert int(out.get("candidate_count") or 0) >= 40
