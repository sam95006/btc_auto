"""Read-only API routes for Bybit Demo Execution Validation."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

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
from backend.nexus_demo_execution.account_reader import BybitDemoAccountReader, FakeDemoAccountReader
from backend.nexus_demo_execution.allocation import MarginAllocator
from backend.nexus_demo_execution.capital_constitution import CapitalConstitution
from backend.nexus_demo_execution.demo_domain import DemoDomainPolicy
from backend.nexus_demo_execution.kill_switch import KillSwitch
from backend.nexus_demo_execution.orchestration import DemoValidationOrchestrator
from backend.nexus_demo_execution.order_adapter import DemoOrderAdapter
from backend.nexus_demo_execution.persistence import DemoExecutionPersistence
from backend.nexus_demo_execution.safety_gate import DemoExecutionSafetyGate

logger = logging.getLogger(__name__)


def _data_root() -> Path:
    root = Path(os.environ.get("NEXUS_DATA_DIR") or "data/nexus_demo_validation")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_live_or_fake_reader() -> BybitDemoAccountReader:
    """Prefer live Bybit Demo private GET when credentials are present."""
    key = (os.environ.get("BYBIT_DEMO_API_KEY") or "").strip()
    secret = (os.environ.get("BYBIT_DEMO_API_SECRET") or "").strip()
    if key and secret:
        from backend.nexus_demo_execution.http_demo_reader import HttpDemoAccountReader

        logger.info("demo_account_reader=HttpDemoAccountReader demo_key_present=true")
        return HttpDemoAccountReader(api_key=key, api_secret=secret)
    logger.warning("demo_account_reader=FakeDemoAccountReader credential_missing=true")
    return FakeDemoAccountReader()

READ_ONLY_META = {
    "read_only": True,
    "exchange_write": False,
    "mainnet": MAINNET,
    "real_money": REAL_MONEY,
    "bybit_demo": BYBIT_DEMO,
    "mode": "DEMO_EXECUTION_VALIDATION",
    "service_name": SERVICE_NAME,
    "labels": list(DEMO_EXECUTION_LABELS),
}


class DemoExecutionApiState:
    """Singleton backing store for read-only status endpoints."""

    def __init__(self) -> None:
        self.gate = DemoExecutionSafetyGate()
        self.kill_switch = KillSwitch(gate=self.gate)
        self.constitution = CapitalConstitution()
        self.domain = DemoDomainPolicy()
        self.allocator = MarginAllocator()
        self.epoch_tracker = AccountEpochTracker()
        self.order_adapter = DemoOrderAdapter(gate=self.gate)
        self.persistence = DemoExecutionPersistence(
            db_path=_data_root() / "validation.sqlite3",
        )
        self._last_cycle_result: dict[str, Any] | None = None
        self._orchestrator: DemoValidationOrchestrator | None = None

    def _build_orchestrator(self, reader: BybitDemoAccountReader | None = None) -> DemoValidationOrchestrator:
        return DemoValidationOrchestrator(
            gate=self.gate,
            reader=reader or _build_live_or_fake_reader(),
            persistence=self.persistence,
            epoch_tracker=self.epoch_tracker,
            order_adapter=self.order_adapter,
            kill_switch=self.kill_switch,
            export_dir=_data_root() / "artifacts" / "demo_validation",
        )

    def run_readonly_cycle(self, reader: BybitDemoAccountReader | None = None) -> dict[str, Any]:
        """Safe readonly cycle — no exchange writes. Uses live Demo private GET when keyed."""
        if reader is None:
            reader = _build_live_or_fake_reader()
            if isinstance(reader, FakeDemoAccountReader):
                from backend.nexus_demo_execution.account_reader import DemoAccountSnapshot

                # Offline fallback only — never used as capital source when live keys exist.
                reader.set_snapshot(
                    DemoAccountSnapshot(
                        wallet_balance=0.0,
                        equity=0.0,
                        available_balance=0.0,
                        margin_balance=0.0,
                        used_margin=0.0,
                        unrealized_pnl=0.0,
                        realized_pnl=0.0,
                        open_positions=[],
                        open_orders=[],
                    )
                )
        orch = self._build_orchestrator(reader)
        self._orchestrator = orch
        result = orch.run_readonly_cycle()
        payload = result.to_dict()
        self._last_cycle_result = payload
        return payload

    def status_payload(self) -> dict[str, Any]:
        gate_snap = self.gate.snapshot()
        return {
            **READ_ONLY_META,
            "fixed_leverage": FIXED_LEVERAGE,
            "max_open": MAX_OPEN,
            "max_pending": MAX_PENDING,
            "min_margin": MIN_MARGIN,
            "max_margin": MAX_MARGIN,
            "autonomous_mode": gate_snap["autonomous_mode"],
            "current_stage": gate_snap["current_stage"],
            "next_gate": gate_snap["next_gate"],
            "round_terminal": gate_snap.get("round_terminal"),
            "round_complete": gate_snap.get("round_complete", False),
            "first_demo_smoke_order_ready": gate_snap["first_demo_smoke_order_ready"],
            "can_write_orders": gate_snap["can_write_orders"],
            "exchange_write_call_count": self.order_adapter.exchange_write_call_count,
            "kill_switch": self.kill_switch.snapshot(),
            "constitution": self.constitution.snapshot(),
            "domain": self.domain.summary(),
            "persistence": self.persistence.summary(),
            "epoch": self.epoch_tracker.summary(),
            "order_adapter": self.order_adapter.counters(),
            "last_cycle": self._last_cycle_result,
        }

    def account_payload(self) -> dict[str, Any]:
        orch = self._orchestrator
        snap = orch._last_snapshot if orch else None
        if snap is None:
            return {"available": False, "reason": "no_cycle_run"}
        return {
            "wallet_balance": snap.wallet_balance,
            "equity": snap.equity,
            "available_balance": snap.available_balance,
            "open_positions": len(snap.open_positions),
            "open_orders": len(snap.open_orders),
            "source": snap.source,
        }

    def dry_run_latest(self) -> dict[str, Any]:
        if self._orchestrator:
            intent = self._orchestrator.latest_dry_run_intent()
            if intent:
                return {"found": True, "intent": intent}
        rows = self.persistence.read_all("dry_run_intents")
        if rows:
            return {"found": True, "intent": rows[-1]}
        return {"found": False}


_STATE = DemoExecutionApiState()


def get_demo_execution_state() -> DemoExecutionApiState:
    return _STATE


def _wrap(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    labels = list(payload.get("labels") or [])
    for label in READ_ONLY_META["labels"]:
        if label not in labels:
            labels.append(label)
    payload["labels"] = labels
    return {**READ_ONLY_META, **payload}


def register_demo_execution_routes(app: Flask) -> None:
    """Register /api/nexus/demo-execution/* read-only routes."""

    @app.route("/api/nexus/demo-execution/status")
    def demo_execution_status():
        return jsonify(_wrap(_STATE.status_payload()))

    @app.route("/api/nexus/demo-execution/gate")
    def demo_execution_gate():
        return jsonify(_wrap(_STATE.gate.snapshot()))

    @app.route("/api/nexus/demo-execution/account")
    def demo_execution_account():
        return jsonify(_wrap(_STATE.account_payload()))

    @app.route("/api/nexus/demo-execution/epoch")
    def demo_execution_epoch():
        return jsonify(_wrap(_STATE.epoch_tracker.summary()))

    @app.route("/api/nexus/demo-execution/dry-run/latest")
    def demo_execution_dry_run_latest():
        return jsonify(_wrap(_STATE.dry_run_latest()))

    @app.route("/api/nexus/demo-execution/constitution")
    def demo_execution_constitution():
        return jsonify(_wrap(_STATE.constitution.snapshot()))

    @app.route("/api/nexus/demo-execution/domain")
    def demo_execution_domain():
        return jsonify(_wrap(_STATE.domain.summary()))

    @app.route("/api/nexus/demo-execution/kill-switch")
    def demo_execution_kill_switch():
        return jsonify(_wrap(_STATE.kill_switch.snapshot()))

    @app.route("/api/nexus/demo-execution/persistence")
    def demo_execution_persistence():
        return jsonify(_wrap(_STATE.persistence.summary()))

    @app.route("/api/nexus/demo-execution/run-readonly-cycle", methods=["GET", "POST"])
    def demo_execution_run_readonly_cycle():
        """Trigger safe readonly validation cycle — live Demo GET when keyed; never exchange write."""
        result = _STATE.run_readonly_cycle()
        return jsonify(_wrap({"cycle": result}))

    logger.info("demo_execution_routes_registered")
