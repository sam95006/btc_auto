#!/usr/bin/env python3
"""Offline CI runner — advances gates to FOUNDER_CONFIRMATION_REQUIRED using FakeReader."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.nexus_demo_execution.account_epoch import AccountEpochTracker
from backend.nexus_demo_execution.account_reader import DemoAccountSnapshot, FakeDemoAccountReader
from backend.nexus_demo_execution.kill_switch import KillSwitch
from backend.nexus_demo_execution.orchestration import DemoValidationOrchestrator
from backend.nexus_demo_execution.order_adapter import DemoOrderAdapter
from backend.nexus_demo_execution.persistence import DemoExecutionPersistence
from backend.nexus_demo_execution.safety_gate import (
    ROUND_TERMINAL_STAGE,
    DemoExecutionSafetyGate,
)


def _default_snapshot() -> DemoAccountSnapshot:
    return DemoAccountSnapshot(
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


def run_gate_chain(
    *,
    output_dir: Path,
    db_path: Path,
    wallet_balance: float = 200.0,
    available_balance: float = 180.0,
) -> dict:
    gate = DemoExecutionSafetyGate()
    reader = FakeDemoAccountReader()
    reader.set_snapshot(
        DemoAccountSnapshot(
            wallet_balance=wallet_balance,
            equity=wallet_balance,
            available_balance=available_balance,
            margin_balance=wallet_balance,
            used_margin=wallet_balance - available_balance,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            open_positions=[],
            open_orders=[],
        )
    )
    persistence = DemoExecutionPersistence(db_path=db_path)
    orchestrator = DemoValidationOrchestrator(
        gate=gate,
        reader=reader,
        persistence=persistence,
        epoch_tracker=AccountEpochTracker(),
        order_adapter=DemoOrderAdapter(gate=gate),
        kill_switch=KillSwitch(gate=gate),
        export_dir=output_dir,
    )
    result = orchestrator.run_readonly_cycle()
    report = {
        "success": result.success,
        "terminal_stage": gate.current_stage.value,
        "expected_terminal": ROUND_TERMINAL_STAGE.value,
        "exchange_write_call_count": result.exchange_write_call_count,
        "first_demo_smoke_order_ready": result.first_demo_smoke_order_ready,
        "autonomous_mode": result.autonomous_mode,
        "error": result.error,
        "output_dir": str(output_dir),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "gate_runner_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Demo validation gate runner (offline)")
    parser.add_argument(
        "--output-dir",
        default="artifacts/demo_validation",
        help="Evidence output directory",
    )
    parser.add_argument(
        "--db-path",
        default="artifacts/demo_validation/validation.sqlite3",
        help="SQLite persistence path",
    )
    parser.add_argument("--wallet-balance", type=float, default=200.0)
    parser.add_argument("--available-balance", type=float, default=180.0)
    args = parser.parse_args(argv)

    report = run_gate_chain(
        output_dir=Path(args.output_dir),
        db_path=Path(args.db_path),
        wallet_balance=args.wallet_balance,
        available_balance=args.available_balance,
    )
    print(json.dumps(report, indent=2, sort_keys=True))

    if not report["success"]:
        return 1
    if report["terminal_stage"] != ROUND_TERMINAL_STAGE.value:
        return 2
    if report["exchange_write_call_count"] != 0:
        return 3
    if report["first_demo_smoke_order_ready"]:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
