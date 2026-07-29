"""Read-only API routes for Bybit Demo Execution Validation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

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
from backend.nexus_demo_execution.allocation import MarginAllocator
from backend.nexus_demo_execution.capital_constitution import CapitalConstitution
from backend.nexus_demo_execution.demo_domain import DemoDomainPolicy
from backend.nexus_demo_execution.kill_switch import KillSwitch
from backend.nexus_demo_execution.order_adapter import DemoOrderAdapter
from backend.nexus_demo_execution.persistence import DemoExecutionPersistence
from backend.nexus_demo_execution.safety_gate import DemoExecutionSafetyGate

logger = logging.getLogger(__name__)

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
            db_path=Path("data/demo_execution/validation.sqlite3"),
        )

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
            "first_demo_smoke_order_ready": gate_snap["first_demo_smoke_order_ready"],
            "kill_switch": self.kill_switch.snapshot(),
            "constitution": self.constitution.snapshot(),
            "domain": self.domain.summary(),
            "persistence": self.persistence.summary(),
            "epoch": self.epoch_tracker.summary(),
            "order_adapter": self.order_adapter.counters(),
        }


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

    @app.route("/api/nexus/demo-execution/epoch")
    def demo_execution_epoch():
        return jsonify(_wrap(_STATE.epoch_tracker.summary()))

    logger.info("demo_execution_routes_registered")
