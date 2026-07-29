"""Demo validation orchestrator — advances gates without exchange writes."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution import FIXED_LEVERAGE, MAX_MARGIN, MIN_MARGIN, SERVICE_NAME
from backend.nexus_demo_execution.account_epoch import AccountEpochTracker
from backend.nexus_demo_execution.account_reader import (
    AccountReaderError,
    BybitDemoAccountReader,
    DemoAccountSnapshot,
)
from backend.nexus_demo_execution.allocation import AllocationResult, MarginAllocator
from backend.nexus_demo_execution.export_tool import DemoExecutionExporter, ExportFilters
from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.kill_switch import KillSwitch, KillSwitchTrigger
from backend.nexus_demo_execution.order_adapter import DemoOrderAdapter
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
    DemoExecutionSafetyGate,
    ROUND_TERMINAL_STAGE,
    SafetyGateStage,
)

INITIAL_DEMO_VALIDATION_LABEL = "INITIAL_DEMO_VALIDATION"
DEFAULT_SYMBOL = "BTCUSDT"


@dataclass
class DryRunIntent:
    intent_id: str
    symbol: str
    side: str
    margin_usdt: float
    leverage: int
    available_balance: float
    account_epoch: str
    dry_run_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "side": self.side,
            "margin_usdt": self.margin_usdt,
            "leverage": self.leverage,
            "available_balance": self.available_balance,
            "account_epoch": self.account_epoch,
            "dry_run_only": self.dry_run_only,
        }


@dataclass
class ValidationCycleResult:
    success: bool
    current_stage: str
    autonomous_mode: str
    exchange_write_call_count: int
    first_demo_smoke_order_ready: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "current_stage": self.current_stage,
            "autonomous_mode": self.autonomous_mode,
            "exchange_write_call_count": self.exchange_write_call_count,
            "first_demo_smoke_order_ready": self.first_demo_smoke_order_ready,
            "evidence": redact_secrets(self.evidence),
            "error": self.error,
        }


@dataclass
class DemoValidationOrchestrator:
    """Runs readonly validation cycle — max stop at FOUNDER_CONFIRMATION_REQUIRED."""

    gate: DemoExecutionSafetyGate
    reader: BybitDemoAccountReader
    persistence: DemoExecutionPersistence
    epoch_tracker: AccountEpochTracker
    reconciler: DemoReconciler = field(default_factory=DemoReconciler)
    allocator: MarginAllocator = field(default_factory=MarginAllocator)
    order_adapter: DemoOrderAdapter | None = None
    kill_switch: KillSwitch | None = None
    export_dir: Path = field(default_factory=lambda: Path("artifacts/demo_validation"))
    _last_snapshot: DemoAccountSnapshot | None = field(default=None, repr=False)
    _last_intent: DryRunIntent | None = field(default=None, repr=False)
    _epoch_label: str = INITIAL_DEMO_VALIDATION_LABEL

    def __post_init__(self) -> None:
        if self.order_adapter is None:
            self.order_adapter = DemoOrderAdapter(gate=self.gate)
        if self.kill_switch is None:
            self.kill_switch = KillSwitch(gate=self.gate)

    def run_readonly_cycle(self) -> ValidationCycleResult:
        """Execute full validation gate chain without exchange writes."""
        self.gate.reset()
        evidence: dict[str, Any] = {
            "service": SERVICE_NAME,
            "started_at": time.time(),
            "epoch_label": self._epoch_label,
        }

        try:
            snap = self._read_and_reconcile(evidence)
            intent = self._build_dry_run_intent(snap, evidence)
            self._validate_order_payload(intent, evidence)
            self._validate_protection_payload(intent, evidence)
            self._verify_restart_recovery(evidence)
            self._verify_persistence(evidence)
            self._verify_export(evidence)
            self._verify_protection_final(evidence)
            self._advance_founder_confirmation(evidence)

            evidence["completed_at"] = time.time()
            evidence["terminal_stage"] = ROUND_TERMINAL_STAGE.value
            self._record_evidence(evidence)

            return ValidationCycleResult(
                success=True,
                current_stage=self.gate.current_stage.value,
                autonomous_mode=self.gate.autonomous_mode.value,
                exchange_write_call_count=self.order_adapter.exchange_write_call_count,
                first_demo_smoke_order_ready=self.gate.first_demo_smoke_order_ready,
                evidence=evidence,
            )
        except _CycleAbort as exc:
            self.kill_switch.check_triggers({"last_error": str(exc)})
            return ValidationCycleResult(
                success=False,
                current_stage=self.gate.current_stage.value,
                autonomous_mode=self.gate.autonomous_mode.value,
                exchange_write_call_count=self.order_adapter.exchange_write_call_count,
                first_demo_smoke_order_ready=self.gate.first_demo_smoke_order_ready,
                evidence=evidence,
                error=str(exc),
            )

    def latest_dry_run_intent(self) -> dict[str, Any] | None:
        if self._last_intent:
            return self._last_intent.to_dict()
        rows = self.persistence.read_all("dry_run_intents")
        return rows[-1] if rows else None

    def _read_and_reconcile(self, evidence: dict[str, Any]) -> DemoAccountSnapshot:
        try:
            snap = self.reader.read_with_constitution()
        except (AccountReaderError, Exception) as exc:
            self.gate.fail(f"account_read_failed:{exc}")
            raise _CycleAbort(str(exc)) from exc

        self._last_snapshot = snap
        epoch = self.epoch_tracker.observe(snap)
        self._epoch_label = INITIAL_DEMO_VALIDATION_LABEL

        recon = self.reconciler.reconcile(
            local_positions=[],
            local_orders=[],
            remote_positions=snap.open_positions,
            remote_orders=snap.open_orders,
        )
        evidence["reconciliation"] = recon.to_dict()
        evidence["account_snapshot"] = _snapshot_evidence(snap)

        if recon.state != ReconciliationState.MATCH:
            self.gate.fail(f"reconciliation_failed:{recon.state.value}")
            raise _CycleAbort(recon.detail)

        self.persistence.append(
            "snapshots",
            evidence["account_snapshot"],
            account_epoch=epoch.epoch_id,
        )
        self.persistence.append(
            "epochs",
            {**epoch.to_dict(), "label": self._epoch_label},
            account_epoch=epoch.epoch_id,
        )

        if not self.gate.advance(SafetyGateStage.ACCOUNT_RECONCILED, detail="reconciled"):
            raise _CycleAbort(self.gate.last_failure)
        return snap

    def _build_dry_run_intent(
        self,
        snap: DemoAccountSnapshot,
        evidence: dict[str, Any],
    ) -> DryRunIntent:
        epoch = self.epoch_tracker.current_epoch
        epoch_id = epoch.epoch_id if epoch else "epoch-unknown"

        requested = min(
            max(MIN_MARGIN, snap.available_balance * 0.25),
            snap.available_balance,
            MAX_MARGIN,
        )
        decision = self.allocator.allocate(snap, requested_margin=requested)
        evidence["allocation"] = decision.to_dict()

        if decision.result != AllocationResult.ALLOCATED:
            self.gate.fail(f"allocation_failed:{decision.result.value}")
            raise _CycleAbort(decision.reason)

        intent = DryRunIntent(
            intent_id=f"dry-{uuid.uuid4().hex[:12]}",
            symbol=DEFAULT_SYMBOL,
            side="Buy",
            margin_usdt=decision.margin_usdt,
            leverage=FIXED_LEVERAGE,
            available_balance=snap.available_balance,
            account_epoch=epoch_id,
        )
        self._last_intent = intent
        self.persistence.append(
            "dry_run_intents",
            intent.to_dict(),
            account_epoch=epoch_id,
        )
        evidence["dry_run_intent"] = intent.to_dict()

        if not self.gate.advance(SafetyGateStage.DRY_RUN_INTENT, detail="intent_built"):
            raise _CycleAbort(self.gate.last_failure)
        return intent

    def _validate_order_payload(self, intent: DryRunIntent, evidence: dict[str, Any]) -> None:
        qty = _margin_to_qty(intent.margin_usdt, leverage=intent.leverage)
        payload = build_demo_order_payload(
            symbol=intent.symbol,
            side=intent.side,
            qty=qty,
            margin_usdt=intent.margin_usdt,
            leverage=intent.leverage,
        )
        validation = validate_demo_order_payload(payload)
        evidence["order_payload"] = validation.to_dict()

        if not validation.valid:
            self.gate.fail(f"order_payload_invalid:{';'.join(validation.errors)}")
            raise _CycleAbort("order_payload_invalid")

        self.persistence.append("intents", validation.to_dict(), account_epoch=intent.account_epoch)
        if not self.gate.advance(
            SafetyGateStage.DEMO_ORDER_PAYLOAD_VALIDATED,
            detail="payload_validated",
        ):
            raise _CycleAbort(self.gate.last_failure)

    def _validate_protection_payload(self, intent: DryRunIntent, evidence: dict[str, Any]) -> None:
        entry_price = 50000.0
        qty = _margin_to_qty(intent.margin_usdt, leverage=intent.leverage)
        protection = build_protection_payload(
            symbol=intent.symbol,
            side=intent.side,
            entry_price=entry_price,
            qty=qty,
            stop_loss=entry_price * 0.98,
            take_profit=entry_price * 1.02,
            leverage=intent.leverage,
        )
        validation = validate_protection_payload(protection)
        evidence["protection_payload"] = validation.to_dict()

        if not validation.verified:
            self.gate.fail(f"protection_not_verified:{';'.join(validation.errors)}")
            raise _CycleAbort("protection_not_verified")

        self.persistence.append(
            "protection_checks",
            validation.to_dict(),
            account_epoch=intent.account_epoch,
        )
        if not self.gate.advance(
            SafetyGateStage.PROTECTION_PAYLOAD_VALIDATED,
            detail="protection_validated",
        ):
            raise _CycleAbort(self.gate.last_failure)

    def _verify_restart_recovery(self, evidence: dict[str, Any]) -> None:
        """In-process restart recovery — reload persisted state."""
        epoch_rows = self.persistence.read_all("epochs")
        intent_rows = self.persistence.read_all("dry_run_intents")
        recovery = {
            "epochs_recovered": len(epoch_rows),
            "intents_recovered": len(intent_rows),
            "checksum": _recovery_checksum(epoch_rows, intent_rows),
        }
        evidence["restart_recovery"] = recovery

        if not epoch_rows or not intent_rows:
            self.gate.fail("restart_recovery_incomplete")
            raise _CycleAbort("restart_recovery_incomplete")

        if not self.gate.advance(
            SafetyGateStage.RESTART_RECOVERY_VERIFIED,
            detail="recovery_verified",
        ):
            raise _CycleAbort(self.gate.last_failure)

    def _verify_persistence(self, evidence: dict[str, Any]) -> None:
        summary = self.persistence.summary()
        evidence["persistence"] = summary
        counts = summary.get("stream_counts") or {}
        required = ("epochs", "snapshots", "dry_run_intents")
        missing = [s for s in required if counts.get(s, 0) < 1]
        if missing:
            self.gate.fail(f"persistence_incomplete:{','.join(missing)}")
            raise _CycleAbort("persistence_incomplete")

        if not self.gate.advance(
            SafetyGateStage.PERSISTENCE_VERIFIED,
            detail="persistence_verified",
        ):
            raise _CycleAbort(self.gate.last_failure)

    def _verify_export(self, evidence: dict[str, Any]) -> None:
        exporter = DemoExecutionExporter(
            persistence=self.persistence,
            output_dir=self.export_dir,
        )
        paths = exporter.export_all()
        evidence["export_paths"] = paths
        required_files = (
            "summary.json",
            "account_epochs.json",
            "account_snapshots.csv",
            "dry_run_intents.jsonl",
            "evidence_manifest.json",
        )
        missing = [name for name in required_files if not (self.export_dir / name).exists()]
        if missing:
            self.gate.fail(f"export_incomplete:{','.join(missing)}")
            raise _CycleAbort("export_incomplete")

        if not self.gate.advance(SafetyGateStage.EXPORT_VERIFIED, detail="export_verified"):
            raise _CycleAbort(self.gate.last_failure)

    def _verify_protection_final(self, evidence: dict[str, Any]) -> None:
        checks = self.persistence.read_all("protection_checks")
        if not checks or not checks[-1].get("verified"):
            self.gate.fail("protection_final_not_verified")
            raise _CycleAbort("protection_final_not_verified")

        evidence["protection_final"] = {"verified": True, "check_count": len(checks)}
        if not self.gate.advance(
            SafetyGateStage.PROTECTION_VERIFIED,
            detail="protection_verified",
        ):
            raise _CycleAbort(self.gate.last_failure)

    def _advance_founder_confirmation(self, evidence: dict[str, Any]) -> None:
        evidence["founder_confirmation"] = {
            "required": True,
            "first_demo_smoke_order_ready": False,
            "can_write_orders": False,
        }
        if not self.gate.advance(
            SafetyGateStage.FOUNDER_CONFIRMATION_REQUIRED,
            detail="awaiting_founder",
        ):
            raise _CycleAbort(self.gate.last_failure)

    def _record_evidence(self, evidence: dict[str, Any]) -> None:
        self.persistence.append("gate_evidence", evidence)
        manifest_path = self.export_dir / "cycle_result.json"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(redact_secrets(evidence), indent=2, sort_keys=True),
            encoding="utf-8",
        )


class _CycleAbort(Exception):
    pass


def _snapshot_evidence(snap: DemoAccountSnapshot) -> dict[str, Any]:
    return {
        "wallet_balance": snap.wallet_balance,
        "equity": snap.equity,
        "available_balance": snap.available_balance,
        "open_positions": len(snap.open_positions),
        "open_orders": len(snap.open_orders),
        "source": snap.source,
    }


def _margin_to_qty(margin_usdt: float, *, leverage: int, price: float = 50000.0) -> float:
    notional = margin_usdt * leverage
    return round(notional / price, 4)


def _recovery_checksum(
    epochs: list[dict[str, Any]],
    intents: list[dict[str, Any]],
) -> str:
    payload = json.dumps({"epochs": epochs, "intents": intents}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
