"""Phase 6.6 — Credential presence + irreversible fingerprint (never log secrets)."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

from backend.nexus_research.demo_exchange.constants import (
    ENV_API_KEY,
    ENV_API_SECRET,
    FINGERPRINT_LEN,
)
from backend.nexus_research.demo_exchange.errors import CredentialMissingError


def fingerprint_secret(value: str, length: int = FINGERPRINT_LEN) -> str:
    """Irreversible fingerprint; max 6–8 hex chars. Empty → empty."""
    if not value:
        return ""
    n = max(6, min(8, int(length)))
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:n]


def _redact(value: str) -> str:
    """Never return raw secret; for exception/report safety."""
    return "***"


@dataclass(frozen=True)
class CredentialPresence:
    configured: bool
    key_present: bool
    secret_present: bool
    fingerprint: str  # of api key only; irreversible
    key_env: str = ENV_API_KEY
    secret_env: str = ENV_API_SECRET

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "credential_configured": self.configured,
            "key_present": self.key_present,
            "secret_present": self.secret_present,
            "credential_fingerprint": self.fingerprint,
            "key_env": self.key_env,
            "secret_env": self.secret_env,
        }


class DemoCredentialPresenceValidator:
    """Checks env presence only; never echoes key/secret values."""

    def __init__(
        self,
        key_env: str = ENV_API_KEY,
        secret_env: str = ENV_API_SECRET,
        environ: dict[str, str] | None = None,
    ) -> None:
        self.key_env = key_env
        self.secret_env = secret_env
        self._environ = environ if environ is not None else os.environ

    def _get(self, name: str) -> str:
        return str(self._environ.get(name) or "").strip()

    def validate(self, *, require: bool = False) -> CredentialPresence:
        key = self._get(self.key_env)
        secret = self._get(self.secret_env)
        key_ok = bool(key)
        secret_ok = bool(secret)
        configured = key_ok and secret_ok
        fp = fingerprint_secret(key) if key_ok else ""
        result = CredentialPresence(
            configured=configured,
            key_present=key_ok,
            secret_present=secret_ok,
            fingerprint=fp,
            key_env=self.key_env,
            secret_env=self.secret_env,
        )
        if require and not configured:
            raise CredentialMissingError("demo_credentials_missing")
        return result

    def load_secrets_for_signer(self) -> tuple[str, str]:
        """Return (key, secret) for in-memory signing only. Caller must not log."""
        presence = self.validate(require=True)
        key = self._get(self.key_env)
        secret = self._get(self.secret_env)
        # Defensive: never attach raw values to presence object
        _ = presence
        return key, secret

    @staticmethod
    def sanitize_message(msg: str, secrets: list[str]) -> str:
        out = str(msg or "")
        for s in secrets:
            if s and s in out:
                out = out.replace(s, _redact(s))
        return out
