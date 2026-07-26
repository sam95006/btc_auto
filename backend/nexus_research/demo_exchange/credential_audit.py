"""Phase 6.6.1 — DemoCredentialPresenceAudit + BootContinuity + Fingerprint.

Hard rules:
- Presence: PRESENT / MISSING for BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET
- Fingerprint: hmac-sha256(key + secret, app_salt), truncated to 8 hex — NEVER log raw key
- Boot continuity: boot_id, deployment_commit, credential_present, fingerprint, probe_enabled, timestamp
- No secret values in any output
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_exchange.constants import (
    ENV_API_KEY,
    ENV_API_SECRET,
    FINGERPRINT_LEN,
)

_APP_SALT = b"nexus-demo-credential-audit-v1"
_BOOT_ID: str = ""


def _get_boot_id() -> str:
    global _BOOT_ID
    if not _BOOT_ID:
        _BOOT_ID = uuid.uuid4().hex[:12]
    return _BOOT_ID


def credential_fingerprint(key: str, secret: str, *, length: int = FINGERPRINT_LEN) -> str:
    """Irreversible HMAC-SHA256 fingerprint of key+secret with fixed app salt.

    Returns empty string when either value is empty.
    Truncated to ``length`` hex chars (default 8).
    """
    if not key or not secret:
        return ""
    n = max(6, min(8, int(length)))
    payload = f"{key}:{secret}".encode("utf-8")
    digest = hmac.new(_APP_SALT, payload, hashlib.sha256).hexdigest()
    return digest[:n]


@dataclass(frozen=True)
class CredentialPresenceStatus:
    key_status: str   # "PRESENT" | "MISSING"
    secret_status: str  # "PRESENT" | "MISSING"

    @property
    def both_present(self) -> bool:
        return self.key_status == "PRESENT" and self.secret_status == "PRESENT"


def check_credential_presence(
    environ: dict[str, str] | None = None,
) -> CredentialPresenceStatus:
    """Check BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET presence only."""
    src = environ if environ is not None else os.environ
    key_val = (src.get(ENV_API_KEY) or "").strip()
    secret_val = (src.get(ENV_API_SECRET) or "").strip()
    return CredentialPresenceStatus(
        key_status="PRESENT" if key_val else "MISSING",
        secret_status="PRESENT" if secret_val else "MISSING",
    )


def build_credential_fingerprint(
    environ: dict[str, str] | None = None,
) -> str:
    """Build irreversible fingerprint from env credentials.  Empty if missing."""
    src = environ if environ is not None else os.environ
    key = (src.get(ENV_API_KEY) or "").strip()
    secret = (src.get(ENV_API_SECRET) or "").strip()
    return credential_fingerprint(key, secret)


def _probe_enabled_flag() -> bool:
    raw = os.environ.get("DEMO_READONLY_PROBE_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes")


@dataclass(frozen=True)
class BootContinuityRecord:
    """Boot continuity — no secret values, fingerprint only."""
    boot_id: str
    deployment_commit: str
    credential_present: bool
    fingerprint: str
    probe_enabled: bool
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "boot_id": self.boot_id,
            "deployment_commit": self.deployment_commit,
            "credential_present": self.credential_present,
            "fingerprint": self.fingerprint,
            "probe_enabled": self.probe_enabled,
            "timestamp_ms": self.timestamp_ms,
            "secret_safe": True,
        }


def build_boot_continuity(
    environ: dict[str, str] | None = None,
) -> BootContinuityRecord:
    """Build a boot continuity record.  Never includes secret values."""
    src = environ if environ is not None else os.environ
    presence = check_credential_presence(src)
    fp = build_credential_fingerprint(src)
    commit = (src.get("DEPLOYMENT_COMMIT") or src.get("GIT_COMMIT") or "").strip()
    return BootContinuityRecord(
        boot_id=_get_boot_id(),
        deployment_commit=commit,
        credential_present=presence.both_present,
        fingerprint=fp,
        probe_enabled=_probe_enabled_flag(),
        timestamp_ms=int(time.time() * 1000),
    )


@dataclass
class DemoCredentialPresenceAudit:
    """Full audit record combining presence, fingerprint, and boot continuity."""
    presence: CredentialPresenceStatus
    fingerprint: str
    boot_continuity: BootContinuityRecord
    checked_at_ms: int = 0

    @classmethod
    def build(
        cls,
        environ: dict[str, str] | None = None,
    ) -> "DemoCredentialPresenceAudit":
        src = environ if environ is not None else os.environ
        presence = check_credential_presence(src)
        fp = build_credential_fingerprint(src)
        boot = build_boot_continuity(src)
        return cls(
            presence=presence,
            fingerprint=fp,
            boot_continuity=boot,
            checked_at_ms=int(time.time() * 1000),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_status": self.presence.key_status,
            "secret_status": self.presence.secret_status,
            "credential_present": self.presence.both_present,
            "fingerprint": self.fingerprint,
            "boot_continuity": self.boot_continuity.to_dict(),
            "checked_at_ms": self.checked_at_ms,
            "secret_safe": True,
        }
