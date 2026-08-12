"""Public-safe projection writer — allow-list only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_live_shadow_runtime.constants import (
    PROJECTION_ALLOW_FIELDS,
    PROJECTION_DENY_FIELDS,
)
from backend.nexus_live_shadow_runtime.state_machine import utc_now


class ProjectionError(RuntimeError):
    """Fail-closed projection violation."""


def filter_public_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only allow-listed fields; hard-refuse deny-list keys."""
    for key in payload:
        if key in PROJECTION_DENY_FIELDS or any(
            banned in str(key).lower() for banned in ("secret", "api_key", "private_key", "wallet")
        ):
            raise ProjectionError(f"denied_field:{key}")
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in PROJECTION_ALLOW_FIELDS:
            out[key] = value
    # Public invariants always stamped.
    out["actual_ordered"] = False
    out["actual_filled"] = False
    out["exchange_order_id"] = None
    return out


class PublicSafeProjectionWriter:
    """Append-only JSONL public projection under RUNTIME_ROOT."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.write_count = 0

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe = filter_public_safe(payload)
        if "emitted_at" not in safe:
            safe["emitted_at"] = utc_now()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(safe, ensure_ascii=False, default=str) + "\n")
        self.write_count += 1
        return safe
