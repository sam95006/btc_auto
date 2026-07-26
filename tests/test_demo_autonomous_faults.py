"""Fault / edge tests for autonomous Demo modules."""
from __future__ import annotations

import pytest

from backend.nexus_research.demo_autonomous.leverage_policy import ConfidenceLeveragePolicy
from backend.nexus_research.demo_autonomous.position_lifecycle import (
    DemoPositionLifecycleController,
    ExitReason,
    PositionSnapshot,
)
from backend.nexus_research.demo_autonomous.risk_budget import AutonomousDemoRiskBudget
from backend.nexus_research.demo_autonomous.session_authorization import AuthorizationValidator
from backend.nexus_research.demo_autonomous.universe import LiquidityTier
from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport, ALLOWED_WRITE_PATHS
from backend.nexus_research.demo_exchange.errors import WriteForbiddenError
from backend.nexus_research.demo_exchange.signer import DemoRequestSigner


class TestLeverageFaults:
    def test_small_over_20_capped(self):
        d = ConfidenceLeveragePolicy().select(
            tier=LiquidityTier.TIER_D_SMALL_HIGH_RISK,
            confidence=99,
            stop_distance_pct=0.8,
            instrument_max_leverage=100,
        )
        assert d.selected <= 20

    def test_major_50x_shadow_still_buffered(self):
        d = ConfidenceLeveragePolicy().select(
            tier=LiquidityTier.TIER_A_MAJOR,
            confidence=95,
            stop_distance_pct=1.0,
            instrument_max_leverage=100,
        )
        # 50x only if buffer allows; with 1% stop, 50x liq~2% buffer~1% < 2% → reduced
        assert d.selected <= 50
        if d.allow:
            assert d.stop_to_liq_buffer_pct >= 2.0 - 1e-6


class TestRiskBudget:
    def test_daily_loss_pauses(self):
        rb = AutonomousDemoRiskBudget(equity=5000.0, max_daily_loss_pct=1.5)
        rb.record_outcome(-80.0)  # 1.6%
        ok, reason = rb.allow_new_order()
        assert ok is False
        assert reason and "daily" in reason

    def test_three_losses(self):
        rb = AutonomousDemoRiskBudget(equity=5000.0)
        rb.record_outcome(-1)
        rb.record_outcome(-1)
        rb.record_outcome(-1)
        ok, reason = rb.allow_new_order()
        assert ok is False
        assert reason == "max_consecutive_losses"


class TestLifecycle:
    def test_hard_stop_long(self):
        import time

        ctrl = DemoPositionLifecycleController()
        now = int(time.time() * 1000)
        pos = PositionSnapshot(
            symbol="BTCUSDT",
            side="Buy",
            size=0.01,
            entry_price=100_000,
            mark_price=98_000,
            unrealised_pnl=-20,
            liquidation_price=96_000,
            stop_loss=99_000,
            take_profit=103_000,
            opened_at_ms=now - 60_000,
            protection_verified=True,
        )
        d = ctrl.evaluate(pos, stop_distance_pct=1.5, now_ms=now)
        assert d.should_exit and d.reason == ExitReason.HARD_STOP

    def test_emergency_stop(self):
        import time

        ctrl = DemoPositionLifecycleController()
        now = int(time.time() * 1000)
        pos = PositionSnapshot(
            "ETHUSDT", "Sell", 0.1, 3000, 3010, -1, 3200, 3100, 2900, now - 1_000, True,
        )
        d = ctrl.evaluate(pos, stop_distance_pct=1.5, emergency_stop=True, now_ms=now)
        assert d.reason == ExitReason.MANUAL_KILL_SWITCH


class TestWriteTransportSafety:
    def test_withdraw_forbidden(self):
        auth = AuthorizationValidator()
        auth.issue(ttl_ms=60_000)
        t = DemoWriteTransport(signer=DemoRequestSigner("k", "s"), auth=auth, dry_run=True)
        with pytest.raises(WriteForbiddenError):
            t.post("/v5/asset/withdraw", {"coin": "USDT"})

    def test_create_in_allowlist(self):
        assert "/v5/order/create" in ALLOWED_WRITE_PATHS

    def test_expired_session_blocks_write(self):
        from backend.nexus_research.demo_autonomous.session_authorization import AuthorizationError

        auth = AuthorizationValidator()
        auth.issue(ttl_ms=1)
        import time
        time.sleep(0.02)
        t = DemoWriteTransport(signer=DemoRequestSigner("k", "s"), auth=auth, dry_run=True)
        with pytest.raises(AuthorizationError):
            t.post("/v5/order/create", {"symbol": "BTCUSDT"})
