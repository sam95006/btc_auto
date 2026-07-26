"""Tests for autonomous Demo ops status contract + session renew."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.nexus_research.demo_autonomous.ops_status import (
    OpsState,
    derive_ops_state,
    record_scan_result,
)
from backend.nexus_research.demo_autonomous.session_authorization import (
    AuthorizationError,
    AuthorizationValidator,
)


class TestOpsStateDerive:
    def test_scanning_when_running_flat(self):
        st = derive_ops_state(
            session={"active": True, "expired": False, "emergencyStopped": False},
            controller={"running": True},
            position_count=0,
            open_order_count=0,
            protection_active=False,
            exit_pending=False,
            eligible_candidates=0,
            top_candidate=None,
            recovery_required=False,
            risk_paused=False,
            last_closed_recent=False,
        )
        assert st == OpsState.SCANNING

    def test_protected_when_position_and_sltp(self):
        st = derive_ops_state(
            session={"active": True, "expired": False, "emergencyStopped": False},
            controller={"running": True},
            position_count=1,
            open_order_count=2,
            protection_active=True,
            exit_pending=False,
            eligible_candidates=1,
            top_candidate={"symbol": "BTCUSDT", "allowTrade": True},
            recovery_required=False,
            risk_paused=False,
            last_closed_recent=False,
        )
        assert st == OpsState.PROTECTED

    def test_session_expired_when_flat(self):
        st = derive_ops_state(
            session={"active": False, "expired": True, "emergencyStopped": False},
            controller={"running": True},
            position_count=0,
            open_order_count=0,
            protection_active=False,
            exit_pending=False,
            eligible_candidates=0,
            top_candidate=None,
            recovery_required=False,
            risk_paused=False,
            last_closed_recent=False,
        )
        assert st == OpsState.SESSION_EXPIRED

    def test_emergency_stop(self):
        st = derive_ops_state(
            session={"active": False, "expired": False, "emergencyStopped": True},
            controller={"running": False},
            position_count=0,
            open_order_count=0,
            protection_active=False,
            exit_pending=False,
            eligible_candidates=0,
            top_candidate=None,
            recovery_required=False,
            risk_paused=False,
            last_closed_recent=False,
        )
        assert st == OpsState.EMERGENCY_STOPPED


class TestSessionRenew:
    def test_renew_cannot_raise_risk(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
        v = AuthorizationValidator()
        v.issue(ttl_ms=60_000, max_risk_per_trade_pct=0.5)
        renewed = v.renew(ttl_ms=120_000, max_risk_per_trade_pct=0.9)
        assert renewed.max_risk_per_trade_pct <= 0.5
        assert renewed.environment == "BYBIT_DEMO"
        assert renewed.is_active()

    def test_renew_requires_parent(self):
        v = AuthorizationValidator()
        with pytest.raises(AuthorizationError):
            v.renew()

    def test_persist_and_restore(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
        v1 = AuthorizationValidator()
        issued = v1.issue(ttl_ms=600_000)
        assert v1.persist_to_disk() is True
        v2 = AuthorizationValidator()
        assert v2.restore_from_disk() is True
        assert v2.session is not None
        assert v2.session.authorization_hash == issued.authorization_hash


class TestRecordScan:
    def test_record_scan_updates_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
        # Reset singleton
        import backend.nexus_research.demo_autonomous.ops_status as ops

        ops._STORE = None
        store = record_scan_result(
            {
                "universe": {"totalContracts": 10, "tradable": 4},
                "candidates": [{"symbol": "BTCUSDT"}],
                "top": {"symbol": "BTCUSDT", "side": "Buy", "allowTrade": True},
                "blocker": None,
                "orderSent": False,
            }
        )
        assert store.symbols_scanned == 10
        assert store.eligible_candidates == 1
        assert store.last_scan_at_ms is not None
        assert "SCANNED" in store.lifecycle_completed
