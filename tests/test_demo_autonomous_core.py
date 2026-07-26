"""Tests for autonomous demo session, universe, leverage, orchestrator."""
from __future__ import annotations

import pytest

from backend.nexus_research.demo_autonomous.leverage_policy import ConfidenceLeveragePolicy
from backend.nexus_research.demo_autonomous.orchestrator import AutonomousDemoOrchestrator
from backend.nexus_research.demo_autonomous.session_authorization import (
    AuthorizationError,
    AuthorizationValidator,
)
from backend.nexus_research.demo_autonomous.universe import (
    DynamicContractUniverse,
    FIXTURE_INSTRUMENTS,
    LiquidityTier,
    fixture_quality,
)
from backend.nexus_research.demo_autonomous.write_adapter import AutonomousDemoOrderAdapter
from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport
from backend.nexus_research.demo_exchange.signer import DemoRequestSigner


class TestSessionAuthorization:
    def test_issue_and_active(self):
        v = AuthorizationValidator()
        auth = v.issue(ttl_ms=60_000)
        assert auth.is_active()
        assert auth.environment == "BYBIT_DEMO"
        assert auth.to_public_dict()["mainnetAllowed"] is False

    def test_emergency_stop(self):
        v = AuthorizationValidator()
        v.issue(ttl_ms=60_000)
        v.emergency_stop("test")
        with pytest.raises(AuthorizationError):
            v.require_active()

    def test_expiry(self):
        v = AuthorizationValidator()
        auth = v.issue(ttl_ms=1)
        import time
        time.sleep(0.02)
        assert auth.is_expired()


class TestUniverse:
    def test_fixture_tiers(self):
        u = DynamicContractUniverse()
        contracts = u.build(FIXTURE_INSTRUMENTS, fixture_quality())
        by_sym = {c.meta.symbol: c for c in contracts}
        assert by_sym["BTCUSDT"].tier == LiquidityTier.TIER_A_MAJOR
        assert by_sym["SOLUSDT"].tier in (LiquidityTier.TIER_B_LARGE, LiquidityTier.TIER_A_MAJOR)
        assert by_sym["PEPEUSDT"].tier in (
            LiquidityTier.TIER_D_SMALL_HIGH_RISK,
            LiquidityTier.TIER_C_MID,
            LiquidityTier.BLOCKED,
        )
        summary = u.summary(contracts)
        assert summary["totalContracts"] >= 4


class TestLeveragePolicy:
    def test_major_25x_band(self):
        d = ConfidenceLeveragePolicy().select(
            tier=LiquidityTier.TIER_A_MAJOR,
            confidence=70,
            stop_distance_pct=1.5,
            instrument_max_leverage=100,
        )
        assert d.allow
        assert 25 <= d.selected <= 35

    def test_small_coin_cap_20(self):
        d = ConfidenceLeveragePolicy().select(
            tier=LiquidityTier.TIER_D_SMALL_HIGH_RISK,
            confidence=90,
            stop_distance_pct=1.0,
            instrument_max_leverage=50,
        )
        assert d.selected <= 20

    def test_low_confidence_blocks(self):
        d = ConfidenceLeveragePolicy().select(
            tier=LiquidityTier.TIER_A_MAJOR,
            confidence=50,
            stop_distance_pct=1.5,
            instrument_max_leverage=100,
        )
        assert d.allow is False

    def test_stop_near_liq_reduces_or_blocks(self):
        d = ConfidenceLeveragePolicy().select(
            tier=LiquidityTier.TIER_A_MAJOR,
            confidence=80,
            stop_distance_pct=5.0,  # wide stop vs 25x liq ~4%
            instrument_max_leverage=100,
        )
        assert d.selected < 25 or d.allow is False


class TestOrchestratorDryRun:
    def test_scan_no_send(self):
        orch = AutonomousDemoOrchestrator(dry_run=True)
        result = orch.run_cycle(equity=4994.18989642, send=False)
        assert result.order_sent is False
        assert result.universe_summary["totalContracts"] >= 3
        d = result.to_dict()
        assert d["mainnetUsed"] is False
        assert d["orderSent"] is False

    def test_send_without_session_blocked(self):
        orch = AutonomousDemoOrchestrator(dry_run=True)
        result = orch.run_cycle(equity=4994.18989642, send=True)
        assert result.order_sent is False
        assert result.blocker in ("session_inactive", "no_eligible_candidate", "write_adapter_missing")

    def test_send_with_session_dry_run(self):
        auth = AuthorizationValidator()
        auth.issue(ttl_ms=300_000, max_risk_per_trade_pct=0.5)
        signer = DemoRequestSigner("k", "s")
        transport = DemoWriteTransport(signer=signer, auth=auth, dry_run=True)
        adapter = AutonomousDemoOrderAdapter(transport, auth=auth)
        orch = AutonomousDemoOrchestrator(auth=auth, write_adapter=adapter, dry_run=True)
        result = orch.run_cycle(equity=4994.18989642, send=True)
        # May be no eligible under gates — still must not crash; if sent, dry-run only
        if result.order_sent:
            assert result.write_result is not None
            assert result.write_result["place"]["dryRun"] is True
        assert result.to_dict()["realMoneyUsed"] is False

    def test_existing_exposure_blocks(self):
        orch = AutonomousDemoOrchestrator(dry_run=True)
        result = orch.run_cycle(equity=4994.0, open_positions=1, send=True)
        assert result.order_sent is False
        assert result.blocker == "existing_position_or_order"
