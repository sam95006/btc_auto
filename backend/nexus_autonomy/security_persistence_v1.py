"""Persistence security — ledger/snapshot/evidence fail-closed guards."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from backend.nexus_autonomy.security_constants_v1 import SECRET_PATTERNS
from backend.nexus_autonomy.security_exceptions_v1 import PersistenceSecurityError


def assert_safe_relative_path(path: str | Path, *, root: Path) -> Path:
    """Reject path traversal, absolute escapes, and symlink escapes outside root."""
    root = root.resolve()
    raw = str(path)
    if "\x00" in raw:
        raise PersistenceSecurityError("nul_in_path")
    # Explicit traversal tokens
    posix = PurePosixPath(raw.replace("\\", "/"))
    if ".." in posix.parts:
        raise PersistenceSecurityError("path_traversal")
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PersistenceSecurityError("path_escape") from exc
    if candidate.is_symlink():
        target = candidate.resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise PersistenceSecurityError("symlink_escape") from exc
    return candidate


def scan_secrets_in_evidence(payload: Any) -> list[str]:
    """Return list of secret-pattern finding codes (values never echoed)."""
    blob = json.dumps(payload, default=str)
    lowered = blob.lower()
    findings: list[str] = []
    for pat in SECRET_PATTERNS:
        if pat in lowered:
            findings.append(f"pattern:{pat.strip()}")
    # High-entropy-looking assignments (python / env style)
    assignment_hit = bool(
        re.search(r"(api[_-]?key|api[_-]?secret|token)\s*[:=]\s*['\"][^'\"]{16,}", blob, re.I)
    )
    # JSON quoted-key assignments: "api_key": "...." (R4 secret_scan_json_assignment_blind_spot)
    json_assignment_hit = bool(
        re.search(
            r'"(api[_-]?key|api[_-]?secret|token)"\s*:\s*"[^"]{16,}"',
            blob,
            re.I,
        )
    )
    if assignment_hit or json_assignment_hit:
        findings.append("credential_assignment")
    if "begin private key" in lowered:
        findings.append("private_key_pem")
    return findings


def fail_closed_json_loads(text: str) -> Any:
    """Deserialize JSON fail-closed: reject non-object roots for ledger events."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PersistenceSecurityError("corrupt_json") from exc
    if data is None or isinstance(data, (int, float, bool, str)):
        raise PersistenceSecurityError("untrusted_scalar_root")
    return data


def assert_ledger_event_safe(event: dict[str, Any]) -> None:
    if not isinstance(event, dict):
        raise PersistenceSecurityError("event_not_object")
    findings = scan_secrets_in_evidence(event)
    if findings:
        raise PersistenceSecurityError(f"secret_in_ledger:{findings[0]}")
    # Reject raw provider material
    for banned in ("raw_provider_prompt", "raw_provider_response", "api_secret", "api_key"):
        if banned in event:
            raise PersistenceSecurityError(f"banned_field:{banned}")
        payload = event.get("payload")
        if isinstance(payload, dict) and banned in payload:
            raise PersistenceSecurityError(f"banned_payload_field:{banned}")


def assert_schema_migration_trusted(declared: str, allowed: set[str]) -> None:
    if declared not in allowed:
        raise PersistenceSecurityError(f"untrusted_schema_migration:{declared}")


def run_persistence_security_self_test(tmp_root: Path | None = None) -> dict[str, Any]:
    root = tmp_root or Path(".")
    root = root.resolve()
    traversal_blocked = False
    try:
        assert_safe_relative_path("../etc/passwd", root=root)
    except PersistenceSecurityError:
        traversal_blocked = True

    corrupt_blocked = False
    try:
        fail_closed_json_loads("{not json")
    except PersistenceSecurityError:
        corrupt_blocked = True

    secret_blocked = False
    try:
        assert_ledger_event_safe({"type": "X", "api_secret": "supersecretvalue123"})
    except PersistenceSecurityError:
        secret_blocked = True

    migration_blocked = False
    try:
        assert_schema_migration_trusted("evil_drop_all", {"private_event_ledger_v1"})
    except PersistenceSecurityError:
        migration_blocked = True

    provider_blocked = False
    try:
        assert_ledger_event_safe({"type": "P", "payload": {"raw_provider_prompt": "sk-abc"}})
    except PersistenceSecurityError:
        provider_blocked = True

    passed = all(
        [traversal_blocked, corrupt_blocked, secret_blocked, migration_blocked, provider_blocked]
    )
    return {
        "persistence_security_test_count": 5,
        "path_traversal_blocked": traversal_blocked,
        "corrupt_json_blocked": corrupt_blocked,
        "secret_in_ledger_blocked": secret_blocked,
        "untrusted_migration_blocked": migration_blocked,
        "provider_raw_blocked": provider_blocked,
        "passed": passed,
        "secret_leak_count": 0 if secret_blocked and provider_blocked else 1,
    }
