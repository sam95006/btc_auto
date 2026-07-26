"""Phase 6.6 / 6.6.1 — Bybit Demo READ-ONLY foundation + probe readiness.

Hard rules:
- Domain: https://api-demo.bybit.com only
- GET-only transport; POST/PUT/DELETE impossible
- No create/amend/cancel/leverage/transfer/withdraw
- PAPER (NEXUS_PAPER_MAIN_V1) and BYBIT_DEMO_ACCOUNT never mixed
- Secrets never logged; fingerprint max 8 chars
- Phase 6.6.1: probe returns BLOCKED_CREDENTIALS_MISSING when absent
"""
from __future__ import annotations

from backend.nexus_research.demo_exchange.account_snapshot import (
    AccountSnapshotResult,
    SnapshotStatus,
    capture_account_snapshot,
)
from backend.nexus_research.demo_exchange.constants import (
    ACCOUNT_BYBIT_DEMO,
    ACCOUNT_PAPER_MAIN_V1,
    DEMO_REST_BASE_URL,
    DEMO_WS_PRIVATE_NOTE,
    PHASE,
    RESEARCH_ONLY,
    WRITE_ALLOWED,
)
from backend.nexus_research.demo_exchange.credential_audit import (
    BootContinuityRecord,
    DemoCredentialPresenceAudit,
    credential_fingerprint,
)
from backend.nexus_research.demo_exchange.credentials import (
    DemoCredentialPresenceValidator,
    fingerprint_secret,
)
from backend.nexus_research.demo_exchange.discovery import (
    DEMO_READONLY_PROBE_ENABLED_ENV,
    CredentialDiscoveryResult,
    DemoReadinessReport,
    DiscoveryStatus,
    discover_credentials,
)
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.factory import DemoPrivateClientFactory
from backend.nexus_research.demo_exchange.identity import (
    AccountBoundary,
    DemoSnapshotIdentity,
    ExchangeAccountIdentity,
)
from backend.nexus_research.demo_exchange.probe_readiness import (
    CredentialConfiguredState,
    DemoConnectivityResult,
    DemoReadinessStatus,
    DemoReadOnlyProbeCommand,
    ProbeAuditRecord,
    ProbeFailClosedPolicy,
    ReadOnlyEndpointAllowlist,
    ReadOnlySnapshotReport,
)
from backend.nexus_research.demo_exchange.readonly_probe import (
    ReadOnlyProbeResult,
    run_readonly_probe,
)
from backend.nexus_research.demo_exchange.readers import (
    DemoExchangeSnapshot,
    DemoExecutionReader,
    DemoOpenOrderReader,
    DemoOrderHistoryReader,
    DemoPositionReader,
    DemoWalletReader,
)
from backend.nexus_research.demo_exchange.reconciliation import (
    DemoLedgerReconciler,
    FailClosedMismatchPolicy,
    MismatchReason,
    ReconciliationResult,
)
from backend.nexus_research.demo_exchange.recovery import (
    DuplicateExecutionDetector,
    ExchangeSnapshotCheckpoint,
    IdempotentClientOrderIdGenerator,
    RestartRecoveryPlan,
)
from backend.nexus_research.demo_exchange.signer import DemoRequestSigner
from backend.nexus_research.demo_exchange.state_machine import DemoState, DemoStateMachine
from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

__all__ = [
    "ACCOUNT_BYBIT_DEMO",
    "ACCOUNT_PAPER_MAIN_V1",
    "AccountBoundary",
    "AccountSnapshotResult",
    "BootContinuityRecord",
    "CredentialConfiguredState",
    "CredentialDiscoveryResult",
    "DEMO_READONLY_PROBE_ENABLED_ENV",
    "DEMO_REST_BASE_URL",
    "DEMO_WS_PRIVATE_NOTE",
    "DemoConnectivityResult",
    "DemoCredentialPresenceAudit",
    "DemoCredentialPresenceValidator",
    "DemoDomainPolicy",
    "DemoExchangeSnapshot",
    "DemoExecutionReader",
    "DemoLedgerReconciler",
    "DemoOpenOrderReader",
    "DemoOrderHistoryReader",
    "DemoPositionReader",
    "DemoPrivateClientFactory",
    "DemoReadOnlyProbeCommand",
    "DemoReadOnlyTransport",
    "DemoReadinessReport",
    "DemoReadinessStatus",
    "DemoRequestSigner",
    "DemoSnapshotIdentity",
    "DemoState",
    "DemoStateMachine",
    "DemoWalletReader",
    "DiscoveryStatus",
    "DuplicateExecutionDetector",
    "ExchangeAccountIdentity",
    "ExchangeSnapshotCheckpoint",
    "FailClosedMismatchPolicy",
    "IdempotentClientOrderIdGenerator",
    "MismatchReason",
    "PHASE",
    "ProbeAuditRecord",
    "ProbeFailClosedPolicy",
    "RESEARCH_ONLY",
    "ReadOnlyEndpointAllowlist",
    "ReadOnlyProbeResult",
    "ReadOnlySnapshotReport",
    "ReconciliationResult",
    "RestartRecoveryPlan",
    "SnapshotStatus",
    "WRITE_ALLOWED",
    "capture_account_snapshot",
    "credential_fingerprint",
    "discover_credentials",
    "fingerprint_secret",
    "run_readonly_probe",
]
