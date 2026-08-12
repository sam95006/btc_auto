"""Manual pause / resume for Provider ops scheduling (not real resume ownership)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_provider_ops.constants import PROVIDER_LANES, SCHEMA_MANUAL


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ManualLaneControl:
    """Per-lane manual pause/resume for ops scheduling only."""

    def __init__(self) -> None:
        self._paused: dict[str, bool] = {pid: False for pid in PROVIDER_LANES}
        self._history: list[dict[str, Any]] = []

    def pause(self, profile_id: str, *, reason: str = "founder_manual_pause") -> dict[str, Any]:
        if profile_id not in self._paused:
            raise KeyError(f"unknown_provider_lane:{profile_id}")
        self._paused[profile_id] = True
        event = {
            "action": "pause",
            "profile_id": profile_id,
            "reason": reason,
            "at": _utc(),
            "affects_real_resume_ownership": False,
        }
        self._history.append(event)
        return event

    def resume(self, profile_id: str, *, reason: str = "founder_manual_resume") -> dict[str, Any]:
        """Resume *ops scheduling* for a lane — does not execute real Provider resume."""
        if profile_id not in self._paused:
            raise KeyError(f"unknown_provider_lane:{profile_id}")
        self._paused[profile_id] = False
        event = {
            "action": "resume_ops_scheduling",
            "profile_id": profile_id,
            "reason": reason,
            "at": _utc(),
            "affects_real_resume_ownership": False,
            "real_resume_executed": False,
            "note": "Manual resume clears ops pause only; local Coordinator owns real resume.",
        }
        self._history.append(event)
        return event

    def pause_all(self, *, reason: str = "founder_manual_pause_all") -> list[dict[str, Any]]:
        return [self.pause(pid, reason=reason) for pid in PROVIDER_LANES]

    def resume_all(self, *, reason: str = "founder_manual_resume_all") -> list[dict[str, Any]]:
        return [self.resume(pid, reason=reason) for pid in PROVIDER_LANES]

    def is_paused(self, profile_id: str) -> bool:
        return bool(self._paused.get(profile_id))

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_MANUAL,
            "created_at": _utc(),
            "lanes": {
                GROQ_REFLECTION_REASONER: {
                    "paused": self.is_paused(GROQ_REFLECTION_REASONER),
                },
                SAMBANOVA_INDEPENDENT_CRITIC: {
                    "paused": self.is_paused(SAMBANOVA_INDEPENDENT_CRITIC),
                },
            },
            "any_paused": any(self._paused.values()),
            "history": list(self._history),
            "real_resume_executed": False,
            "ops_owns_real_resume": False,
        }
