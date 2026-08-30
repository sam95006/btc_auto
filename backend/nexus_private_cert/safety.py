"""Demo-only safety gate for the read-only certifier (fail-closed)."""

from __future__ import annotations

import os
from typing import Any

# The certifier is allowed to touch external credentials ONLY when every one of
# these flags holds. Any mismatch is a hard SAFETY BLOCK.
REQUIRED_TRUE = ("BYBIT_DEMO",)
REQUIRED_FALSE = (
    "MAINNET",
    "REAL_MONEY",
    "EXCHANGE_WRITE",
    "DEMO_AUTONOMOUS_ENABLED",
    "AUTONOMOUS_SEND",
)


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def _is_false(value: str | None) -> bool:
    # A safety-critical FALSE flag must be EXPLICITLY false. An unset flag is a
    # violation (fail-closed) — it must never silently count as a certified
    # explicit false.
    return (value or "").strip().lower() in ("false", "0", "no")


def read_safety_flags(env: dict[str, str] | None = None) -> dict[str, str]:
    src = env if env is not None else os.environ
    keys = list(REQUIRED_TRUE) + list(REQUIRED_FALSE)
    return {k: (src.get(k, "") or "").strip().lower() or "unset" for k in keys}


def safety_gate(env: dict[str, str] | None = None) -> tuple[bool, dict[str, Any]]:
    """Return (ok, detail). ok is True only if the demo-only posture holds."""
    src = env if env is not None else os.environ
    violations: list[str] = []
    for k in REQUIRED_TRUE:
        if not _is_true(src.get(k)):
            violations.append(f"{k}!=true")
    for k in REQUIRED_FALSE:
        if not _is_false(src.get(k)):
            violations.append(f"{k}!=false")
    ok = not violations
    return ok, {
        "ok": ok,
        "flags": read_safety_flags(src),
        "violations": violations,
    }
