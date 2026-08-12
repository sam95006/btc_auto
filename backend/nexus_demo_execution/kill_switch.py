"""Kill switch — forces DEMO_AUTONOMOUS_DISABLED."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_demo_execution import BYBIT_DEMO, MAINNET, REAL_MONEY
from backend.nexus_demo_execution.safety_gate import (
    AutonomousMode,
    DemoExecutionSafetyGate,
    POST_FOUNDER_STAGES,
    SafetyGateStage,
)


class KillSwitchTrigger(str, Enum):
    OPERATOR_STOP = "OPERATOR_STOP"
    MAINNET_DETECTED = "MAINNET_DETECTED"
    REAL_MONEY_FLAG = "REAL_MONEY_FLAG"
    EXCHANGE_WRITE_ATTEMPTED = "EXCHANGE_WRITE_ATTEMPTED"
    FAKE_BALANCE_DETECTED = "FAKE_BALANCE_DETECTED"
    GATE_FAILURE = "GATE_FAILURE"
    PROTECTION_NOT_VERIFIED = "PROTECTION_NOT_VERIFIED"
    FOUNDER_BYPASS_ATTEMPT = "FOUNDER_BYPASS_ATTEMPT"
    AUTONOMOUS_WITHOUT_APPROVAL = "AUTONOMOUS_WITHOUT_APPROVAL"
    DEMO_BOUNDARY_VIOLATION = "DEMO_BOUNDARY_VIOLATION"
    CREDENTIAL_LEAK_DETECTED = "CREDENTIAL_LEAK_DETECTED"


FOUNDER_TRIGGER_LIST: tuple[KillSwitchTrigger, ...] = (
    KillSwitchTrigger.OPERATOR_STOP,
    KillSwitchTrigger.MAINNET_DETECTED,
    KillSwitchTrigger.REAL_MONEY_FLAG,
    KillSwitchTrigger.EXCHANGE_WRITE_ATTEMPTED,
    KillSwitchTrigger.FAKE_BALANCE_DETECTED,
    KillSwitchTrigger.GATE_FAILURE,
    KillSwitchTrigger.PROTECTION_NOT_VERIFIED,
    KillSwitchTrigger.FOUNDER_BYPASS_ATTEMPT,
    KillSwitchTrigger.AUTONOMOUS_WITHOUT_APPROVAL,
    KillSwitchTrigger.DEMO_BOUNDARY_VIOLATION,
    KillSwitchTrigger.CREDENTIAL_LEAK_DETECTED,
)


@dataclass
class KillSwitch:
    """Emergency stop — immediately disables autonomous demo execution."""

    gate: DemoExecutionSafetyGate
    engaged: bool = False
    reason: str = ""
    trigger: KillSwitchTrigger | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def engage(self, reason: str, *, trigger: KillSwitchTrigger | None = None) -> None:
        self.engaged = True
        self.reason = reason
        self.trigger = trigger or KillSwitchTrigger.OPERATOR_STOP
        self.gate.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
        self.gate.last_failure = f"kill_switch:{self.trigger.value}:{reason}"
        self.history.append(
            {
                "action": "engage",
                "reason": reason,
                "trigger": self.trigger.value,
            }
        )

    def engage_trigger(self, trigger: KillSwitchTrigger, *, detail: str = "") -> None:
        self.engage(detail or trigger.value, trigger=trigger)

    def release(self, *, founder_confirmed: bool = False) -> bool:
        if not founder_confirmed:
            return False
        self.engaged = False
        self.reason = ""
        self.trigger = None
        self.history.append({"action": "release", "founder_confirmed": True})
        return True

    def is_blocked(self) -> bool:
        return self.engaged or self.gate.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED

    def check_triggers(self, context: dict[str, Any] | None = None) -> bool:
        """Evaluate founder trigger list; engage if any condition met."""
        ctx = context or {}
        if not BYBIT_DEMO or MAINNET or REAL_MONEY:
            self.engage_trigger(KillSwitchTrigger.DEMO_BOUNDARY_VIOLATION)
            return True
        if ctx.get("mainnet_detected"):
            self.engage_trigger(KillSwitchTrigger.MAINNET_DETECTED)
            return True
        if ctx.get("real_money"):
            self.engage_trigger(KillSwitchTrigger.REAL_MONEY_FLAG)
            return True
        # Authorized one-shot founder smoke write is allowed; unauthorized writes trip kill.
        unauthorized_write = bool(ctx.get("unauthorized_exchange_write"))
        if unauthorized_write or (
            ctx.get("exchange_write_call_count", 0) > 0
            and not ctx.get("founder_smoke_authorized")
            and not self.gate.smoke_write_window_open
            and not self.gate.smoke_executed
        ):
            self.engage_trigger(KillSwitchTrigger.EXCHANGE_WRITE_ATTEMPTED)
            return True
        if ctx.get("fake_balance"):
            self.engage_trigger(KillSwitchTrigger.FAKE_BALANCE_DETECTED)
            return True
        if ctx.get("protection_not_verified"):
            self.engage_trigger(KillSwitchTrigger.PROTECTION_NOT_VERIFIED)
            return True
        if ctx.get("founder_bypass"):
            self.engage_trigger(KillSwitchTrigger.FOUNDER_BYPASS_ATTEMPT)
            return True
        # Smoke executed is allowed; autonomous without approval is not.
        if self.gate.current_stage == SafetyGateStage.DEMO_AUTONOMOUS_ENABLED:
            self.engage_trigger(KillSwitchTrigger.AUTONOMOUS_WITHOUT_APPROVAL)
            return True
        if (
            self.gate.current_stage == SafetyGateStage.DEMO_ORDER_SMOKE_EXECUTED
            and ctx.get("autonomous_without_approval")
        ):
            self.engage_trigger(KillSwitchTrigger.AUTONOMOUS_WITHOUT_APPROVAL)
            return True
        if self.gate.last_failure:
            self.engage_trigger(KillSwitchTrigger.GATE_FAILURE, detail=self.gate.last_failure)
            return True
        if ctx.get("credential_leak"):
            self.engage_trigger(KillSwitchTrigger.CREDENTIAL_LEAK_DETECTED)
            return True
        return False

    def snapshot(self) -> dict[str, Any]:
        return {
            "engaged": self.engaged,
            "reason": self.reason,
            "trigger": self.trigger.value if self.trigger else None,
            "blocked": self.is_blocked(),
            "autonomous_mode": self.gate.autonomous_mode.value,
            "current_stage": self.gate.current_stage.value,
            "history_count": len(self.history),
            "founder_triggers": [t.value for t in FOUNDER_TRIGGER_LIST],
        }

    def force_disable_gate(self) -> None:
        self.gate.current_stage = SafetyGateStage.READ_ONLY
        self.gate.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
