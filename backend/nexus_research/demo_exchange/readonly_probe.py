"""Phase 6.6.1 — GET-only Live Probe runner.

Activated ONLY when DEMO_READONLY_PROBE_ENABLED=true AND credentials present.

Hard rules:
- Domain hard-locked to api-demo.bybit.com
- Allowed GETs: server time, query-api, wallet-balance, position/list, order/realtime,
  order/history, execution/list, market instruments/tickers/kline (public)
- Permission: FAIL_CLOSED on Withdraw/Transfer/Exchange/Mainnet markers
- Trade-capable Demo keys are EXPECTED for a future controlled order path;
  they are recorded but do NOT enable writes (transport still GET-only)
- ZERO write methods
- On hard permission fail: FAIL_CLOSED, stop further private calls
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
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import (
    DemoExchangeError,
    PermissionDeniedError,
)
from backend.nexus_research.demo_exchange.factory import DemoPrivateClientFactory
from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

logger = logging.getLogger(__name__)

# Hard-fail permissions: discovery must stop. Never relax these.
HARD_FAIL_PERMISSIONS = frozenset({
    "Withdraw",
    "Transfer",
    "Exchange",
    "AccountTransfer",
    "SubMemberTransfer",
})

# Trade-capable markers: expected on Demo trading keys. Writes remain impossible.
TRADE_CAPABLE_PERMISSIONS = frozenset({
    "Trade",
    "Order",
    "Position",
    "ContractTrade",
    "SpotTrade",
    "OptionsTrade",
    "CopyTrading",
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
            "execution_write_allowed": False,
            "started_at_ms": self.started_at_ms,
            "finished_at_ms": self.finished_at_ms,
            "secret_safe": True,
        }


def _probe_enabled() -> bool:
    raw = os.environ.get("DEMO_READONLY_PROBE_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes")


def _check_permissions(result_data: dict[str, Any]) -> dict[str, Any]:
    """Classify API key permissions.

    Hard-fail (stop private probe): Withdraw / Transfer / Exchange.
    Trade-capable: recorded only — app-layer writes remain impossible.
    """
    permissions = result_data.get("permissions") or {}
    if isinstance(permissions, dict):
        all_perms: set[str] = set()
        for _category, perms in permissions.items():
            if isinstance(perms, list):
                all_perms.update(str(p) for p in perms)
            elif isinstance(perms, str):
                all_perms.add(perms)
            # Category keys themselves can be permission families
            all_perms.add(str(_category))
    elif isinstance(permissions, list):
        all_perms = {str(p) for p in permissions}
    else:
        all_perms = set()

    hard = all_perms & HARD_FAIL_PERMISSIONS
    trade = all_perms & TRADE_CAPABLE_PERMISSIONS
    return {
        "permissions_found": sorted(all_perms) if all_perms else [],
        "hard_violations": sorted(hard),
        "violations": sorted(hard),  # alias used by older tests / callers
        "trade_capable": bool(trade),
        "trade_permissions": sorted(trade),
        "read_only": (not hard) and (not trade),
        "fail_closed": bool(hard),
        "writes_still_impossible": True,
        "execution_write_allowed": False,
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

    # 1) Server time (public)
    try:
        resp = transport.request("GET", "/v5/market/time", {})
        result.network_calls += 1
        result.endpoints_probed.append("/v5/market/time")
        if int(resp.get("retCode", -1)) == 0:
            result.server_time_ok = True
        else:
            result.errors.append(f"/v5/market/time:retCode={resp.get('retCode')}")
    except DemoExchangeError as exc:
        result.errors.append(f"/v5/market/time:{type(exc).__name__}")
        result.network_calls += 1
    except Exception as exc:
        result.errors.append(f"/v5/market/time:{type(exc).__name__}")
        result.network_calls += 1

    # 2) API key permission info — hard-fail stops further private GETs
    try:
        resp = transport.request("GET", "/v5/user/query-api", {})
        result.network_calls += 1
        result.endpoints_probed.append("/v5/user/query-api")
        payload = resp.get("result") if isinstance(resp.get("result"), dict) else resp
        perm = _check_permissions(payload if isinstance(payload, dict) else {})
        result.permission_check = perm
        if perm.get("fail_closed"):
            result.fail_closed = True
            result.status = ProbeStatus.FAIL_CLOSED_PERMISSION
            result.errors.append("permission:hard_fail:" + ",".join(perm.get("hard_violations") or []))
            logger.warning("probe_fail_closed reason=hard_permission_violation")
            result.finished_at_ms = int(time.time() * 1000)
            return result
        if perm.get("trade_capable"):
            result.errors.append("permission:trade_capable_key_writes_still_impossible")
    except PermissionDeniedError:
        result.fail_closed = True
        result.status = ProbeStatus.FAIL_CLOSED_PERMISSION
        result.errors.append("/v5/user/query-api:permission_denied")
        result.finished_at_ms = int(time.time() * 1000)
        return result
    except DemoExchangeError as exc:
        # Permission endpoint unavailable — continue discovery but record
        result.errors.append(f"/v5/user/query-api:{type(exc).__name__}")
        result.network_calls += 1
    except Exception as exc:
        result.errors.append(f"/v5/user/query-api:{type(exc).__name__}")
        result.network_calls += 1

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
