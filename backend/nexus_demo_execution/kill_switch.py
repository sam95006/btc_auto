"""Kill switch — forces DEMO_AUTONOMOUS_DISABLED."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_demo_execution.safety_gate import (
    AutonomousMode,
    DemoExecutionSafetyGate,
    SafetyGateStage,
)


@dataclass
class KillSwitch:
    """Emergency stop — immediately disables autonomous demo execution."""

    gate: DemoExecutionSafetyGate
    engaged: bool = False
    reason: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    def engage(self, reason: str) -> None:
        self.engaged = True
        self.reason = reason
        self.gate.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
        self.gate.last_failure = f"kill_switch:{reason}"
        self.history.append({"action": "engage", "reason": reason})

    def release(self, *, founder_confirmed: bool = False) -> bool:
        if not founder_confirmed:
            return False
        self.engaged = False
        self.reason = ""
        self.history.append({"action": "release", "founder_confirmed": True})
        return True

    def is_blocked(self) -> bool:
        return self.engaged or self.gate.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED

    def snapshot(self) -> dict[str, Any]:
        return {
            "engaged": self.engaged,
            "reason": self.reason,
            "blocked": self.is_blocked(),
            "autonomous_mode": self.gate.autonomous_mode.value,
            "current_stage": self.gate.current_stage.value,
            "history_count": len(self.history),
        }

    def force_disable_gate(self) -> None:
        self.gate.current_stage = SafetyGateStage.READ_ONLY
        self.gate.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
