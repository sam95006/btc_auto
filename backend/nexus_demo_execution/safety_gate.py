"""Demo execution safety gate — staged enablement with fail-closed defaults."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_demo_execution import BYBIT_DEMO, DEMO_EXECUTION_LABELS, MAINNET, REAL_MONEY


class SafetyGateStage(str, Enum):
    READ_ONLY = "READ_ONLY"
    ACCOUNT_RECONCILED = "ACCOUNT_RECONCILED"
    DRY_RUN_INTENT = "DRY_RUN_INTENT"
    DEMO_ORDER_PAYLOAD_VALIDATED = "DEMO_ORDER_PAYLOAD_VALIDATED"
    PROTECTION_PAYLOAD_VALIDATED = "PROTECTION_PAYLOAD_VALIDATED"
    RESTART_RECOVERY_VERIFIED = "RESTART_RECOVERY_VERIFIED"
    PERSISTENCE_VERIFIED = "PERSISTENCE_VERIFIED"
    EXPORT_VERIFIED = "EXPORT_VERIFIED"
    PROTECTION_VERIFIED = "PROTECTION_VERIFIED"
    FOUNDER_CONFIRMATION_REQUIRED = "FOUNDER_CONFIRMATION_REQUIRED"
    # Post-founder stages — unreachable in validation round
    DEMO_ORDER_SMOKE_EXECUTED = "DEMO_ORDER_SMOKE_EXECUTED"
    DEMO_AUTONOMOUS_ENABLED = "DEMO_AUTONOMOUS_ENABLED"


class AutonomousMode(str, Enum):
    DEMO_AUTONOMOUS_DISABLED = "DEMO_AUTONOMOUS_DISABLED"
    DEMO_AUTONOMOUS_ENABLED = "DEMO_AUTONOMOUS_ENABLED"


STAGE_ORDER: tuple[SafetyGateStage, ...] = (
    SafetyGateStage.READ_ONLY,
    SafetyGateStage.ACCOUNT_RECONCILED,
    SafetyGateStage.DRY_RUN_INTENT,
    SafetyGateStage.DEMO_ORDER_PAYLOAD_VALIDATED,
    SafetyGateStage.PROTECTION_PAYLOAD_VALIDATED,
    SafetyGateStage.RESTART_RECOVERY_VERIFIED,
    SafetyGateStage.PERSISTENCE_VERIFIED,
    SafetyGateStage.EXPORT_VERIFIED,
    SafetyGateStage.PROTECTION_VERIFIED,
    SafetyGateStage.FOUNDER_CONFIRMATION_REQUIRED,
)

ROUND_TERMINAL_STAGE = SafetyGateStage.FOUNDER_CONFIRMATION_REQUIRED

POST_FOUNDER_STAGES = frozenset(
    {
        SafetyGateStage.DEMO_ORDER_SMOKE_EXECUTED,
        SafetyGateStage.DEMO_AUTONOMOUS_ENABLED,
    }
)


@dataclass
class GateTransition:
    stage: SafetyGateStage
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage.value, "passed": self.passed, "detail": self.detail}


@dataclass
class DemoExecutionSafetyGate:
    """Any failure forces DEMO_AUTONOMOUS_DISABLED."""

    current_stage: SafetyGateStage = SafetyGateStage.READ_ONLY
    autonomous_mode: AutonomousMode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
    transitions: list[GateTransition] = field(default_factory=list)
    last_failure: str = ""
    smoke_write_window_open: bool = False
    smoke_orders_remaining: int = 0
    smoke_executed: bool = False

    def reset(self) -> None:
        self.current_stage = SafetyGateStage.READ_ONLY
        self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
        self.transitions.clear()
        self.last_failure = ""
        self.smoke_write_window_open = False
        self.smoke_orders_remaining = 0
        # keep smoke_executed sticky within process unless explicit reset_smoke

    def reset_smoke_flags(self) -> None:
        self.smoke_write_window_open = False
        self.smoke_orders_remaining = 0
        self.smoke_executed = False

    def fail(self, detail: str) -> None:
        self.last_failure = detail
        self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
        self.smoke_write_window_open = False
        self.smoke_orders_remaining = 0
        self.transitions.append(
            GateTransition(stage=self.current_stage, passed=False, detail=detail)
        )

    def advance(self, stage: SafetyGateStage, *, detail: str = "") -> bool:
        if stage == SafetyGateStage.DEMO_AUTONOMOUS_ENABLED:
            self.fail(f"post_founder_stage_forbidden:{stage.value}")
            return False
        if stage == SafetyGateStage.DEMO_ORDER_SMOKE_EXECUTED:
            self.fail(f"use_complete_smoke_execution:{stage.value}")
            return False
        if stage not in STAGE_ORDER:
            self.fail(f"unknown_stage:{stage.value}")
            return False
        expected_idx = STAGE_ORDER.index(self.current_stage)
        target_idx = STAGE_ORDER.index(stage)
        if target_idx != expected_idx + 1 and target_idx > expected_idx:
            self.fail(f"stage_skip_forbidden:{self.current_stage.value}->{stage.value}")
            return False
        if not BYBIT_DEMO or MAINNET or REAL_MONEY:
            self.fail("demo_only_boundary_violation")
            return False
        self.current_stage = stage
        self.transitions.append(GateTransition(stage=stage, passed=True, detail=detail))
        self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
        return True

    def open_smoke_write_window(self, *, max_orders: int = 1) -> None:
        self.smoke_write_window_open = True
        self.smoke_orders_remaining = max_orders
        self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED

    def close_smoke_write_window(self) -> None:
        self.smoke_write_window_open = False
        self.smoke_orders_remaining = 0
        self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED

    def complete_smoke_execution(self, *, detail: str = "") -> bool:
        """Mark smoke complete — never enables autonomous."""
        if not BYBIT_DEMO or MAINNET or REAL_MONEY:
            self.fail("demo_only_boundary_violation")
            return False
        self.last_failure = ""
        self.current_stage = SafetyGateStage.DEMO_ORDER_SMOKE_EXECUTED
        self.smoke_executed = True
        self.close_smoke_write_window()
        self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
        self.transitions.append(
            GateTransition(
                stage=SafetyGateStage.DEMO_ORDER_SMOKE_EXECUTED,
                passed=True,
                detail=detail or "smoke_executed",
            )
        )
        return True

    def can_write_orders(self) -> bool:
        """True only during Founder one-shot smoke write window."""
        return (
            self.smoke_write_window_open
            and self.smoke_orders_remaining > 0
            and self.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED
            and not self.last_failure
        )

    @property
    def first_demo_smoke_order_ready(self) -> bool:
        """Ready when founder confirmation reached and smoke not yet executed."""
        return (
            self.current_stage == SafetyGateStage.FOUNDER_CONFIRMATION_REQUIRED
            and not self.smoke_executed
            and self.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED
            and not self.last_failure
        )

    @property
    def next_gate(self) -> str:
        if self.last_failure:
            return "RECOVERY_REQUIRED"
        if self.current_stage == SafetyGateStage.DEMO_ORDER_SMOKE_EXECUTED:
            return "FOUNDER_GATE=DEMO_AUTONOMOUS_6H_BOUNDED_VALIDATION"
        if self.current_stage == SafetyGateStage.DEMO_AUTONOMOUS_ENABLED:
            return "NONE"
        idx = STAGE_ORDER.index(self.current_stage)
        if idx >= len(STAGE_ORDER) - 1:
            return "NONE"
        return STAGE_ORDER[idx + 1].value

    @property
    def round_complete(self) -> bool:
        return (
            self.current_stage
            in {
                ROUND_TERMINAL_STAGE,
                SafetyGateStage.DEMO_ORDER_SMOKE_EXECUTED,
            }
            and not self.last_failure
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "current_stage": self.current_stage.value,
            "autonomous_mode": self.autonomous_mode.value,
            "next_gate": self.next_gate,
            "round_terminal": ROUND_TERMINAL_STAGE.value,
            "round_complete": self.round_complete,
            "first_demo_smoke_order_ready": self.first_demo_smoke_order_ready,
            "can_write_orders": self.can_write_orders(),
            "smoke_write_window_open": self.smoke_write_window_open,
            "smoke_orders_remaining": self.smoke_orders_remaining,
            "smoke_executed": self.smoke_executed,
            "last_failure": self.last_failure,
            "labels": list(DEMO_EXECUTION_LABELS),
            "transitions": [t.to_dict() for t in self.transitions],
        }
