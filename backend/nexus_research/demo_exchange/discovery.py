"""Phase 6.6.1 — Credential Discovery (no network calls, no secret values).

Statuses:
- CREDENTIAL_DETECTED_PROBE_DISABLED: expected env present, probe flag off
- BLOCKED_CREDENTIALS_MISSING: expected env names absent
- BLOCKED_CREDENTIAL_NAME_MISMATCH: alternate historical names present but expected missing

Hard rules:
- NEVER call Bybit on startup or discovery
- NEVER log/print/return secret values
- Only check os.environ key existence and non-emptiness
- DEMO_READONLY_PROBE_ENABLED default = false (unset = false)
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_exchange.constants import (
    ENV_API_KEY,
    ENV_API_SECRET,
    WRITE_ALLOWED,
)

DEMO_READONLY_PROBE_ENABLED_ENV = "DEMO_READONLY_PROBE_ENABLED"

ALTERNATE_KEY_NAMES = (
    "BYBIT_M0_API_KEY",
    "BYBIT_API_KEY",
    "NEXUS_BYBIT_API_KEY",
)
ALTERNATE_SECRET_NAMES = (
    "BYBIT_M0_API_SECRET",
    "BYBIT_API_SECRET",
    "NEXUS_BYBIT_API_SECRET",
)


def _probe_enabled() -> bool:
    raw = os.environ.get(DEMO_READONLY_PROBE_ENABLED_ENV, "").strip().lower()
    return raw in ("1", "true", "yes")


def _env_present(name: str, environ: dict[str, str] | None = None) -> bool:
    src = environ if environ is not None else os.environ
    val = src.get(name, "")
    return bool(val and val.strip())


class DiscoveryStatus:
    CREDENTIAL_DETECTED_PROBE_DISABLED = "CREDENTIAL_DETECTED_PROBE_DISABLED"
    BLOCKED_CREDENTIALS_MISSING = "BLOCKED_CREDENTIALS_MISSING"
    BLOCKED_CREDENTIAL_NAME_MISMATCH = "BLOCKED_CREDENTIAL_NAME_MISMATCH"


@dataclass(frozen=True)
class CredentialDiscoveryResult:
    """Immutable result of credential discovery — no secret values."""
    status: str
    probe_enabled: bool
    key_present: bool
    secret_present: bool
    alternate_key_detected: bool
    alternate_secret_detected: bool
    private_api_call_count: int = 0
    write_impossible: bool = True
    execution_write_allowed: bool = False
    network_calls: int = 0
    checked_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "probe_enabled": self.probe_enabled,
            "key_present": self.key_present,
            "secret_present": self.secret_present,
            "alternate_key_detected": self.alternate_key_detected,
            "alternate_secret_detected": self.alternate_secret_detected,
            "private_api_call_count": self.private_api_call_count,
            "write_impossible": self.write_impossible,
            "execution_write_allowed": self.execution_write_allowed,
            "network_calls": self.network_calls,
            "checked_at_ms": self.checked_at_ms,
        }


def discover_credentials(
    environ: dict[str, str] | None = None,
) -> CredentialDiscoveryResult:
    """Run credential discovery. Zero network calls. Never reads secret values."""
    probe_on = _probe_enabled()
    key_present = _env_present(ENV_API_KEY, environ)
    secret_present = _env_present(ENV_API_SECRET, environ)
    expected_configured = key_present and secret_present

    alt_key = any(_env_present(n, environ) for n in ALTERNATE_KEY_NAMES)
    alt_secret = any(_env_present(n, environ) for n in ALTERNATE_SECRET_NAMES)

    if expected_configured:
        status = DiscoveryStatus.CREDENTIAL_DETECTED_PROBE_DISABLED
    elif (alt_key or alt_secret) and not expected_configured:
        status = DiscoveryStatus.BLOCKED_CREDENTIAL_NAME_MISMATCH
    else:
        status = DiscoveryStatus.BLOCKED_CREDENTIALS_MISSING

    return CredentialDiscoveryResult(
        status=status,
        probe_enabled=probe_on,
        key_present=key_present,
        secret_present=secret_present,
        alternate_key_detected=alt_key,
        alternate_secret_detected=alt_secret,
        private_api_call_count=0,
        write_impossible=not WRITE_ALLOWED,
        execution_write_allowed=False,
        network_calls=0,
        checked_at_ms=int(time.time() * 1000),
    )


@dataclass
class DemoReadinessReport:
    """Full readiness report for the /api/nexus/demo/readiness endpoint."""
    discovery: CredentialDiscoveryResult | None = None
    probe_enabled: bool = False
    private_api_call_count: int = 0
    write_impossible: bool = True
    execution_write_allowed: bool = False
    phase: str = "6.6.1"
    errors: list[str] = field(default_factory=list)

    @classmethod
    def build(cls, environ: dict[str, str] | None = None) -> "DemoReadinessReport":
        discovery = discover_credentials(environ)
        return cls(
            discovery=discovery,
            probe_enabled=discovery.probe_enabled,
            private_api_call_count=0,
            write_impossible=True,
            execution_write_allowed=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.discovery.status if self.discovery else "UNKNOWN",
            "probe_enabled": self.probe_enabled,
            "private_api_call_count": self.private_api_call_count,
            "write_impossible": self.write_impossible,
            "execution_write_allowed": self.execution_write_allowed,
            "discovery": self.discovery.to_dict() if self.discovery else None,
            "errors": self.errors,
        }
