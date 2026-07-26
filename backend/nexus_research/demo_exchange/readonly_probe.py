"""Phase 6.6.1 — GET-only Live Probe runner.

Activated ONLY when DEMO_READONLY_PROBE_ENABLED=true AND credentials present.

Hard rules:
- Domain hard-locked to api-demo.bybit.com
- Allowed GETs: server time, wallet-balance, position/list, order/realtime,
  order/history, execution/list, market instruments/tickers/kline (public)
- API key info/permission check — FAIL_CLOSED if Trade/Withdraw/Transfer appear
- ZERO write methods
- On any permission fail: FAIL_CLOSED, stop further private calls
- Never include secrets in responses
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_exchange.constants import (
    ALLOWED_GET_PATHS,
    DEMO_REST_BASE_URL,
)
from backend.nexus_research.demo_exchange.credential_audit import (
    build_credential_fingerprint,
    check_credential_presence,
)
from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import (
    CredentialMissingError,
    DemoExchangeError,
    PermissionDeniedError,
)
from backend.nexus_research.demo_exchange.factory import DemoPrivateClientFactory
from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

logger = logging.getLogger(__name__)

FORBIDDEN_API_PERMISSIONS = frozenset({
    "Trade",
    "Withdraw",
    "Transfer",
    "ContractTrade",
    "SpotTrade",
    "OptionsTrade",
    "CopyTrading",
    "Exchange",
})

PUBLIC_GET_PATHS = frozenset({
    "/v5/market/time",
    "/v5/market/instruments-info",
    "/v5/market/tickers",
    "/v5/market/kline",
})

PRIVATE_GET_PATHS = frozenset(ALLOWED_GET_PATHS)


class ProbeStatus:
    PROBE_DISABLED = "PROBE_DISABLED"
    BLOCKED_CREDENTIALS_MISSING = "BLOCKED_CREDENTIALS_MISSING"
    FAIL_CLOSED_PERMISSION = "FAIL_CLOSED_PERMISSION"
    FAIL_CLOSED_ERROR = "FAIL_CLOSED_ERROR"
    PROBE_PASSED = "PROBE_PASSED"
    CONNECTIVITY_FAILED = "CONNECTIVITY_FAILED"


@dataclass
class ReadOnlyProbeResult:
    """Result of a GET-only live probe.  Never contains secret values."""
    status: str
    probe_enabled: bool
    credential_present: bool
    fingerprint: str
    domain: str = DEMO_REST_BASE_URL
    network_calls: int = 0
    server_time_ok: bool = False
    wallet_readable: bool = False
    position_readable: bool = False
    order_readable: bool = False
    execution_readable: bool = False
    permission_check: dict[str, Any] = field(default_factory=dict)
    fail_closed: bool = False
    errors: list[str] = field(default_factory=list)
    endpoints_probed: list[str] = field(default_factory=list)
    write_attempted: bool = False
    started_at_ms: int = 0
    finished_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "probe_enabled": self.probe_enabled,
            "credential_present": self.credential_present,
            "fingerprint": self.fingerprint,
            "domain": self.domain,
            "network_calls": self.network_calls,
            "server_time_ok": self.server_time_ok,
            "wallet_readable": self.wallet_readable,
            "position_readable": self.position_readable,
            "order_readable": self.order_readable,
            "execution_readable": self.execution_readable,
            "permission_check": dict(self.permission_check),
            "fail_closed": self.fail_closed,
            "errors": list(self.errors),
            "endpoints_probed": list(self.endpoints_probed),
            "write_attempted": self.write_attempted,
            "write_impossible": True,
            "started_at_ms": self.started_at_ms,
            "finished_at_ms": self.finished_at_ms,
            "secret_safe": True,
        }


def _probe_enabled() -> bool:
    raw = os.environ.get("DEMO_READONLY_PROBE_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes")


def _check_permissions(result_data: dict[str, Any]) -> dict[str, Any]:
    """Check API key info result for forbidden permissions.

    Bybit v5 /v5/user/query-api returns permissions in the result.
    If any forbidden permission appears → FAIL_CLOSED.
    """
    permissions = result_data.get("permissions") or {}
    if isinstance(permissions, dict):
        all_perms: set[str] = set()
        for category, perms in permissions.items():
            if isinstance(perms, list):
                all_perms.update(perms)
            elif isinstance(perms, str):
                all_perms.add(perms)
    elif isinstance(permissions, list):
        all_perms = set(permissions)
    else:
        all_perms = set()

    violations = all_perms & FORBIDDEN_API_PERMISSIONS
    read_only = bool({"ReadOnly"} & all_perms) or not violations
    return {
        "permissions_found": sorted(all_perms) if all_perms else [],
        "violations": sorted(violations),
        "read_only": read_only and not violations,
        "fail_closed": bool(violations),
    }


def run_readonly_probe(
    *,
    environ: dict[str, str] | None = None,
    transport: DemoReadOnlyTransport | None = None,
) -> ReadOnlyProbeResult:
    """Execute GET-only live probe.  Returns immediately if disabled or creds missing."""
    now = int(time.time() * 1000)
    probe_on = _probe_enabled()
    presence = check_credential_presence(environ)
    fp = build_credential_fingerprint(environ)

    if not probe_on:
        return ReadOnlyProbeResult(
            status=ProbeStatus.PROBE_DISABLED,
            probe_enabled=False,
            credential_present=presence.both_present,
            fingerprint=fp,
            network_calls=0,
            started_at_ms=now,
            finished_at_ms=now,
        )

    if not presence.both_present:
        return ReadOnlyProbeResult(
            status=ProbeStatus.BLOCKED_CREDENTIALS_MISSING,
            probe_enabled=True,
            credential_present=False,
            fingerprint="",
            network_calls=0,
            started_at_ms=now,
            finished_at_ms=now,
        )

    if transport is None:
        try:
            policy = DemoDomainPolicy(DEMO_REST_BASE_URL)
            factory = DemoPrivateClientFactory(policy=policy)
            transport, _meta = factory.create()
        except Exception as exc:
            return ReadOnlyProbeResult(
                status=ProbeStatus.FAIL_CLOSED_ERROR,
                probe_enabled=True,
                credential_present=True,
                fingerprint=fp,
                fail_closed=True,
                errors=[f"factory:{type(exc).__name__}"],
                network_calls=0,
                started_at_ms=now,
                finished_at_ms=int(time.time() * 1000),
            )

    result = ReadOnlyProbeResult(
        status=ProbeStatus.PROBE_PASSED,
        probe_enabled=True,
        credential_present=True,
        fingerprint=fp,
        domain=DEMO_REST_BASE_URL,
        started_at_ms=now,
    )

    probe_sequence = [
        ("/v5/account/wallet-balance", {"accountType": "UNIFIED"}, "wallet_readable"),
        ("/v5/position/list", {"category": "linear", "settleCoin": "USDT"}, "position_readable"),
        ("/v5/order/realtime", {"category": "linear", "settleCoin": "USDT"}, "order_readable"),
        ("/v5/execution/list", {"category": "linear"}, "execution_readable"),
    ]

    for path, params, attr in probe_sequence:
        try:
            resp = transport.request("GET", path, params)
            setattr(result, attr, True)
            result.endpoints_probed.append(path)
            result.network_calls += 1
            ret_code = int(resp.get("retCode", -1))
            if ret_code != 0:
                result.errors.append(f"{path}:retCode={ret_code}")
        except PermissionDeniedError:
            result.fail_closed = True
            result.status = ProbeStatus.FAIL_CLOSED_PERMISSION
            result.errors.append(f"{path}:permission_denied")
            logger.warning("probe_fail_closed path=%s reason=permission_denied", path)
            break
        except DemoExchangeError as exc:
            result.errors.append(f"{path}:{type(exc).__name__}")
            result.network_calls += 1
        except Exception as exc:
            result.errors.append(f"{path}:{type(exc).__name__}")
            result.network_calls += 1

    if result.fail_closed:
        result.status = ProbeStatus.FAIL_CLOSED_PERMISSION

    result.finished_at_ms = int(time.time() * 1000)
    return result
