"""Bybit Demo Execution Validation — comprehensive test suite (60+ tests)."""
from __future__ import annotations

import json
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
    HARDCODED_5000U,
    AllocationSource,
    BalanceSource,
    CapitalConstitution,
    CapitalConstitutionError,
    CapitalSource,
)
from backend.nexus_demo_execution.demo_domain import (
    ALLOWED_HOST,
    DEMO_REST_BASE_URL,
    DemoDomainPolicy,
    DemoDomainRejectedError,
)
from backend.nexus_demo_execution.export_tool import DemoExecutionExporter, ExportFilters, redact_record
from backend.nexus_demo_execution.http_demo_reader import HttpDemoTransport, redact_secrets
from backend.nexus_demo_execution.kill_switch import FOUNDER_TRIGGER_LIST, KillSwitch, KillSwitchTrigger
from backend.nexus_demo_execution.orchestration import DemoValidationOrchestrator, INITIAL_DEMO_VALIDATION_LABEL
from backend.nexus_demo_execution.order_adapter import DemoOrderAdapter, OrderIntent
from backend.nexus_demo_execution.order_payload import (
    build_demo_order_payload,
    validate_demo_order_payload,
)
from backend.nexus_demo_execution.persistence import DemoExecutionPersistence
from backend.nexus_demo_execution.protection_payload import (
    build_protection_payload,
    validate_protection_payload,
)
from backend.nexus_demo_execution.reconciliation import DemoReconciler, ReconciliationState
from backend.nexus_demo_execution.safety_gate import (
    ROUND_TERMINAL_STAGE,
    STAGE_ORDER,
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


def _orchestrator(tmp_path: Path, snap: DemoAccountSnapshot | None = None) -> DemoValidationOrchestrator:
    reader = FakeDemoAccountReader()
    reader.set_snapshot(snap or _snap())
    gate = DemoExecutionSafetyGate()
    return DemoValidationOrchestrator(
        gate=gate,
        reader=reader,
        persistence=DemoExecutionPersistence(db_path=tmp_path / "test.sqlite3"),
        epoch_tracker=AccountEpochTracker(),
        order_adapter=DemoOrderAdapter(gate=gate),
        kill_switch=KillSwitch(gate=gate),
        export_dir=tmp_path / "export",
    )


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

    def test_demo_labels_include_founder_required(self):
        assert "FOUNDER_CONFIRMATION_REQUIRED" in DEMO_EXECUTION_LABELS

    def test_service_name(self):
        assert "demo" in SERVICE_NAME.lower()


# ── Capital Constitution ──────────────────────────────────────────────────────

class TestCapitalConstitution:
    def test_valid_constitution(self):
        c = CapitalConstitution()
        c.validate()
        assert c.snapshot()["valid"] is True

    def test_capital_source_demo(self):
        assert CapitalConstitution().capital_source == CapitalSource.BYBIT_DEMO_ACCOUNT

    def test_balance_source_private_api(self):
        assert CapitalConstitution().balance_source == BalanceSource.BYBIT_DEMO_PRIVATE_API

    def test_allocation_source_available(self):
        assert CapitalConstitution().allocation_source == AllocationSource.AVAILABLE_BALANCE

    def test_no_internal_fake_balance(self):
        assert CapitalConstitution().internal_fake_balance is False

    def test_reject_virtual_balance_key(self):
        c = CapitalConstitution()
        c.reject_virtual_balance({"virtual_balance": 100})
        assert c.violations

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
        with pytest.raises(AccountReaderError, match="no_snapshot"):
            FakeDemoAccountReader().read_snapshot()

    def test_fake_reader_returns_injected(self):
        reader = FakeDemoAccountReader()
        reader.set_snapshot(_snap(wallet_balance=123.45))
        assert reader.read_snapshot().wallet_balance == 123.45

    def test_never_invents_balance(self):
        with pytest.raises(AccountReaderError):
            FakeDemoAccountReader().read_snapshot()

    def test_read_with_constitution(self):
        reader = FakeDemoAccountReader()
        reader.set_snapshot(_snap(wallet_balance=100.0))
        assert reader.read_with_constitution().available_balance == 180.0

    def test_invalid_source_rejected(self):
        reader = FakeDemoAccountReader()
        reader.set_snapshot(_snap(source="paper_ledger"))
        with pytest.raises(AccountReaderError):
            reader.read_with_constitution()


# ── Demo Domain ───────────────────────────────────────────────────────────────

class TestDemoDomain:
    def test_demo_base_url_allowed(self):
        assert DemoDomainPolicy().base_url == DEMO_REST_BASE_URL

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


# ── Allocation ────────────────────────────────────────────────────────────────

class TestAllocation:
    def test_allocate_success(self):
        d = MarginAllocator().allocate(_snap(available_balance=100.0), requested_margin=50.0)
        assert d.result == AllocationResult.ALLOCATED
        assert d.leverage == FIXED_LEVERAGE

    def test_skip_insufficient_safe_margin(self):
        d = MarginAllocator().allocate(_snap(available_balance=10.0), requested_margin=50.0)
        assert d.result == AllocationResult.SKIP_INSUFFICIENT_SAFE_MARGIN

    def test_insufficient_demo_balance(self):
        d = MarginAllocator().allocate(_snap(available_balance=25.0), requested_margin=100.0)
        assert d.result == AllocationResult.INSUFFICIENT_DEMO_BALANCE

    def test_max_open_reached(self):
        d = MarginAllocator().allocate(_snap(open_positions=[{}, {}]), requested_margin=30.0)
        assert d.result == AllocationResult.MAX_OPEN_REACHED


# ── Safety Gate ───────────────────────────────────────────────────────────────

class TestSafetyGate:
    def test_initial_read_only(self):
        assert DemoExecutionSafetyGate().current_stage == SafetyGateStage.READ_ONLY

    def test_stage_order_length(self):
        assert len(STAGE_ORDER) == 10

    def test_terminal_stage(self):
        assert ROUND_TERMINAL_STAGE == SafetyGateStage.FOUNDER_CONFIRMATION_REQUIRED

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
        assert DemoExecutionSafetyGate().first_demo_smoke_order_ready is False

    def test_can_write_false_without_window(self):
        gate = DemoExecutionSafetyGate()
        for stage in STAGE_ORDER[1:]:
            gate.advance(stage)
        assert gate.can_write_orders() is False
        assert gate.first_demo_smoke_order_ready is True

    def test_post_founder_stage_forbidden_via_advance(self):
        gate = DemoExecutionSafetyGate()
        for stage in STAGE_ORDER[1:]:
            gate.advance(stage)
        assert gate.advance(SafetyGateStage.DEMO_ORDER_SMOKE_EXECUTED) is False
        assert gate.complete_smoke_execution(detail="test") is True
        assert gate.current_stage == SafetyGateStage.DEMO_ORDER_SMOKE_EXECUTED
        assert gate.can_write_orders() is False
        assert gate.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED

    def test_full_gate_to_founder(self):
        gate = DemoExecutionSafetyGate()
        for stage in STAGE_ORDER[1:]:
            assert gate.advance(stage) is True
        assert gate.first_demo_smoke_order_ready is True
        assert gate.can_write_orders() is False
        assert gate.current_stage == ROUND_TERMINAL_STAGE
        assert gate.round_complete is True


# ── Order Payload ─────────────────────────────────────────────────────────────

class TestOrderPayload:
    def test_valid_payload(self):
        payload = build_demo_order_payload(
            symbol="BTCUSDT", side="Buy", qty=0.01, margin_usdt=25.0,
        )
        result = validate_demo_order_payload(payload)
        assert result.valid is True

    def test_isolated_required(self):
        payload = build_demo_order_payload(
            symbol="BTCUSDT", side="Buy", qty=0.01, margin_usdt=25.0,
        )
        payload["tradeMode"] = "Cross"
        assert validate_demo_order_payload(payload).valid is False

    def test_leverage_must_be_25(self):
        payload = build_demo_order_payload(
            symbol="BTCUSDT", side="Buy", qty=0.01, margin_usdt=25.0, leverage=10,
        )
        assert validate_demo_order_payload(payload).valid is False

    def test_missing_field_invalid(self):
        payload = build_demo_order_payload(
            symbol="BTCUSDT", side="Buy", qty=0.01, margin_usdt=25.0,
        )
        del payload["symbol"]
        assert validate_demo_order_payload(payload).valid is False

    def test_domain_rejected(self):
        payload = build_demo_order_payload(
            symbol="BTCUSDT", side="Buy", qty=0.01, margin_usdt=25.0,
        )
        payload["domain"] = "https://api.bybit.com"
        result = validate_demo_order_payload(payload)
        assert result.valid is False


# ── Protection Payload ────────────────────────────────────────────────────────

class TestProtectionPayload:
    def test_valid_protection(self):
        payload = build_protection_payload(
            symbol="BTCUSDT", side="Buy", entry_price=50000, qty=0.01,
            stop_loss=49000, take_profit=51000,
        )
        assert validate_protection_payload(payload).verified is True

    def test_unknown_field_not_verified(self):
        payload = build_protection_payload(
            symbol="BTCUSDT", side="Buy", entry_price=50000, qty=0.01,
            stop_loss=49000, take_profit=51000,
        )
        payload["unknown_field"] = "bad"
        result = validate_protection_payload(payload)
        assert result.verified is False
        assert "unknown_field" in result.unknown_fields

    def test_missing_sl_not_verified(self):
        payload = build_protection_payload(
            symbol="BTCUSDT", side="Buy", entry_price=50000, qty=0.01,
            stop_loss=49000, take_profit=51000,
        )
        del payload["stopLoss"]
        assert validate_protection_payload(payload).verified is False


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

    def test_write_stays_disabled_at_founder_gate(self):
        gate = DemoExecutionSafetyGate()
        for stage in STAGE_ORDER[1:]:
            gate.advance(stage)
        adapter = DemoOrderAdapter(gate=gate)
        intent = OrderIntent(symbol="ETHUSDT", side="Sell", qty=0.1, margin_usdt=30, leverage=25)
        result = adapter.submit(intent, dry_run=False)
        assert result.accepted is False
        assert adapter.exchange_write_call_count == 0

    def test_idempotency_replay(self):
        gate = DemoExecutionSafetyGate()
        adapter = DemoOrderAdapter(gate=gate)
        intent = OrderIntent(
            symbol="BTCUSDT", side="Buy", qty=0.01, margin_usdt=25, leverage=25,
            idempotency_key="fixed-key-001",
        )
        adapter.submit(intent)
        r2 = adapter.submit(intent)
        assert r2.reason == "idempotent_replay"


# ── Kill Switch ───────────────────────────────────────────────────────────────

class TestKillSwitch:
    def test_engage_blocks(self):
        gate = DemoExecutionSafetyGate()
        ks = KillSwitch(gate=gate)
        ks.engage("operator_stop")
        assert ks.is_blocked() is True

    def test_founder_trigger_list(self):
        assert KillSwitchTrigger.EXCHANGE_WRITE_ATTEMPTED in FOUNDER_TRIGGER_LIST

    def test_check_exchange_write_trigger(self):
        gate = DemoExecutionSafetyGate()
        ks = KillSwitch(gate=gate)
        assert ks.check_triggers({"exchange_write_call_count": 1}) is True
        assert ks.trigger == KillSwitchTrigger.EXCHANGE_WRITE_ATTEMPTED

    def test_release_requires_founder(self):
        gate = DemoExecutionSafetyGate()
        ks = KillSwitch(gate=gate)
        ks.engage("test")
        assert ks.release(founder_confirmed=False) is False


# ── Orchestration ─────────────────────────────────────────────────────────────

class TestOrchestration:
    def test_full_cycle_reaches_founder(self, tmp_path):
        orch = _orchestrator(tmp_path)
        result = orch.run_readonly_cycle()
        assert result.success is True
        assert result.current_stage == ROUND_TERMINAL_STAGE.value
        assert result.exchange_write_call_count == 0
        assert result.first_demo_smoke_order_ready is True
        assert orch.gate.can_write_orders() is False

    def test_fake_balance_blocked(self, tmp_path):
        reader = FakeDemoAccountReader()
        reader.set_snapshot(_snap(source="paper_ledger"))
        gate = DemoExecutionSafetyGate()
        orch = DemoValidationOrchestrator(
            gate=gate,
            reader=reader,
            persistence=DemoExecutionPersistence(db_path=tmp_path / "bad.sqlite3"),
            epoch_tracker=AccountEpochTracker(),
            export_dir=tmp_path / "export",
        )
        result = orch.run_readonly_cycle()
        assert result.success is False

    def test_insufficient_balance_blocked(self, tmp_path):
        orch = _orchestrator(tmp_path, _snap(available_balance=5.0))
        result = orch.run_readonly_cycle()
        assert result.success is False

    def test_epoch_label_initial(self, tmp_path):
        orch = _orchestrator(tmp_path)
        orch.run_readonly_cycle()
        epochs = orch.persistence.read_all("epochs")
        assert epochs[-1].get("label") == INITIAL_DEMO_VALIDATION_LABEL


# ── Persistence & Export ─────────────────────────────────────────────────────

class TestPersistenceExport:
    def test_append_and_read(self, tmp_path):
        db = DemoExecutionPersistence(db_path=tmp_path / "test.sqlite3")
        cs = db.append("orders", {"order_id": "o1", "symbol": "BTCUSDT"})
        rows = db.read_all("orders")
        assert rows[0]["order_id"] == "o1"
        assert rows[0]["checksum"] == cs

    def test_export_all_artifacts(self, tmp_path):
        db = DemoExecutionPersistence(db_path=tmp_path / "test.sqlite3")
        db.append("epochs", {"epoch_id": "epoch-0001", "label": "INITIAL_DEMO_VALIDATION"})
        db.append("snapshots", {"wallet_balance": 200, "available_balance": 180})
        db.append("dry_run_intents", {"intent_id": "dry-001", "dry_run_only": True})
        out = tmp_path / "export"
        paths = DemoExecutionExporter(persistence=db, output_dir=out).export_all()
        for key in ("summary", "account_epochs", "account_snapshots_csv", "dry_run_intents_jsonl"):
            assert Path(paths[key]).exists()

    def test_export_redaction(self):
        record = {"api_secret": "supersecret12345", "symbol": "BTCUSDT"}
        redacted = redact_record(record)
        assert redacted["api_secret"] == "[REDACTED]"
        assert redacted["symbol"] == "BTCUSDT"

    def test_redact_secrets_helper(self):
        assert redact_secrets({"api_key": "abc123"})["api_key"] == "[REDACTED]"


# ── Http Demo Reader ──────────────────────────────────────────────────────────

class TestHttpDemoReader:
    def test_transport_domain_guard(self):
        transport = HttpDemoTransport()
        assert transport.policy.base_url == DEMO_REST_BASE_URL

    def test_transport_rejects_bad_path(self):
        transport = HttpDemoTransport()
        with pytest.raises(AccountReaderError):
            transport.get("/v5/order/create", {}, {})


# ── Reconciliation ────────────────────────────────────────────────────────────

class TestReconciliation:
    def test_match(self):
        r = DemoReconciler().reconcile(
            local_positions=[], remote_positions=[],
            local_orders=[], remote_orders=[],
        )
        assert r.state == ReconciliationState.MATCH

    def test_mismatch(self):
        r = DemoReconciler().reconcile(
            local_positions=[{}], remote_positions=[],
            local_orders=[], remote_orders=[],
        )
        assert r.state == ReconciliationState.MISMATCH


# ── Account Epoch ─────────────────────────────────────────────────────────────

class TestAccountEpoch:
    def test_first_observation_creates_epoch(self):
        ep = AccountEpochTracker().observe(_snap(wallet_balance=100.0))
        assert ep.epoch_id == "epoch-0001"


# ── Security Scan ─────────────────────────────────────────────────────────────

class TestSecurityScan:
    def test_package_clean(self):
        assert assert_no_mainnet().violation_count == 0

    def test_scan_finds_files(self):
        assert scan_package().scanned_files >= 10


# ── CI Gate Runner ────────────────────────────────────────────────────────────

class TestGateRunner:
    def test_offline_runner(self, tmp_path):
        from tools.ci.demo_validation_gate_runner import run_gate_chain

        report = run_gate_chain(
            output_dir=tmp_path / "artifacts",
            db_path=tmp_path / "runner.sqlite3",
        )
        assert report["success"] is True
        assert report["terminal_stage"] == ROUND_TERMINAL_STAGE.value
        assert report["exchange_write_call_count"] == 0


# ── API Routes ────────────────────────────────────────────────────────────────

class TestApiRoutes:
    def test_register_import(self):
        from backend.nexus_demo_execution.api_routes import get_demo_execution_state

        assert get_demo_execution_state().gate.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED

    def test_status_payload_smoke(self):
        from backend.nexus_demo_execution.api_routes import get_demo_execution_state

        payload = get_demo_execution_state().status_payload()
        assert payload["first_demo_smoke_order_ready"] is False
        assert payload["can_write_orders"] is False
        assert payload["exchange_write_call_count"] == 0

    def test_run_readonly_cycle_endpoint_state(self, tmp_path, monkeypatch):
        from backend.nexus_demo_execution import api_routes as api_mod
        from backend.nexus_demo_execution.account_reader import DemoAccountSnapshot, FakeDemoAccountReader
        from backend.nexus_demo_execution.api_routes import DemoExecutionApiState

        monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path / "writable_data"))
        api_mod._STATE = None
        state = DemoExecutionApiState()
        monkeypatch.setattr(state, "persistence", DemoExecutionPersistence(db_path=tmp_path / "api.sqlite3"))
        reader = FakeDemoAccountReader()
        reader.set_snapshot(
            DemoAccountSnapshot(
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
        )
        result = state.run_readonly_cycle(reader)
        assert result["success"] is True
        assert result["current_stage"] == ROUND_TERMINAL_STAGE.value

    def test_data_root_falls_back_when_unwritable(self, tmp_path, monkeypatch):
        from backend.nexus_demo_execution import api_routes as api_mod

        forbidden = tmp_path / "no_write"
        forbidden.mkdir()
        forbidden.chmod(0o400)
        monkeypatch.setenv("NEXUS_DATA_DIR", str(forbidden / "child"))
        api_mod._STATE = None
        try:
            state = api_mod.DemoExecutionApiState()
            assert state.data_root is not None
            # Must not raise; may mark blocked or fall back to writable path
            payload = state.status_payload()
            assert payload["can_write_orders"] is False
            assert payload["exchange_write_call_count"] == 0
        finally:
            forbidden.chmod(0o700)
