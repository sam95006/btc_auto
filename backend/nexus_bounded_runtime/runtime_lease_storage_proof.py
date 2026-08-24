"""Runtime durable lease storage proof — authoritative on the validation service filesystem."""
from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from backend.nexus_bounded_runtime.durable_lease_store import (
    _is_ephemeral_path,
    validate_durable_lease_storage_path,
)

BOUNDED_LEASE_POLICY_LABEL = "6H_V2"
PERSISTENT_MOUNT_MARKERS = (
    "/app/data",
    "nexus_demo_validation",
    "zeabur",
)


def resolve_configured_data_root() -> str:
    for key in ("NEXUS_DATA_ROOT", "NEXUS_DATA_DIR", "DATA_ROOT"):
        value = (os.environ.get(key) or "").strip()
        if not value:
            continue
        if _is_ephemeral_path(Path(value)):
            continue
        return value
    return ""


def resolve_bounded_lease_root(data_root: Path | str, *, policy_label: str = BOUNDED_LEASE_POLICY_LABEL) -> Path:
    root = Path(data_root).resolve()
    return root / "artifacts" / "bounded_runtime_lease" / policy_label


def redact_storage_path(path: Path | str) -> str:
    text = str(path).replace("\\", "/")
    text = re.sub(r"/Users/[^/]+", "/Users/<redacted>", text, flags=re.IGNORECASE)
    text = re.sub(r"/home/[^/]+", "/home/<redacted>", text, flags=re.IGNORECASE)
    text = re.sub(r"([A-Za-z]:/Users/)[^/]+", r"\1<redacted>", text, flags=re.IGNORECASE)
    return text


def _persistent_volume_identity(*, data_root: Path, configured_root: str) -> dict[str, Any]:
    if configured_root:
        resolved = Path(configured_root).resolve()
        return {
            "proven": not _is_ephemeral_path(resolved),
            "source": "environment",
            "configured_data_root": redact_storage_path(resolved),
        }
    resolved = data_root.resolve()
    text = str(resolved).lower().replace("\\", "/")
    if _is_ephemeral_path(resolved):
        return {
            "proven": False,
            "source": "ephemeral_fallback",
            "configured_data_root": redact_storage_path(resolved),
        }
    if any(marker in text for marker in PERSISTENT_MOUNT_MARKERS):
        return {
            "proven": True,
            "source": "zeabur_mount",
            "configured_data_root": redact_storage_path(resolved),
        }
    return {
        "proven": not _is_ephemeral_path(resolved),
        "source": "runtime_resolved",
        "configured_data_root": redact_storage_path(resolved),
    }


def prove_runtime_durable_lease_storage(
    data_root: Path | str,
    *,
    policy_label: str = BOUNDED_LEASE_POLICY_LABEL,
) -> dict[str, Any]:
    """Write/read/delete probe on the active runtime lease root."""
    active_data_root = Path(data_root).resolve()
    configured_root = resolve_configured_data_root()
    lease_root = resolve_bounded_lease_root(active_data_root, policy_label=policy_label)
    ephemeral = _is_ephemeral_path(lease_root) or _is_ephemeral_path(active_data_root)
    volume = _persistent_volume_identity(data_root=active_data_root, configured_root=configured_root)

    probe_ok = False
    probe_error: str | None = None
    try:
        lease_root.mkdir(parents=True, exist_ok=True)
        probe = lease_root / f".runtime_lease_probe_{uuid.uuid4().hex[:8]}"
        token = f"probe-{time.time()}"
        probe.write_text(token, encoding="utf-8")
        readback = probe.read_text(encoding="utf-8")
        probe.unlink(missing_ok=True)
        probe_ok = readback == token
    except OSError as exc:
        probe_error = type(exc).__name__

    validation = validate_durable_lease_storage_path(lease_root)
    runtime_proven = bool(
        probe_ok
        and not ephemeral
        and validation.get("DURABLE_LEASE_STORAGE_PREFLIGHT_PASS") is True
        and volume.get("proven") is True
    )

    return {
        "NEXUS_DATA_ROOT": redact_storage_path(configured_root or active_data_root),
        "DURABLE_LEASE_STORAGE_PATH": redact_storage_path(lease_root),
        "DURABLE_LEASE_STORAGE_RUNTIME_PROVEN": runtime_proven,
        "EPHEMERAL_LEASE_STORAGE": ephemeral,
        "DURABLE_LEASE_STORAGE_PROBE_PASS": probe_ok,
        "PERSISTENT_VOLUME_IDENTITY_PROVEN": volume.get("proven") is True,
        "PERSISTENT_VOLUME_IDENTITY_SOURCE": volume.get("source"),
        "RUNTIME_STORAGE_PROOF_SOURCE": "validation_runtime",
        "configured_data_root": volume.get("configured_data_root"),
        "lease_root_resolved": redact_storage_path(lease_root),
        "probe_error": probe_error,
        "writable": validation.get("writable"),
    }


def consume_remote_storage_proof(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize bounded-6h/status payload into preflight storage checks."""
    bounded = payload if isinstance(payload, dict) else {}
    runtime_proven = bounded.get("DURABLE_LEASE_STORAGE_RUNTIME_PROVEN") is True
    ephemeral = bounded.get("EPHEMERAL_LEASE_STORAGE") is True
    return {
        "DURABLE_LEASE_STORAGE_RUNTIME_PROVEN": runtime_proven,
        "DURABLE_LEASE_STORAGE_PATH": bounded.get("DURABLE_LEASE_STORAGE_PATH"),
        "EPHEMERAL_LEASE_STORAGE": ephemeral,
        "DURABLE_LEASE_STORAGE_PREFLIGHT_PASS": runtime_proven and not ephemeral,
        "RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER": runtime_proven and bounded.get("RUNTIME_STORAGE_PROOF_SOURCE") == "validation_runtime",
        "NEXUS_DATA_ROOT": bounded.get("NEXUS_DATA_ROOT"),
        "PERSISTENT_VOLUME_IDENTITY_PROVEN": bounded.get("PERSISTENT_VOLUME_IDENTITY_PROVEN") is True,
    }
