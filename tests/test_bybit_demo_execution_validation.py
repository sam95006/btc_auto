"""Bybit Demo Execution Validation — comprehensive test suite (40+ tests)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from backend.nexus_demo_execution import (
    BYBIT_DEMO,
    DEMO_EXECUTION_LABELS,
    FIXED_LEVERAGE,
    MAINNET,
    MAX_MARGIN,
    MAX_OPEN,
    MAX_PENDING,
    MIN_MARGIN,
    REAL_MONEY,
    SERVICE_NAME,
)
from backend.nexus_demo_execution.account_epoch import AccountEpochTracker
from backend.nexus_demo_execution.account_reader import (
    AccountReaderError,
    DemoAccountSnapshot,
    FakeDemoAccountReader,
)
from backend.nexus_demo_execution.allocation import AllocationResult, MarginAllocator
from backend.nexus_demo_execution.capital_constitution import (
    CapitalConstitution,
    CapitalConstitutionError,
    CapitalSource,
    BalanceSource,
    AllocationSource,
    HARDCODED_5000U,
)
from backend.nexus_demo_execution.demo_domain import (
    ALLOWED_HOST,
    DEMO_REST_BASE_URL,
    DemoDomainPolicy,
    DemoDomainRejectedError,
)
from backend.nexus_demo_execution.export_tool import DemoExecutionExporter, ExportFilters
from backend.nexus_demo_execution.kill_switch import KillSwitch
from backend.nexus_demo_execution.order_adapter import DemoOrderAdapter, OrderIntent
from backend.nexus_demo_execution.persistence import DemoExecutionPersistence
from backend.nexus_demo_execution.reconciliation import DemoReconciler, ReconciliationState
from backend.nexus_demo_execution.safety_gate import (
    AutonomousMode,
    DemoExecutionSafetyGate,
    SafetyGateStage,
)
from backend.nexus_demo_execution.security_scan import assert_no_mainnet, scan_package


def _snap(**kw) -> DemoAccountSnapshot:
    defaults = dict(
        wallet_balance=200.0,
        equity=200.0,
        available_balance=180.0,
        margin_balance=200.0,
        used_margin=20.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        open_positions=[],
        open_orders=[],
    )
    defaults.update(kw)
    return DemoAccountSnapshot(**defaults)


# ── Constants ─────────────────────────────────────────────────────────────────

class TestConstants:
    def test_bybit_demo_true(self):
        assert BYBIT_DEMO is True

    def test_mainnet_false(self):
        assert MAINNET is False

    def test_real_money_false(self):
        assert REAL_MONEY is False

    def test_fixed_leverage_25(self):
        assert FIXED_LEVERAGE == 25

    def test_max_open_2(self):
        assert MAX_OPEN == 2

    def test_max_pending_2(self):
        assert MAX_PENDING == 2

    def test_min_margin_20(self):
        assert MIN_MARGIN == 20

    def test_max_margin_500(self):
        assert MAX_MARGIN == 500

    def test_demo_labels_include_disabled(self):
        assert "DEMO_AUTONOMOUS_DISABLED" in DEMO_EXECUTION_LABELS

    def test_service_name(self):
        assert "demo" in SERVICE_NAME.lower()


# ── Capital Constitution ──────────────────────────────────────────────────────

class TestCapitalConstitution:
    def test_valid_constitution(self):
        c = CapitalConstitution()
        c.validate()
        assert c.snapshot()["valid"] is True

    def test_capital_source_demo(self):
        c = CapitalConstitution()
        assert c.capital_source == CapitalSource.BYBIT_DEMO_ACCOUNT

    def test_balance_source_private_api(self):
        c = CapitalConstitution()
        assert c.balance_source == BalanceSource.BYBIT_DEMO_PRIVATE_API

    def test_allocation_source_available(self):
        c = CapitalConstitution()
        assert c.allocation_source == AllocationSource.AVAILABLE_BALANCE

    def test_no_internal_fake_balance(self):
        c = CapitalConstitution()
        assert c.internal_fake_balance is False

    def test_no_automatic_fund_reset(self):
        c = CapitalConstitution()
        assert c.automatic_fund_reset is False

    def test_founder_manual_reset_only(self):
        c = CapitalConstitution()
        assert c.founder_manual_reset_only is True

    def test_reject_virtual_balance_key(self):
        c = CapitalConstitution()
        with pytest.raises(CapitalConstitutionError):
            c.reject_virtual_balance({"virtual_balance": 100})
            if c.violations:
                raise CapitalConstitutionError("x")

    def test_reject_hardcoded_5000u(self):
        c = CapitalConstitution()
        with pytest.raises(CapitalConstitutionError):
            c.reject_hardcoded_balance(HARDCODED_5000U, source="hardcoded")

    def test_accept_api_balance(self):
        c = CapitalConstitution()
        c.assert_balance_from_api(150.0, api_source=BalanceSource.BYBIT_DEMO_PRIVATE_API.value)


# ── Account Reader ────────────────────────────────────────────────────────────

class TestAccountReader:
    def test_fake_reader_requires_snapshot(self):
        reader = FakeDemoAccountReader()
        with pytest.raises(AccountReaderError, match="no_snapshot"):
            reader.read_snapshot()

    def test_fake_reader_returns_injected(self):
        reader = FakeDemoAccountReader()
        snap = _snap(wallet_balance=123.45)
        reader.set_snapshot(snap)
        assert reader.read_snapshot().wallet_balance == 123.45

    def test_never_invents_balance(self):
        reader = FakeDemoAccountReader()
        with pytest.raises(AccountReaderError):
            reader.read_snapshot()

    def test_read_with_constitution(self):
        reader = FakeDemoAccountReader()
        reader.set_snapshot(_snap(wallet_balance=100.0))
        result = reader.read_with_constitution()
        assert result.available_balance == 180.0

    def test_invalid_source_rejected(self):
        reader = FakeDemoAccountReader()
        reader.set_snapshot(_snap(source="paper_ledger"))
        with pytest.raises(AccountReaderError):
            reader.read_with_constitution()


# ── Demo Domain ───────────────────────────────────────────────────────────────

class TestDemoDomain:
    def test_demo_base_url_allowed(self):
        policy = DemoDomainPolicy()
        assert policy.base_url == DEMO_REST_BASE_URL

    def test_allowed_host(self):
        assert ALLOWED_HOST == "api-demo.bybit.com"

    def test_mainnet_rejected(self):
        with pytest.raises(DemoDomainRejectedError):
            DemoDomainPolicy.validate_base_url("https://api.bybit.com")

    def test_testnet_rejected(self):
        with pytest.raises(DemoDomainRejectedError):
            DemoDomainPolicy.validate_base_url("https://api-testnet.bybit.com")

    def test_arbitrary_domain_rejected(self):
        with pytest.raises(DemoDomainRejectedError):
            DemoDomainPolicy.validate_base_url("https://evil.example.com")

    def test_is_mainnet_url(self):
        policy = DemoDomainPolicy()
        assert policy.is_mainnet_url("https://api.bybit.com/v5/market/time") is True
        assert policy.is_mainnet_url(DEMO_REST_BASE_URL) is False

    def test_summary_flags(self):
        s = DemoDomainPolicy().summary()
        assert s["mainnetRejected"] is True
        assert s["bybitDemoOnly"] is True


# ── Allocation ────────────────────────────────────────────────────────────────

class TestAllocation:
    def test_allocate_success(self):
        alloc = MarginAllocator()
        d = alloc.allocate(_snap(available_balance=100.0), requested_margin=50.0)
        assert d.result == AllocationResult.ALLOCATED
        assert d.margin_usdt == 50.0
        assert d.leverage == FIXED_LEVERAGE

    def test_skip_insufficient_safe_margin(self):
        alloc = MarginAllocator()
        d = alloc.allocate(_snap(available_balance=10.0), requested_margin=50.0)
        assert d.result == AllocationResult.SKIP_INSUFFICIENT_SAFE_MARGIN

    def test_insufficient_demo_balance(self):
        alloc = MarginAllocator()
        d = alloc.allocate(_snap(available_balance=25.0), requested_margin=100.0)
        assert d.result == AllocationResult.INSUFFICIENT_DEMO_BALANCE

    def test_max_open_reached(self):
        alloc = MarginAllocator()
        d = alloc.allocate(
            _snap(open_positions=[{}, {}]),
            requested_margin=30.0,
        )
        assert d.result == AllocationResult.MAX_OPEN_REACHED

    def test_max_pending_reached(self):
        alloc = MarginAllocator()
        d = alloc.allocate(
            _snap(open_orders=[{}, {}]),
            requested_margin=30.0,
        )
        assert d.result == AllocationResult.MAX_PENDING_REACHED

    def test_max_margin_cap(self):
        alloc = MarginAllocator()
        d = alloc.allocate(_snap(available_balance=1000.0), requested_margin=600.0)
        assert d.result == AllocationResult.ALLOCATED
        assert d.margin_usdt == MAX_MARGIN


# ── Safety Gate ───────────────────────────────────────────────────────────────

class TestSafetyGate:
    def test_initial_read_only(self):
        gate = DemoExecutionSafetyGate()
        assert gate.current_stage == SafetyGateStage.READ_ONLY

    def test_initial_disabled(self):
        gate = DemoExecutionSafetyGate()
        assert gate.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED

    def test_advance_stages(self):
        gate = DemoExecutionSafetyGate()
        assert gate.advance(SafetyGateStage.ACCOUNT_RECONCILED)
        assert gate.advance(SafetyGateStage.DRY_RUN_INTENT)
        assert gate.current_stage == SafetyGateStage.DRY_RUN_INTENT

    def test_fail_disables(self):
        gate = DemoExecutionSafetyGate()
        gate.fail("test_failure")
        assert gate.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED

    def test_smoke_not_ready_initially(self):
        gate = DemoExecutionSafetyGate()
        assert gate.first_demo_smoke_order_ready is False

    def test_next_gate_after_read_only(self):
        gate = DemoExecutionSafetyGate()
        assert gate.next_gate == SafetyGateStage.ACCOUNT_RECONCILED.value

    def test_can_write_requires_enabled(self):
        gate = DemoExecutionSafetyGate()
        assert gate.can_write_orders() is False

    def test_full_gate_progression(self):
        gate = DemoExecutionSafetyGate()
        for stage in (
            SafetyGateStage.ACCOUNT_RECONCILED,
            SafetyGateStage.DRY_RUN_INTENT,
            SafetyGateStage.DEMO_ORDER_SMOKE,
            SafetyGateStage.PROTECTION_VERIFIED,
            SafetyGateStage.FOUNDER_CONFIRMATION,
            SafetyGateStage.DEMO_AUTONOMOUS_ENABLED,
        ):
            assert gate.advance(stage) is True
        assert gate.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_ENABLED
        assert gate.can_write_orders() is True


# ── Order Adapter ─────────────────────────────────────────────────────────────

class TestOrderAdapter:
    def test_write_disabled_by_default(self):
        gate = DemoExecutionSafetyGate()
        adapter = DemoOrderAdapter(gate=gate)
        intent = OrderIntent(symbol="BTCUSDT", side="Buy", qty=0.01, margin_usdt=25, leverage=25)
        result = adapter.submit(intent)
        assert result.accepted is False
        assert result.dry_run is True
        assert adapter.exchange_write_call_count == 0

    def test_idempotency_replay(self):
        gate = DemoExecutionSafetyGate()
        adapter = DemoOrderAdapter(gate=gate)
        intent = OrderIntent(
            symbol="BTCUSDT", side="Buy", qty=0.01, margin_usdt=25, leverage=25,
            idempotency_key="fixed-key-001",
        )
        r1 = adapter.submit(intent)
        r2 = adapter.submit(intent)
        assert r2.reason == "idempotent_replay"

    def test_write_after_gate_enabled(self):
        gate = DemoExecutionSafetyGate()
        for stage in (
            SafetyGateStage.ACCOUNT_RECONCILED,
            SafetyGateStage.DRY_RUN_INTENT,
            SafetyGateStage.DEMO_ORDER_SMOKE,
            SafetyGateStage.PROTECTION_VERIFIED,
            SafetyGateStage.FOUNDER_CONFIRMATION,
            SafetyGateStage.DEMO_AUTONOMOUS_ENABLED,
        ):
            gate.advance(stage)
        adapter = DemoOrderAdapter(gate=gate)
        intent = OrderIntent(symbol="ETHUSDT", side="Sell", qty=0.1, margin_usdt=30, leverage=25)
        result = adapter.submit(intent, dry_run=False)
        assert result.accepted is True
        assert adapter.exchange_write_call_count == 1


# ── Kill Switch ───────────────────────────────────────────────────────────────

class TestKillSwitch:
    def test_engage_blocks(self):
        gate = DemoExecutionSafetyGate()
        ks = KillSwitch(gate=gate)
        ks.engage("operator_stop")
        assert ks.is_blocked() is True

    def test_release_requires_founder(self):
        gate = DemoExecutionSafetyGate()
        ks = KillSwitch(gate=gate)
        ks.engage("test")
        assert ks.release(founder_confirmed=False) is False
        assert ks.engaged is True

    def test_release_with_founder(self):
        gate = DemoExecutionSafetyGate()
        ks = KillSwitch(gate=gate)
        ks.engage("test")
        assert ks.release(founder_confirmed=True) is True
        assert ks.engaged is False

    def test_force_disable_gate(self):
        gate = DemoExecutionSafetyGate()
        gate.advance(SafetyGateStage.ACCOUNT_RECONCILED)
        ks = KillSwitch(gate=gate)
        ks.force_disable_gate()
        assert gate.current_stage == SafetyGateStage.READ_ONLY


# ── Reconciliation ────────────────────────────────────────────────────────────

class TestReconciliation:
    def test_match(self):
        r = DemoReconciler().reconcile(
            local_positions=[{}], remote_positions=[{}],
            local_orders=[], remote_orders=[],
        )
        assert r.state == ReconciliationState.MATCH

    def test_mismatch(self):
        r = DemoReconciler().reconcile(
            local_positions=[{}], remote_positions=[],
            local_orders=[], remote_orders=[],
        )
        assert r.state == ReconciliationState.MISMATCH

    def test_ambiguous(self):
        r = DemoReconciler().reconcile(
            local_positions=[], remote_positions=[],
            local_orders=[], remote_orders=[],
            ambiguous=True,
        )
        assert r.state == ReconciliationState.AMBIGUOUS


# ── Account Epoch ─────────────────────────────────────────────────────────────

class TestAccountEpoch:
    def test_first_observation_creates_epoch(self):
        tracker = AccountEpochTracker()
        ep = tracker.observe(_snap(wallet_balance=100.0))
        assert ep.epoch_id == "epoch-0001"

    def test_fund_reset_new_epoch(self):
        tracker = AccountEpochTracker()
        tracker.observe(_snap(wallet_balance=100.0))
        ep2 = tracker.observe(_snap(wallet_balance=500.0), trade_count=5, reflection_count=3)
        assert ep2.epoch_id == "epoch-0002"
        assert tracker.epochs[0].retained_trade_count == 5
        assert tracker.epochs[0].retained_reflection_count == 3

    def test_no_reset_small_change(self):
        tracker = AccountEpochTracker()
        tracker.observe(_snap(wallet_balance=100.0))
        ep2 = tracker.observe(_snap(wallet_balance=110.0))
        assert ep2.epoch_id == "epoch-0001"


# ── Persistence & Export ─────────────────────────────────────────────────────

class TestPersistenceExport:
    def test_append_and_read(self, tmp_path):
        db = DemoExecutionPersistence(db_path=tmp_path / "test.sqlite3")
        cs = db.append("orders", {"order_id": "o1", "symbol": "BTCUSDT"})
        rows = db.read_all("orders")
        assert len(rows) == 1
        assert rows[0]["order_id"] == "o1"
        assert rows[0]["checksum"] == cs

    def test_epoch_filter(self, tmp_path):
        db = DemoExecutionPersistence(db_path=tmp_path / "test.sqlite3")
        db.append("orders", {"order_id": "o1"}, account_epoch="epoch-0001")
        db.append("orders", {"order_id": "o2"}, account_epoch="epoch-0002")
        assert len(db.read_all("orders", account_epoch="epoch-0001")) == 1

    def test_export_artifacts(self, tmp_path):
        db = DemoExecutionPersistence(db_path=tmp_path / "test.sqlite3")
        db.append("orders", {"order_id": "o1", "symbol": "BTCUSDT", "side": "Buy", "qty": 0.01, "margin_usdt": 25})
        db.append("reflections", {"note": "test reflection"})
        out = tmp_path / "export"
        exporter = DemoExecutionExporter(persistence=db, output_dir=out)
        paths = exporter.export_all()
        assert Path(paths["summary"]).exists()
        assert Path(paths["trades_csv"]).exists()
        assert Path(paths["reflections_jsonl"]).exists()
        manifest = json.loads(Path(paths["evidence_manifest"]).read_text(encoding="utf-8"))
        assert len(manifest["artifacts"]) == 3


# ── Security Scan ─────────────────────────────────────────────────────────────

class TestSecurityScan:
    def test_package_clean(self):
        report = assert_no_mainnet()
        assert report.violation_count == 0

    def test_scan_finds_files(self):
        report = scan_package()
        assert report.scanned_files >= 10


# ── API Routes (import smoke) ─────────────────────────────────────────────────

class TestApiRoutes:
    def test_register_import(self):
        from backend.nexus_demo_execution.api_routes import register_demo_execution_routes, get_demo_execution_state

        state = get_demo_execution_state()
        assert state.gate.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED

    def test_status_payload_smoke(self):
        from backend.nexus_demo_execution.api_routes import get_demo_execution_state

        payload = get_demo_execution_state().status_payload()
        assert payload["first_demo_smoke_order_ready"] is False
        assert payload["autonomous_mode"] == "DEMO_AUTONOMOUS_DISABLED"
