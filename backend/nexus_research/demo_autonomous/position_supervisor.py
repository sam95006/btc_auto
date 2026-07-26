"""Wire DemoOrderMonitor + lifecycle + reflection for an open Demo position."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_autonomous.outcome_reflection import (
    ReflectionBundle,
    build_reflection_bundle,
)
from backend.nexus_research.demo_autonomous.position_lifecycle import (
    DemoPositionLifecycleController,
    ExitDecision,
    PositionSnapshot,
)
from backend.nexus_research.demo_autonomous.write_adapter import AutonomousDemoOrderAdapter
from backend.nexus_research.demo_execution.monitor import DemoOrderMonitor


@dataclass
class MonitorCycleResult:
    exit_decision: ExitDecision
    closed: bool
    reconciled: bool
    reflection: ReflectionBundle | None = None
    write_result: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit": self.exit_decision.to_dict(),
            "closed": self.closed,
            "reconciled": self.reconciled,
            "reflection": self.reflection.to_dict() if self.reflection else None,
            "writeResult": self.write_result,
            "notes": list(self.notes),
            "secretSafe": True,
            "mainnetUsed": False,
        }


class AutonomousPositionSupervisor:
    """Monitor → optional exit → reflection. Never blind-resends."""

    def __init__(
        self,
        *,
        write_adapter: AutonomousDemoOrderAdapter | None = None,
        dry_run: bool = True,
    ) -> None:
        self.write_adapter = write_adapter
        self.dry_run = dry_run
        self.lifecycle = DemoPositionLifecycleController()
        self.order_monitor = DemoOrderMonitor()

    def tick(
        self,
        pos: PositionSnapshot,
        *,
        stop_distance_pct: float,
        risk_amount: float,
        strategy: str,
        regime: str,
        confidence: float,
        leverage: int,
        spread_bps: float = 0.0,
        signal_reversed: bool = False,
        system_healthy: bool = True,
        emergency_stop: bool = False,
        mark_exit_pnl: float | None = None,
        fees: float = 0.0,
        funding: float = 0.0,
        slippage: float = 0.0,
    ) -> MonitorCycleResult:
        decision = self.lifecycle.evaluate(
            pos,
            stop_distance_pct=stop_distance_pct,
            spread_bps=spread_bps,
            regime=regime,
            signal_reversed=signal_reversed,
            system_healthy=system_healthy,
            emergency_stop=emergency_stop,
        )
        notes: list[str] = []
        if not decision.should_exit:
            return MonitorCycleResult(decision, False, True, notes=notes)

        closed = False
        write_payload = None
        if self.write_adapter is not None and pos.size > 0:
            res = self.write_adapter.close_position(pos.symbol, pos.side, pos.size)
            write_payload = res.to_dict()
            closed = bool(res.ok)
            if not res.ok:
                notes.append(f"close_failed:{res.error or res.ret_msg}")
        elif self.dry_run:
            closed = True
            write_payload = {"ok": True, "dryRun": True, "path": "/v5/order/create"}
            notes.append("dry_run_close_simulated")
        else:
            notes.append("write_adapter_missing")

        reflection = None
        if closed:
            pnl = float(mark_exit_pnl if mark_exit_pnl is not None else pos.unrealised_pnl)
            reflection = build_reflection_bundle(
                symbol=pos.symbol,
                side=pos.side,
                strategy=strategy,
                regime=regime,
                confidence=confidence,
                leverage=leverage,
                gross_pnl=pnl,
                fees=fees,
                funding=funding,
                slippage=slippage,
                risk_amount=risk_amount,
                holding_ms=max(0, int(time.time() * 1000) - pos.opened_at_ms),
                exit_reason=decision.reason.value,
            )

        return MonitorCycleResult(
            exit_decision=decision,
            closed=closed,
            reconciled=closed,
            reflection=reflection,
            write_result=write_payload,
            notes=notes,
        )
