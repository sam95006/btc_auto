"""Phase 6.6.1 — Demo Read-Only Probe Readiness foundation.

Hard rules (inherited from Phase 6.6, extended):
- BLOCKED_CREDENTIALS_MISSING when credentials absent
- Never require user to paste keys now
- Never display secrets
- Never write secrets to git
- Never call Write APIs
- Never create demo money
- Never modify PAPER
- Never treat PAPER balance as Demo balance
- Never auto-connect Live Demo without approval
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_research.demo_exchange.constants import (
    ACCOUNT_BYBIT_DEMO,
    ALLOWED_GET_PATHS,
    DEMO_REST_BASE_URL,
    FORBIDDEN_WRITE_PATH_FRAGMENTS,
    PHASE,
)
from backend.nexus_research.demo_exchange.credentials import (
    CredentialPresence,
    DemoCredentialPresenceValidator,
)
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import (
    CredentialMissingError,
    DemoExchangeError,
    DomainRejectedError,
    MalformedResponseError,
    MethodNotAllowedError,
    PermissionDeniedError,
    RateLimitError,
    SignatureInvalidError,
    TimeoutError_,
    WriteForbiddenError,
)
from backend.nexus_research.demo_exchange.identity import AccountBoundary
from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport


# ---------------------------------------------------------------------------
# 1. DemoReadinessStatus
# ---------------------------------------------------------------------------
class DemoReadinessStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    BLOCKED_CREDENTIALS_MISSING = "BLOCKED_CREDENTIALS_MISSING"
    BLOCKED_CREDENTIAL_INVALID = "BLOCKED_CREDENTIAL_INVALID"
    BLOCKED_CONNECTIVITY_FAILED = "BLOCKED_CONNECTIVITY_FAILED"
    BLOCKED_IDENTITY_MISMATCH = "BLOCKED_IDENTITY_MISMATCH"
    BLOCKED_POLICY_VIOLATION = "BLOCKED_POLICY_VIOLATION"
    BLOCKED_FAIL_CLOSED = "BLOCKED_FAIL_CLOSED"
    PROBE_PASSED = "PROBE_PASSED"
    PROBE_FAILED = "PROBE_FAILED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"


# ---------------------------------------------------------------------------
# 3. CredentialConfiguredState
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CredentialConfiguredState:
    """Immutable snapshot of credential presence for probe decisions."""
    presence: CredentialPresence
    checked_at_ms: int
    phase: str = "6.6.1"

    @classmethod
    def check(
        cls,
        validator: DemoCredentialPresenceValidator | None = None,
    ) -> "CredentialConfiguredState":
        v = validator or DemoCredentialPresenceValidator()
        presence = v.validate(require=False)
        return cls(
            presence=presence,
            checked_at_ms=int(time.time() * 1000),
        )

    @property
    def configured(self) -> bool:
        return self.presence.configured

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "key_present": self.presence.key_present,
            "secret_present": self.presence.secret_present,
            "fingerprint": self.presence.fingerprint,
            "checked_at_ms": self.checked_at_ms,
            "phase": self.phase,
        }


# ---------------------------------------------------------------------------
# 5. ReadOnlyEndpointAllowlist
# ---------------------------------------------------------------------------
class ReadOnlyEndpointAllowlist:
    """Validates paths against hard GET-only allowlist; rejects all writes."""

    def __init__(self) -> None:
        self._allowed: frozenset[str] = ALLOWED_GET_PATHS
        self._forbidden_fragments: tuple[str, ...] = FORBIDDEN_WRITE_PATH_FRAGMENTS

    @property
    def allowed_paths(self) -> frozenset[str]:
        return self._allowed

    def is_allowed(self, path: str) -> bool:
        return path in self._allowed

    def is_write_endpoint(self, path: str) -> bool:
        if path in self._allowed:
            return False
        p = (path or "").lower()
        for frag in self._forbidden_fragments:
            if frag.lower() in p:
                return True
        return False

    def assert_allowed(self, path: str) -> None:
        if self.is_write_endpoint(path):
            raise WriteForbiddenError(f"write_endpoint_denied:{path}")
        if not self.is_allowed(path):
            raise WriteForbiddenError(f"path_not_in_allowlist:{path}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_paths": sorted(self._allowed),
            "forbidden_write_fragments": list(self._forbidden_fragments),
            "get_only": True,
            "write_allowed": False,
        }


# ---------------------------------------------------------------------------
# 4. DemoConnectivityResult
# ---------------------------------------------------------------------------
@dataclass
class DemoConnectivityResult:
    reachable: bool
    latency_ms: int = 0
    error_code: str = ""
    error_detail: str = ""
    endpoint_tested: str = ""
    domain: str = DEMO_REST_BASE_URL
    used_fixtures: bool = False
    ret_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reachable": self.reachable,
            "latency_ms": self.latency_ms,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "endpoint_tested": self.endpoint_tested,
            "domain": self.domain,
            "used_fixtures": self.used_fixtures,
            "ret_code": self.ret_code,
        }


# ---------------------------------------------------------------------------
# 6. ProbeAuditRecord
# ---------------------------------------------------------------------------
@dataclass
class ProbeAuditRecord:
    probe_id: str = ""
    started_at_ms: int = 0
    finished_at_ms: int = 0
    credential_state: CredentialConfiguredState | None = None
    connectivity: DemoConnectivityResult | None = None
    readiness_status: DemoReadinessStatus = DemoReadinessStatus.NOT_STARTED
    endpoint_allowlist_verified: bool = False
    write_attempted: bool = False
    secret_leaked: bool = False
    account_identity_ok: bool = False
    fail_closed_enforced: bool = False
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.probe_id:
            raw = f"probe661:{self.started_at_ms}:{id(self)}"
            self.probe_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "started_at_ms": self.started_at_ms,
            "finished_at_ms": self.finished_at_ms,
            "credential_state": self.credential_state.to_dict() if self.credential_state else None,
            "connectivity": self.connectivity.to_dict() if self.connectivity else None,
            "readiness_status": self.readiness_status.value,
            "endpoint_allowlist_verified": self.endpoint_allowlist_verified,
            "write_attempted": self.write_attempted,
            "secret_leaked": self.secret_leaked,
            "account_identity_ok": self.account_identity_ok,
            "fail_closed_enforced": self.fail_closed_enforced,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# 7. ReadOnlySnapshotReport
# ---------------------------------------------------------------------------
@dataclass
class ReadOnlySnapshotReport:
    """Report summarizing a read-only probe snapshot attempt."""
    probe_id: str = ""
    account_id: str = ACCOUNT_BYBIT_DEMO
    domain: str = DEMO_REST_BASE_URL
    wallet_readable: bool = False
    position_readable: bool = False
    order_readable: bool = False
    execution_readable: bool = False
    used_fixtures: bool = False
    endpoints_probed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    captured_at_ms: int = 0

    def __post_init__(self) -> None:
        if not self.captured_at_ms:
            self.captured_at_ms = int(time.time() * 1000)

    @property
    def all_readable(self) -> bool:
        return (
            self.wallet_readable
            and self.position_readable
            and self.order_readable
            and self.execution_readable
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "account_id": self.account_id,
            "domain": self.domain,
            "wallet_readable": self.wallet_readable,
            "position_readable": self.position_readable,
            "order_readable": self.order_readable,
            "execution_readable": self.execution_readable,
            "all_readable": self.all_readable,
            "used_fixtures": self.used_fixtures,
            "endpoints_probed": list(self.endpoints_probed),
            "errors": list(self.errors),
            "captured_at_ms": self.captured_at_ms,
        }


# ---------------------------------------------------------------------------
# 8. ProbeFailClosedPolicy
# ---------------------------------------------------------------------------
class ProbeFailClosedPolicy:
    """Any failure during probe → BLOCKED. Never silent-pass."""

    def evaluate(self, audit: ProbeAuditRecord) -> DemoReadinessStatus:
        if audit.write_attempted:
            audit.fail_closed_enforced = True
            return DemoReadinessStatus.BLOCKED_FAIL_CLOSED
        if audit.secret_leaked:
            audit.fail_closed_enforced = True
            return DemoReadinessStatus.BLOCKED_FAIL_CLOSED
        if audit.credential_state and not audit.credential_state.configured:
            return DemoReadinessStatus.BLOCKED_CREDENTIALS_MISSING
        if audit.connectivity and not audit.connectivity.reachable:
            return DemoReadinessStatus.BLOCKED_CONNECTIVITY_FAILED
        if not audit.account_identity_ok:
            return DemoReadinessStatus.BLOCKED_IDENTITY_MISMATCH
        if audit.errors:
            audit.fail_closed_enforced = True
            return DemoReadinessStatus.BLOCKED_FAIL_CLOSED
        return DemoReadinessStatus.PROBE_PASSED


# ---------------------------------------------------------------------------
# 2. DemoReadOnlyProbeCommand
# ---------------------------------------------------------------------------
class DemoReadOnlyProbeCommand:
    """Execute a scoped read-only probe. Never calls write APIs.

    Returns BLOCKED_CREDENTIALS_MISSING when credentials absent.
    Never requires user to paste keys, display secrets, write secrets to git,
    call Write APIs, create demo money, modify PAPER, treat PAPER balance as
    Demo balance, or auto-connect Live Demo without approval.
    """

    def __init__(
        self,
        *,
        credential_validator: DemoCredentialPresenceValidator | None = None,
        domain_policy: DemoDomainPolicy | None = None,
        transport: DemoReadOnlyTransport | None = None,
        fail_closed_policy: ProbeFailClosedPolicy | None = None,
    ) -> None:
        self._cred_validator = credential_validator or DemoCredentialPresenceValidator()
        self._domain_policy = domain_policy or DemoDomainPolicy(DEMO_REST_BASE_URL)
        self._transport = transport
        self._fail_closed = fail_closed_policy or ProbeFailClosedPolicy()
        self._allowlist = ReadOnlyEndpointAllowlist()

    def execute(self) -> ProbeAuditRecord:
        audit = ProbeAuditRecord(started_at_ms=int(time.time() * 1000))

        # Step 1: Credential check
        cred_state = CredentialConfiguredState.check(self._cred_validator)
        audit.credential_state = cred_state

        if not cred_state.configured:
            audit.readiness_status = DemoReadinessStatus.BLOCKED_CREDENTIALS_MISSING
            audit.finished_at_ms = int(time.time() * 1000)
            return audit

        # Step 2: Domain policy
        try:
            self._domain_policy.assert_url_allowed(DEMO_REST_BASE_URL)
        except DomainRejectedError as exc:
            audit.errors.append(f"domain_policy:{exc}")
            audit.readiness_status = DemoReadinessStatus.BLOCKED_POLICY_VIOLATION
            audit.finished_at_ms = int(time.time() * 1000)
            return audit

        # Step 3: Endpoint allowlist verification
        audit.endpoint_allowlist_verified = True
        for path in self._allowlist.allowed_paths:
            try:
                self._domain_policy.assert_method_allowed("GET")
                if self._allowlist.is_write_endpoint(path):
                    raise WriteForbiddenError(f"allowlisted_path_flagged_as_write:{path}")
            except DemoExchangeError as exc:
                audit.endpoint_allowlist_verified = False
                audit.errors.append(f"allowlist_check:{exc}")

        # Step 4: Account boundary
        try:
            boundary = AccountBoundary()
            boundary.assert_demo_identity(ACCOUNT_BYBIT_DEMO)
            audit.account_identity_ok = True
        except Exception as exc:  # noqa: BLE001
            audit.errors.append(f"account_boundary:{exc}")
            audit.account_identity_ok = False

        # Step 5: Connectivity probe (if transport available)
        connectivity = self._probe_connectivity(audit)
        audit.connectivity = connectivity

        # Step 6: Snapshot report (if transport available and connected)
        if connectivity.reachable and self._transport:
            self._probe_snapshot(audit)

        # Step 7: Fail-closed evaluation
        audit.readiness_status = self._fail_closed.evaluate(audit)
        audit.finished_at_ms = int(time.time() * 1000)
        return audit

    def _probe_connectivity(self, audit: ProbeAuditRecord) -> DemoConnectivityResult:
        if self._transport is None:
            return DemoConnectivityResult(
                reachable=False,
                error_code="no_transport",
                error_detail="transport_not_configured",
                endpoint_tested="/v5/account/wallet-balance",
                used_fixtures=False,
            )

        start = time.monotonic()
        try:
            result = self._transport.request(
                "GET",
                "/v5/account/wallet-balance",
                {"accountType": "UNIFIED"},
            )
            elapsed = int((time.monotonic() - start) * 1000)
            ret_code = int(result.get("retCode", -1))
            return DemoConnectivityResult(
                reachable=True,
                latency_ms=elapsed,
                endpoint_tested="/v5/account/wallet-balance",
                domain=self._domain_policy.base_url,
                used_fixtures=self._transport.use_fixtures,
                ret_code=ret_code,
            )
        except (
            SignatureInvalidError,
            PermissionDeniedError,
        ) as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            audit.errors.append(f"connectivity:{type(exc).__name__}")
            return DemoConnectivityResult(
                reachable=False,
                latency_ms=elapsed,
                error_code=type(exc).__name__,
                error_detail=str(exc),
                endpoint_tested="/v5/account/wallet-balance",
                domain=self._domain_policy.base_url,
                used_fixtures=self._transport.use_fixtures,
            )
        except (TimeoutError_, RateLimitError) as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            audit.errors.append(f"connectivity:{type(exc).__name__}")
            return DemoConnectivityResult(
                reachable=False,
                latency_ms=elapsed,
                error_code=type(exc).__name__,
                error_detail=str(exc),
                endpoint_tested="/v5/account/wallet-balance",
                domain=self._domain_policy.base_url,
                used_fixtures=self._transport.use_fixtures,
            )
        except (MalformedResponseError, Exception) as exc:  # noqa: BLE001
            elapsed = int((time.monotonic() - start) * 1000)
            audit.errors.append(f"connectivity:{type(exc).__name__}")
            return DemoConnectivityResult(
                reachable=False,
                latency_ms=elapsed,
                error_code=type(exc).__name__,
                error_detail=str(exc),
                endpoint_tested="/v5/account/wallet-balance",
                domain=self._domain_policy.base_url,
                used_fixtures=self._transport.use_fixtures,
            )

    def _probe_snapshot(self, audit: ProbeAuditRecord) -> ReadOnlySnapshotReport:
        assert self._transport is not None  # noqa: S101
        report = ReadOnlySnapshotReport(
            probe_id=audit.probe_id,
            domain=self._domain_policy.base_url,
            used_fixtures=self._transport.use_fixtures,
        )
        probe_paths = [
            ("/v5/account/wallet-balance", "wallet_readable"),
            ("/v5/position/list", "position_readable"),
            ("/v5/order/realtime", "order_readable"),
            ("/v5/execution/list", "execution_readable"),
        ]
        for path, attr in probe_paths:
            try:
                self._transport.request("GET", path, {})
                setattr(report, attr, True)
                report.endpoints_probed.append(path)
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"{path}:{type(exc).__name__}")
        return report
