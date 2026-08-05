"""Resume ownership boundary — local Coordinator alone owns real resume.

Provider Completion Ops may observe, pause/resume *ops scheduling*, and
surface Retry-After / capacity signals. It must never steal real Provider
resume ownership or invoke real calibration resume paths.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from backend.nexus_provider_ops.constants import (
    OPS_ROLE,
    REAL_RESUME_OWNER,
    SCHEMA_BOUNDARY,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Symbols / call names that would constitute ownership theft if invoked by ops.
FORBIDDEN_REAL_RESUME_CALLS: frozenset[str] = frozenset(
    {
        "resume_v23",
        "run_quota_aware_calibration",
        "allow_real_resume=True",
        "real_provider_resume",
    }
)


class ResumeOwnershipError(RuntimeError):
    """Raised when ops attempts to own or execute real Provider resume."""


class ResumeBoundary:
    """Guard that keeps real resume ownership with local Coordinator."""

    def __init__(self) -> None:
        self._attempted_real_resume = False
        self._blocked_attempts: list[dict[str, Any]] = []

    @property
    def owner(self) -> str:
        return REAL_RESUME_OWNER

    @property
    def ops_role(self) -> str:
        return OPS_ROLE

    def request_real_resume(self, *, reason: str = "") -> dict[str, Any]:
        """Ops may *request* but never *execute* real resume."""
        self._attempted_real_resume = True
        record = {
            "action": "request_real_resume",
            "allowed": False,
            "blocked_reason": "OPS_NOT_REAL_RESUME_OWNER",
            "owner": REAL_RESUME_OWNER,
            "ops_role": OPS_ROLE,
            "reason": reason,
            "at": _utc(),
        }
        self._blocked_attempts.append(record)
        return record

    def execute_real_resume(self, fn: Callable[..., Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
        """Hard-ban: refuse any real resume execution from ops."""
        self._attempted_real_resume = True
        record = {
            "action": "execute_real_resume",
            "allowed": False,
            "blocked_reason": "REAL_RESUME_OWNERSHIP_THEFT_BANNED",
            "owner": REAL_RESUME_OWNER,
            "callable_invoked": False,
            "fn_name": getattr(fn, "__name__", None),
            "at": _utc(),
        }
        self._blocked_attempts.append(record)
        raise ResumeOwnershipError(
            "local Coordinator remains the only owner of real Provider resume; "
            "Provider Completion Ops must not execute real resume"
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_BOUNDARY,
            "created_at": _utc(),
            "real_resume_owner": REAL_RESUME_OWNER,
            "ops_role": OPS_ROLE,
            "ops_owns_real_resume": False,
            "real_resume_executed_by_ops": False,
            "attempted_real_resume": self._attempted_real_resume,
            "blocked_attempt_count": len(self._blocked_attempts),
            "blocked_attempts": list(self._blocked_attempts),
            "forbidden_real_resume_calls": sorted(FORBIDDEN_REAL_RESUME_CALLS),
        }
