from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from backend.nexus_demo_execution.wallet_lifecycle_accounting import PNL_PROVENANCE
from backend.nexus_research_ai_autonomy.trade_completion_v30 import finalize_closed_trade
from backend.nexus_research_ai_autonomy import v30_production_cycle as prod


class _DummyPathTracker:
    def to_dict(self) -> dict[str, Any]:
        return {
            "mfe_usdt": 0.0,
            "mae_usdt": -0.2,
            "target_touched": False,
            "stop_touched": True,
        }


class _DummyPos:
    symbol = "VELVETUSDT"
    side = "LONG"
    qty = 10.0
    entry_price = 1.0
    path_tracker = _DummyPathTracker()


@dataclass
class _DummyPlan:
    expected_path_range_pct: float = 0.55

    def to_dict(self) -> dict[str, Any]:
        return {"expected_path_range_pct": self.expected_path_range_pct}


@dataclass
class _DummyHoriz:
    def to_dict(self) -> dict[str, Any]:
        return {}


@dataclass
class _DummyEcon:
    def to_dict(self) -> dict[str, Any]:
        return {}


@dataclass
class _DummySizing:
    qty_str: str = "10"

    def to_dict(self) -> dict[str, Any]:
        return {"qty_str": self.qty_str}


class FakeDemoWriteClient:
    def __init__(self, wallet_wallet_balance_sequence: list[float]):
        self._wallet_seq = wallet_wallet_balance_sequence
        self._wallet_i = 0

    def list_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        # Immediately flat
        return []

    def list_executions(self, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return [
            {
                "orderId": "oid-1",
                "execId": "exec-1",
                "execPrice": "1.0",
                "execQty": "10",
                "execFee": "0.0",
                "feeCurrency": "USDT",
                "execTime": int(time.time() * 1000),
                "symbol": "VELVETUSDT",
                "side": "Buy",
                "reduceOnly": "true",
            }
        ]

    def list_closed_pnl(self, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return [
            {
                "orderId": "oid-1",
                "avgEntryPrice": "1.0",
                "avgExitPrice": "0.9",
                "closedPnl": "-0.5",
                "qty": "10",
                "cumEntryValue": "10",
                "cumExitValue": "9",
                "openFee": "1.0",
                "closeFee": "1.0",
                "fundingFee": None,
                "orderPrice": "0.9",
                "orderType": "Market",
                "symbol": "VELVETUSDT",
                "side": "Sell",
                "leverage": "1",
                "updatedTime": int(time.time() * 1000),
                "createdTime": int(time.time() * 1000),
                "execType": "Trade",
                "fillCount": 1,
                "closedSize": "10",
            }
        ]

    def fetch_wallet_snapshot(self, *, coin: str = "USDT", account_type: str = "UNIFIED") -> dict[str, Any]:
        bal = self._wallet_seq[min(self._wallet_i, len(self._wallet_seq) - 1)]
        self._wallet_i += 1
        return {
            "ts_ms": int(time.time() * 1000),
            "exchange_domain": "api-demo.bybit.com",
            "account_type": account_type,
            "wallet_type": "UNIFIED",
            "settle_coin": coin,
            "category": "linear",
            "wallet_balance": str(bal),
            "equity": str(bal),
            "available_balance": str(bal),
            "coin_balance": str(bal),
            "total_wallet_balance": str(bal),
            "total_equity": str(bal),
            "unrealized_pnl": "0",
            "api_key_fingerprint": "fp-test",
            "source_endpoint": "/v5/account/wallet-balance",
        }


def _base_finalize_kwargs(wallet_before: dict[str, Any]) -> dict[str, Any]:
    decision = {
        "decision_id": "d-1",
        "stop_logic": {"price": 0.9},
        "take_profit_logic": {"price": 1.1},
    }
    return dict(
        symbol="VELVETUSDT",
        side="LONG",
        entry_px=1.0,
        exit_px=0.9,
        qty=10.0,
        oid="oid-1",
        entry_ts=int(time.time() * 1000),
        exit_reason="STOP_LOSS",
        hold_sec=10.0,
        opened_mono=time.time(),
        wallet_before=wallet_before,
        decision=decision,
        plan=_DummyPlan(),
        horiz=_DummyHoriz(),
        econ=_DummyEcon(),
        sizing=_DummySizing(),
        order={"qty": "10"},
        pos=_DummyPos(),
        hard_max=3600,
        vol_h=0.35,
        setup_signature="VELVETUSDT|LONG|TREND|TREND_UP|t0.55|s0.40",
    )


def test_wallet_reconciliation_closed_pnl_first_wallet_late(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.nexus_research_ai_autonomy import trade_completion_v30 as tc

    # Speed up the bounded reconciliation loop.
    monkeypatch.setattr(tc.time, "sleep", lambda _s: None)
    monkeypatch.setenv("NEXUS_WALLET_RECONCILIATION_MAX_WAIT_SEC", "8")

    wallet_before = {"wallet_balance": "100.0", "coin_balance": "100.0", "api_key_fingerprint": "fp-test"}
    client = FakeDemoWriteClient(wallet_wallet_balance_sequence=[97.4, 97.5, 97.5, 97.5])

    out = finalize_closed_trade(client=client, **_base_finalize_kwargs(wallet_before))
    assert out["contract"]["ACCOUNTING_COMPLETE"] is True
    assert out["contract"]["wallet_reconciliation"]["WALLET_RECONCILIATION_PASS"] is True


def test_wallet_reconciliation_wallet_never_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.nexus_research_ai_autonomy import trade_completion_v30 as tc

    monkeypatch.setattr(tc.time, "sleep", lambda _s: None)
    monkeypatch.setenv("NEXUS_WALLET_RECONCILIATION_MAX_WAIT_SEC", "8")

    wallet_before = {"wallet_balance": "100.0", "coin_balance": "100.0", "api_key_fingerprint": "fp-test"}
    client = FakeDemoWriteClient(wallet_wallet_balance_sequence=[97.0, 97.0, 97.0, 97.0, 97.0])

    out = finalize_closed_trade(client=client, **_base_finalize_kwargs(wallet_before))
    assert out["contract"]["ACCOUNTING_COMPLETE"] is False


def test_safe_enum_not_redacted_in_stdout(capsys: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.nexus_research_ai_autonomy.autonomy_stdout_v301 import observe_completed_tick
    from backend.nexus_research_ai_autonomy.research_autonomy_scheduler import SchedulerHealth

    health = SchedulerHealth(service_status="WAITING_MARKET")
    last = {"service_status": "WAITING_MARKET", "result": {"reason": "GLOBAL_PENDING_ACCOUNTING"}}
    observe_completed_tick(cycle_n=1, last=last, health=health)
    out = capsys.readouterr().out
    assert "wait_reason=GLOBAL_PENDING_ACCOUNTING" in out


def _write_pending_closure(path: Path, *, accounting_complete: bool, with_lifecycle: bool) -> dict[str, Any]:
    setup_signature = "VELVETUSDT|LONG|TREND|TREND_UP|t0.55|s0.40"
    base: dict[str, Any] = {
        "schema": "v30_trade_closure_v1",
        "closed": True,
        "position_closed": True,
        "setup_signature": setup_signature,
        "symbol": "VELVETUSDT",
        "side": "LONG",
        "entry_price": 1.0,
        "exit_price": 0.9,
        "exit_reason": "STOP_LOSS",
        "hold_sec": 10.0,
        "net_realized": -0.5,
        "ACCOUNTING_COMPLETE": accounting_complete,
        "settlement_state": "PENDING_WALLET_RECONCILIATION" if not accounting_complete else "ACCOUNTING_COMPLETE",
        "reflection_required": False,
        "reflection_created": False,
        "Reflection_created": False,
        "mistake_signature": None,
        "CandidateLesson_created": False,
        "MFE": 0.0,
        "MAE": -0.2,
        "wallet_reconciliation": {"WALLET_RECONCILIATION_PASS": accounting_complete},
        "regime": "TREND_UP",
        "regime_at_entry": "TREND_UP",
        "momentum_at_entry": 0.0,
        "process_class": "GOOD_PROCESS_LOSS",
    }

    if with_lifecycle:
        base["bybit_orderId"] = "oid-1"
        base["wallet_before"] = {
            "wallet_balance": "100.0",
            "coin_balance": "100.0",
            "api_key_fingerprint": "fp-test",
        }
        base["lifecycle"] = {
            **base,
            "bybit_orderId": "oid-1",
            "entry_ts_ms": int(time.time() * 1000),
            "qty": "10",
            "pnl_pct": -5.0,
            "position_zero": True,
            "wallet_before": base["wallet_before"],
            "wallet_after": base["wallet_before"],
            "path_excursion": {"mfe_usdt": 0.0, "mae_usdt": -0.2, "target_touched": False, "stop_touched": True},
            "exit_quality": {"exit_quality_class": "STOP_HIT"},
            "strategy_family": "TREND",
            "regime_at_entry": "TREND_UP",
        }
    return base


def test_global_pending_accounting_blocks_new_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Make closure pending and missing lifecycle keys so retry can't succeed.
    camp_root = tmp_path
    closure_path = camp_root / "autonomy" / "last_trade_closure.json"
    closure_path.parent.mkdir(parents=True, exist_ok=True)
    closure_path.write_text(
        json.dumps(_write_pending_closure(closure_path, accounting_complete=False, with_lifecycle=False)),
        encoding="utf-8",
    )

    monkeypatch.setenv("EXCHANGE_WRITE", "true")
    monkeypatch.setenv("NEXUS_WALLET_RECONCILIATION_MAX_WAIT_SEC", "2")

    monkeypatch.setattr(prod, "load_demo_env", lambda *_args, **_kw: None)
    monkeypatch.setattr(prod, "resolve_demo_env_path", lambda: None)

    # Route campaign_root() to tmp_path.
    from backend.nexus_research_ai_autonomy import cloud_paths_v301

    monkeypatch.setattr(cloud_paths_v301, "campaign_root", lambda *_, **__: camp_root)

    def _stub_run_research_pnl_trade_v30(*_a: Any, **_kw: Any) -> dict[str, Any]:
        raise AssertionError("entry should be blocked by GLOBAL_PENDING_ACCOUNTING")

    import backend.nexus_research_ai_autonomy.research_pnl_trade_v30 as rp

    monkeypatch.setattr(rp, "run_research_pnl_trade_v30", _stub_run_research_pnl_trade_v30)

    market_pack = {
        "selection": {
            "action": "SELECT",
            "selected_symbol": "VELVETUSDT",
            "selected_side": "LONG",
            "preflight": {"entry_price": 1.01, "exchange_feasibility_pass": True, "normalized_qty": "10"},
        }
    }

    out = prod.run_research_demo_loop(account={"wallet_balance": "1000"}, market_pack=market_pack)
    assert out.get("WAIT") is True
    assert out.get("reason") == "GLOBAL_PENDING_ACCOUNTING"


def test_pending_accounting_retry_enables_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    camp_root = tmp_path
    closure_path = camp_root / "autonomy" / "last_trade_closure.json"
    closure_path.parent.mkdir(parents=True, exist_ok=True)

    initial = _write_pending_closure(closure_path, accounting_complete=False, with_lifecycle=True)
    closure_path.write_text(json.dumps(initial), encoding="utf-8")

    monkeypatch.setenv("EXCHANGE_WRITE", "true")
    monkeypatch.setenv("NEXUS_WALLET_RECONCILIATION_MAX_WAIT_SEC", "8")

    # Patch demo env loading and retry client.
    monkeypatch.setattr(prod, "load_demo_env", lambda *_args, **_kw: None)
    monkeypatch.setattr(prod, "resolve_demo_env_path", lambda: None)
    monkeypatch.setattr(prod.time, "sleep", lambda _s: None)

    from backend.nexus_research_ai_autonomy import cloud_paths_v301

    monkeypatch.setattr(cloud_paths_v301, "campaign_root", lambda *_, **__: camp_root)

    # Speed retry loop.
    import backend.nexus_research_ai_autonomy.trade_completion_v30 as tc

    monkeypatch.setattr(tc.time, "sleep", lambda _s: None)

    # DemoWriteClient used inside v30_production_cycle.
    monkeypatch.setattr(prod, "DemoWriteClient", lambda *_a, **_kw: FakeDemoWriteClient(wallet_wallet_balance_sequence=[97.4, 97.5, 97.5, 97.5]))

    # After accounting passes, entry module may run; stub it.
    def _stub_run_research_pnl_trade_v30(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {"executed": False, "WAIT": True, "reason": "ENTRY_STUB"}

    import backend.nexus_research_ai_autonomy.research_pnl_trade_v30 as rp

    monkeypatch.setattr(rp, "run_research_pnl_trade_v30", _stub_run_research_pnl_trade_v30)

    market_pack = {
        "selection": {
            "action": "SELECT",
            "selected_symbol": "VELVETUSDT",
            "selected_side": "LONG",
            "preflight": {"entry_price": 1.01, "exchange_feasibility_pass": True, "normalized_qty": "10"},
        }
    }

    out = prod.run_research_demo_loop(account={"wallet_balance": "1000"}, market_pack=market_pack)
    assert out.get("reason") == "ENTRY_STUB"

    # Closure should be updated to ACCOUNTING_COMPLETE and reflection created.
    updated = json.loads(closure_path.read_text(encoding="utf-8"))
    assert updated.get("ACCOUNTING_COMPLETE") is True
    assert updated.get("Reflection_created") is True or updated.get("reflection_created") is True


