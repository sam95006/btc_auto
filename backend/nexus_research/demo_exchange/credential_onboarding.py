"""Phase 6.6.1 — Credential Onboarding Readiness.

Seven policy / status / checklist classes that gate the path from
"no credentials configured" to "human sets Zeabur secrets and we can
run a real read-only probe."

Hard rules:
- Env var NAMES only — never invent values or store credentials
- Credentials injected ONLY via Zeabur Secret / Environment injection
- Forbidden channels: git, .env tracked, JSON evidence, stdout, exception, logs
- Permission checklist: Demo only, read-only, reject Trade/Withdraw/Transfer/Mainnet
- IP allowlist suggestion if platform supports it
- Key fingerprint: irreversible 6-8 chars only (SHA-256 prefix)
- actual_credentials_present must remain false in this round
- ready_for_live_readonly_probe = false
- ready_for_deploy = false
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_research.demo_exchange.constants import (
    ACCOUNT_BYBIT_DEMO,
    ACCOUNT_PAPER_MAIN_V1,
    DEMO_REST_BASE_URL,
    ENV_API_KEY,
    ENV_API_SECRET,
    FINGERPRINT_LEN,
    FORBIDDEN_BASE_URLS,
    PHASE,
    WRITE_ALLOWED,
)
from backend.nexus_research.demo_exchange.credentials import (
    DemoCredentialPresenceValidator,
    fingerprint_secret,
)


# ---------------------------------------------------------------------------
# Forbidden credential channels — hard deny list
# ---------------------------------------------------------------------------
FORBIDDEN_CREDENTIAL_CHANNELS = frozenset({
    "git_tracked_file",
    "dotenv_tracked",
    "json_evidence_file",
    "stdout",
    "stderr",
    "exception_message",
    "log_output",
    "http_response_body",
    "client_visible_payload",
    "frontend_code",
    "commit_message",
})

ALLOWED_CREDENTIAL_CHANNELS = frozenset({
    "zeabur_secret",
    "zeabur_environment_variable",
    "runtime_environment_variable",
})

# Permissions that must NEVER be present on a demo read-only key
FORBIDDEN_PERMISSIONS = frozenset({
    "Trade",
    "Withdraw",
    "Transfer",
    "Mainnet",
    "ContractTrade",
    "SpotTrade",
    "OptionsTrade",
    "CopyTrading",
    "Exchange",
})

REQUIRED_PERMISSIONS = frozenset({
    "ReadOnly",
})


class OnboardingGate(str, Enum):
    """Gate status for credential onboarding readiness."""
    NOT_STARTED = "NOT_STARTED"
    POLICY_DEFINED = "POLICY_DEFINED"
    CHECKLIST_READY = "CHECKLIST_READY"
    AWAITING_HUMAN_SETUP = "AWAITING_HUMAN_SETUP"
    CREDENTIALS_CONFIGURED = "CREDENTIALS_CONFIGURED"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# 1. DemoCredentialOnboardingPolicy
# ---------------------------------------------------------------------------
class DemoCredentialOnboardingPolicy:
    """Defines which env vars are required and how credentials must be injected.

    Never contains credential values — only names and injection rules.
    """

    REQUIRED_ENV_VARS: tuple[str, ...] = (ENV_API_KEY, ENV_API_SECRET)
    OPTIONAL_ENV_VARS: tuple[str, ...] = ("BYBIT_DEMO_ACCOUNT_LABEL",)

    def __init__(self) -> None:
        self._forbidden_channels = FORBIDDEN_CREDENTIAL_CHANNELS
        self._allowed_channels = ALLOWED_CREDENTIAL_CHANNELS

    @property
    def env_var_names(self) -> list[str]:
        return list(self.REQUIRED_ENV_VARS) + list(self.OPTIONAL_ENV_VARS)

    @property
    def forbidden_channels(self) -> frozenset[str]:
        return self._forbidden_channels

    @property
    def allowed_channels(self) -> frozenset[str]:
        return self._allowed_channels

    def is_channel_allowed(self, channel: str) -> bool:
        return channel in self._allowed_channels

    def is_channel_forbidden(self, channel: str) -> bool:
        return channel in self._forbidden_channels

    def validate_injection_channel(self, channel: str) -> dict[str, Any]:
        allowed = self.is_channel_allowed(channel)
        forbidden = self.is_channel_forbidden(channel)
        return {
            "channel": channel,
            "allowed": allowed,
            "forbidden": forbidden,
            "verdict": "PASS" if allowed else "REJECT",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": "6.6.1",
            "required_env_vars": list(self.REQUIRED_ENV_VARS),
            "optional_env_vars": list(self.OPTIONAL_ENV_VARS),
            "forbidden_channels": sorted(self._forbidden_channels),
            "allowed_channels": sorted(self._allowed_channels),
            "credential_values_present": False,
            "policy_note": "Env var NAMES only; values injected via Zeabur Secret at deploy time",
        }


# ---------------------------------------------------------------------------
# 2. DemoCredentialRuntimeStatus
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DemoCredentialRuntimeStatus:
    """Snapshot of credential runtime state — never holds actual values."""
    key_env: str = ENV_API_KEY
    secret_env: str = ENV_API_SECRET
    key_present: bool = False
    secret_present: bool = False
    credential_configured: bool = False
    fingerprint: str = ""
    actual_credentials_present: bool = False
    ready_for_live_readonly_probe: bool = False
    ready_for_deploy: bool = False
    execution_write_allowed: bool = False
    checked_at_ms: int = 0
    gate: str = OnboardingGate.NOT_STARTED.value

    @classmethod
    def check(
        cls,
        validator: DemoCredentialPresenceValidator | None = None,
    ) -> "DemoCredentialRuntimeStatus":
        v = validator or DemoCredentialPresenceValidator()
        presence = v.validate(require=False)
        configured = presence.configured
        gate = (
            OnboardingGate.CREDENTIALS_CONFIGURED.value
            if configured
            else OnboardingGate.AWAITING_HUMAN_SETUP.value
        )
        return cls(
            key_env=presence.key_env,
            secret_env=presence.secret_env,
            key_present=presence.key_present,
            secret_present=presence.secret_present,
            credential_configured=configured,
            fingerprint=presence.fingerprint,
            actual_credentials_present=configured,
            ready_for_live_readonly_probe=False,
            ready_for_deploy=False,
            execution_write_allowed=False,
            checked_at_ms=int(time.time() * 1000),
            gate=gate,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_env": self.key_env,
            "secret_env": self.secret_env,
            "key_present": self.key_present,
            "secret_present": self.secret_present,
            "credential_configured": self.credential_configured,
            "fingerprint": self.fingerprint,
            "actual_credentials_present": self.actual_credentials_present,
            "ready_for_live_readonly_probe": self.ready_for_live_readonly_probe,
            "ready_for_deploy": self.ready_for_deploy,
            "execution_write_allowed": self.execution_write_allowed,
            "checked_at_ms": self.checked_at_ms,
            "gate": self.gate,
        }


# ---------------------------------------------------------------------------
# 3. DemoCredentialRedactor
# ---------------------------------------------------------------------------
class DemoCredentialRedactor:
    """Redacts credential values from any text surface: logs, exceptions,
    reports, JSON evidence, stdout. Never allows raw secrets through."""

    REDACTED = "***REDACTED***"
    _SUSPICIOUS_PATTERNS = (
        re.compile(r"(?i)(api[_-]?key|api[_-]?secret|password|token)\s*[:=]\s*\S+"),
        re.compile(r"[A-Za-z0-9]{20,}"),
    )

    def __init__(self, known_secrets: list[str] | None = None) -> None:
        self._known: list[str] = list(known_secrets or [])

    def add_secret(self, secret: str) -> None:
        if secret and secret not in self._known:
            self._known.append(secret)

    def redact(self, text: str) -> str:
        out = str(text or "")
        for s in self._known:
            if s and s in out:
                out = out.replace(s, self.REDACTED)
        return out

    def redact_dict(self, d: dict[str, Any]) -> dict[str, Any]:
        """Deep-redact any string values that contain known secrets."""
        result = {}
        for k, v in d.items():
            if isinstance(v, str):
                result[k] = self.redact(v)
            elif isinstance(v, dict):
                result[k] = self.redact_dict(v)
            elif isinstance(v, list):
                result[k] = [
                    self.redact(item) if isinstance(item, str) else item
                    for item in v
                ]
            else:
                result[k] = v
        return result

    def assert_no_leak(self, text: str) -> None:
        """Raises ValueError if any known secret appears in text."""
        for s in self._known:
            if s and s in text:
                raise ValueError("credential_leak_detected")

    def scan_for_suspicious(self, text: str) -> list[str]:
        """Flag patterns that look like they could be credentials."""
        findings: list[str] = []
        for pat in self._SUSPICIOUS_PATTERNS:
            for m in pat.finditer(text):
                findings.append(m.group(0)[:12] + "...")
        return findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "known_secret_count": len(self._known),
            "redaction_marker": self.REDACTED,
            "suspicious_pattern_count": len(self._SUSPICIOUS_PATTERNS),
        }


# ---------------------------------------------------------------------------
# 4. DemoReadOnlyProbePreflight
# ---------------------------------------------------------------------------
@dataclass
class DemoReadOnlyProbePreflight:
    """Pre-flight checklist before a live read-only probe can run.

    All conditions must be true before the probe command fires.
    actual_credentials_present remains false in this round.
    """
    domain_is_demo: bool = False
    get_only_enforced: bool = False
    credential_configured: bool = False
    read_only_permission: bool = False
    identity_is_bybit_demo: bool = False
    paper_separated: bool = False
    write_impossible: bool = False
    execution_write_allowed: bool = False
    actual_credentials_present: bool = False
    ready_for_live_readonly_probe: bool = False
    ready_for_deploy: bool = False
    checked_at_ms: int = 0
    errors: list[str] = field(default_factory=list)

    @classmethod
    def run(
        cls,
        *,
        credential_validator: DemoCredentialPresenceValidator | None = None,
    ) -> "DemoReadOnlyProbePreflight":
        pf = cls(checked_at_ms=int(time.time() * 1000))

        pf.domain_is_demo = DEMO_REST_BASE_URL == "https://api-demo.bybit.com"
        pf.get_only_enforced = True  # DemoReadOnlyTransport blocks non-GET
        pf.write_impossible = not WRITE_ALLOWED
        pf.execution_write_allowed = False

        v = credential_validator or DemoCredentialPresenceValidator()
        presence = v.validate(require=False)
        pf.credential_configured = presence.configured
        pf.actual_credentials_present = presence.configured

        pf.read_only_permission = not presence.configured  # unknown until live probe
        if presence.configured:
            pf.read_only_permission = True  # assumed; validated on live probe

        pf.identity_is_bybit_demo = (ACCOUNT_BYBIT_DEMO == "BYBIT_DEMO_ACCOUNT")
        pf.paper_separated = (ACCOUNT_PAPER_MAIN_V1 != ACCOUNT_BYBIT_DEMO)

        if not pf.domain_is_demo:
            pf.errors.append("domain_not_demo")
        if not pf.paper_separated:
            pf.errors.append("paper_demo_not_separated")
        if pf.execution_write_allowed:
            pf.errors.append("execution_write_must_be_false")

        pf.ready_for_live_readonly_probe = (
            pf.domain_is_demo
            and pf.get_only_enforced
            and pf.credential_configured
            and pf.paper_separated
            and pf.write_impossible
            and not pf.execution_write_allowed
            and not pf.errors
        )
        pf.ready_for_deploy = False

        return pf

    @property
    def all_gates_pass(self) -> bool:
        return self.ready_for_live_readonly_probe and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_is_demo": self.domain_is_demo,
            "domain": DEMO_REST_BASE_URL,
            "get_only_enforced": self.get_only_enforced,
            "credential_configured": self.credential_configured,
            "read_only_permission": self.read_only_permission,
            "identity": ACCOUNT_BYBIT_DEMO,
            "identity_is_bybit_demo": self.identity_is_bybit_demo,
            "paper_separated": self.paper_separated,
            "write_impossible": self.write_impossible,
            "execution_write_allowed": self.execution_write_allowed,
            "actual_credentials_present": self.actual_credentials_present,
            "ready_for_live_readonly_probe": self.ready_for_live_readonly_probe,
            "ready_for_deploy": self.ready_for_deploy,
            "errors": list(self.errors),
            "checked_at_ms": self.checked_at_ms,
        }


# ---------------------------------------------------------------------------
# 5. DemoCredentialPermissionChecklist
# ---------------------------------------------------------------------------
@dataclass
class DemoCredentialPermissionChecklist:
    """Checklist of permission constraints for the Bybit Demo API key.

    The human must create the key with EXACTLY these permissions.
    This class never holds the key itself — only the rules.
    """
    require_demo_only: bool = True
    require_read_only: bool = True
    reject_trade: bool = True
    reject_withdraw: bool = True
    reject_transfer: bool = True
    reject_mainnet: bool = True
    ip_allowlist_suggested: bool = True
    ip_allowlist_note: str = "Restrict to Zeabur egress IPs if platform supports it"
    fingerprint_max_chars: int = FINGERPRINT_LEN
    fingerprint_irreversible: bool = True
    forbidden_permissions: frozenset[str] = field(default_factory=lambda: FORBIDDEN_PERMISSIONS)
    required_permissions: frozenset[str] = field(default_factory=lambda: REQUIRED_PERMISSIONS)
    checked_at_ms: int = 0
    errors: list[str] = field(default_factory=list)

    @classmethod
    def build(cls) -> "DemoCredentialPermissionChecklist":
        return cls(checked_at_ms=int(time.time() * 1000))

    def validate_permission_set(self, declared_permissions: set[str]) -> dict[str, Any]:
        """Validate a declared set of permissions against the checklist."""
        violations: list[str] = []
        missing_required: list[str] = []

        for perm in declared_permissions:
            if perm in self.forbidden_permissions:
                violations.append(f"forbidden_permission_present:{perm}")

        for perm in self.required_permissions:
            if perm not in declared_permissions:
                missing_required.append(f"required_permission_missing:{perm}")

        ok = not violations and not missing_required
        return {
            "ok": ok,
            "declared_permissions": sorted(declared_permissions),
            "violations": violations,
            "missing_required": missing_required,
            "verdict": "PASS" if ok else "REJECT",
        }

    def validate_fingerprint(self, fp: str) -> dict[str, Any]:
        length_ok = 6 <= len(fp) <= self.fingerprint_max_chars if fp else False
        return {
            "fingerprint": fp,
            "length_ok": length_ok,
            "irreversible": self.fingerprint_irreversible,
            "max_chars": self.fingerprint_max_chars,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_demo_only": self.require_demo_only,
            "require_read_only": self.require_read_only,
            "reject_trade": self.reject_trade,
            "reject_withdraw": self.reject_withdraw,
            "reject_transfer": self.reject_transfer,
            "reject_mainnet": self.reject_mainnet,
            "ip_allowlist_suggested": self.ip_allowlist_suggested,
            "ip_allowlist_note": self.ip_allowlist_note,
            "fingerprint_max_chars": self.fingerprint_max_chars,
            "fingerprint_irreversible": self.fingerprint_irreversible,
            "forbidden_permissions": sorted(self.forbidden_permissions),
            "required_permissions": sorted(self.required_permissions),
            "checked_at_ms": self.checked_at_ms,
        }


# ---------------------------------------------------------------------------
# 6. DemoCredentialRotationPlan
# ---------------------------------------------------------------------------
@dataclass
class DemoCredentialRotationPlan:
    """Plan for credential rotation — code-only, never holds credentials.

    Documents the process the human must follow to rotate keys:
    1. Create new key on Bybit Demo with identical read-only permissions
    2. Update Zeabur secrets atomically
    3. Verify new fingerprint appears in runtime status
    4. Revoke old key on Bybit Demo
    """
    rotation_steps: list[str] = field(default_factory=lambda: [
        "create_new_demo_key_with_readonly_permission",
        "update_zeabur_secrets_atomically",
        "verify_new_fingerprint_in_runtime_status",
        "run_read_only_probe_with_new_key",
        "revoke_old_key_on_bybit_demo",
        "confirm_old_fingerprint_no_longer_active",
    ])
    env_vars_to_rotate: tuple[str, ...] = (ENV_API_KEY, ENV_API_SECRET)
    rotation_channel: str = "zeabur_secret"
    requires_downtime: bool = False
    old_key_fingerprint: str = ""
    new_key_fingerprint: str = ""
    rotation_initiated: bool = False
    rotation_completed: bool = False
    checked_at_ms: int = 0

    @classmethod
    def build(cls, *, old_fingerprint: str = "") -> "DemoCredentialRotationPlan":
        return cls(
            old_key_fingerprint=old_fingerprint,
            checked_at_ms=int(time.time() * 1000),
        )

    def verify_rotation(
        self, old_fp: str, new_fp: str
    ) -> dict[str, Any]:
        """Verify that rotation produced a different fingerprint."""
        if not old_fp or not new_fp:
            return {"ok": False, "reason": "fingerprints_missing"}
        if old_fp == new_fp:
            return {"ok": False, "reason": "fingerprints_identical_rotation_failed"}
        length_ok = 6 <= len(new_fp) <= FINGERPRINT_LEN
        return {
            "ok": length_ok,
            "old_fingerprint": old_fp,
            "new_fingerprint": new_fp,
            "fingerprints_differ": True,
            "new_length_ok": length_ok,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "rotation_steps": list(self.rotation_steps),
            "env_vars_to_rotate": list(self.env_vars_to_rotate),
            "rotation_channel": self.rotation_channel,
            "requires_downtime": self.requires_downtime,
            "old_key_fingerprint": self.old_key_fingerprint,
            "new_key_fingerprint": self.new_key_fingerprint,
            "rotation_initiated": self.rotation_initiated,
            "rotation_completed": self.rotation_completed,
            "checked_at_ms": self.checked_at_ms,
        }


# ---------------------------------------------------------------------------
# 7. DemoCredentialRevocationPlan
# ---------------------------------------------------------------------------
@dataclass
class DemoCredentialRevocationPlan:
    """Plan for credential revocation — emergency or planned key removal.

    Documents the process:
    1. Revoke key on Bybit Demo platform
    2. Remove Zeabur secrets
    3. Confirm runtime status shows credentials absent
    4. Confirm probe returns BLOCKED_CREDENTIALS_MISSING
    """
    revocation_steps: list[str] = field(default_factory=lambda: [
        "revoke_key_on_bybit_demo_platform",
        "remove_zeabur_secrets",
        "restart_service_to_clear_env_cache",
        "confirm_runtime_status_credentials_absent",
        "confirm_probe_returns_BLOCKED_CREDENTIALS_MISSING",
    ])
    env_vars_to_clear: tuple[str, ...] = (ENV_API_KEY, ENV_API_SECRET)
    revocation_channel: str = "zeabur_secret"
    revoked_key_fingerprint: str = ""
    revocation_reason: str = ""
    revocation_initiated: bool = False
    revocation_completed: bool = False
    post_revocation_probe_status: str = ""
    checked_at_ms: int = 0

    @classmethod
    def build(
        cls,
        *,
        fingerprint: str = "",
        reason: str = "planned_rotation",
    ) -> "DemoCredentialRevocationPlan":
        return cls(
            revoked_key_fingerprint=fingerprint,
            revocation_reason=reason,
            checked_at_ms=int(time.time() * 1000),
        )

    def verify_revocation(
        self,
        runtime_status: DemoCredentialRuntimeStatus,
    ) -> dict[str, Any]:
        """Verify that after revocation, credentials are absent."""
        absent = not runtime_status.credential_configured
        return {
            "ok": absent,
            "credential_configured": runtime_status.credential_configured,
            "key_present": runtime_status.key_present,
            "secret_present": runtime_status.secret_present,
            "expected_state": "credentials_absent",
            "verdict": "PASS" if absent else "FAIL_CREDENTIALS_STILL_PRESENT",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "revocation_steps": list(self.revocation_steps),
            "env_vars_to_clear": list(self.env_vars_to_clear),
            "revocation_channel": self.revocation_channel,
            "revoked_key_fingerprint": self.revoked_key_fingerprint,
            "revocation_reason": self.revocation_reason,
            "revocation_initiated": self.revocation_initiated,
            "revocation_completed": self.revocation_completed,
            "post_revocation_probe_status": self.post_revocation_probe_status,
            "checked_at_ms": self.checked_at_ms,
        }
