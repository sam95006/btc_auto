"""Demo order execution foundation — TRACK 5-6.

order_sent is ALWAYS False. Write methods raise WriteNotAuthorizedError.
Adapter must NOT call exchange write even if credentials present.
"""
from __future__ import annotations

from backend.nexus_research.demo_execution.adapter import (
    AdapterReadResult,
    DemoOrderAdapter,
)
from backend.nexus_research.demo_execution.candidate import (
    CANDIDATE_EQUITY,
    CANDIDATE_FIXTURE_ENTRY_PRICE,
    CANDIDATE_STOP_DISTANCE_PCT,
    CANDIDATE_SYMBOL,
    ClosePlan,
    FirstControlledDemoOrderCandidate,
    StopPlan,
    build_first_controlled_candidate,
)
from backend.nexus_research.demo_execution.close_controller import (
    CloseRequest,
    CloseResult,
    DemoCloseController,
)
from backend.nexus_research.demo_execution.intent import (
    AuthorizationReplayError,
    DemoOrderAuthorization,
    DemoOrderIntent,
    NotAuthorizedError,
    WriteNotAuthorizedError,
)
from backend.nexus_research.demo_execution.ledger import (
    AuditRecord,
    DemoExecutionLedger,
    DemoOrderAuditTrail,
    LedgerEntry,
)
from backend.nexus_research.demo_execution.monitor import (
    DemoOrderMonitor,
    MonitorEvent,
    TimeoutPolicy,
)
from backend.nexus_research.demo_execution.preflight import (
    DemoOrderPreflight,
    PreflightGate,
    PreflightResult,
)
from backend.nexus_research.demo_execution.reconciler import (
    DemoOrderReconciler,
    OrderMismatchReason,
    OrderReconciliationResult,
)
from backend.nexus_research.demo_execution.recovery import (
    DemoOrderRecovery,
    RecoveryAction,
)
from backend.nexus_research.demo_execution.state_machine import (
    BLOCKED_STATES,
    TERMINAL_STATES,
    DemoOrderState,
    DemoOrderStateMachine,
    StateTransition,
)

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False
WRITE_ALLOWED: bool = False

__all__ = [
    "BLOCKED_STATES",
    "CANDIDATE_EQUITY",
    "CANDIDATE_FIXTURE_ENTRY_PRICE",
    "CANDIDATE_STOP_DISTANCE_PCT",
    "CANDIDATE_SYMBOL",
    "AdapterReadResult",
    "AuditRecord",
    "AuthorizationReplayError",
    "CloseRequest",
    "CloseResult",
    "ClosePlan",
    "DemoCloseController",
    "DemoExecutionLedger",
    "DemoOrderAdapter",
    "DemoOrderAuditTrail",
    "DemoOrderAuthorization",
    "DemoOrderIntent",
    "DemoOrderMonitor",
    "DemoOrderPreflight",
    "DemoOrderReconciler",
    "DemoOrderRecovery",
    "DemoOrderState",
    "DemoOrderStateMachine",
    "FirstControlledDemoOrderCandidate",
    "LedgerEntry",
    "MonitorEvent",
    "NotAuthorizedError",
    "ORDER_SENT",
    "OrderMismatchReason",
    "OrderReconciliationResult",
    "PreflightGate",
    "PreflightResult",
    "RESEARCH_ONLY",
    "RecoveryAction",
    "StateTransition",
    "StopPlan",
    "TERMINAL_STATES",
    "TimeoutPolicy",
    "WRITE_ALLOWED",
    "WriteNotAuthorizedError",
    "build_first_controlled_candidate",
]
