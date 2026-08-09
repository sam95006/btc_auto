"""Max-3-step paid-beta onboarding: Market State / Live Radar / Watchlist+Alerts."""
from __future__ import annotations

import threading
from typing import Any, Optional

from backend.nexus_paid_beta_retention.constants import ONBOARDING_STEPS


class OnboardingStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._progress: dict[str, dict[str, Any]] = {}

    def status(self, account_id: str) -> dict[str, Any]:
        with self._lock:
            cur = self._progress.get(account_id) or {
                "completed_step_ids": [],
                "dismissed": False,
            }
            done = set(cur.get("completed_step_ids") or [])
            steps = []
            for step in ONBOARDING_STEPS:
                steps.append({**step, "done": step["id"] in done})
            return {
                "max_steps": 3,
                "steps": steps,
                "dismissed": bool(cur.get("dismissed")),
                "complete": len(done) >= 3 or bool(cur.get("dismissed")),
                "authority": "SERVER",
            }

    def complete_step(self, account_id: str, step_id: str) -> dict[str, Any]:
        valid = {s["id"] for s in ONBOARDING_STEPS}
        if step_id not in valid:
            raise ValueError("invalid_step")
        with self._lock:
            cur = self._progress.setdefault(
                account_id, {"completed_step_ids": [], "dismissed": False}
            )
            ids = list(cur.get("completed_step_ids") or [])
            if step_id not in ids:
                ids.append(step_id)
            cur["completed_step_ids"] = ids
            return self.status(account_id)

    def dismiss(self, account_id: str) -> dict[str, Any]:
        with self._lock:
            cur = self._progress.setdefault(
                account_id, {"completed_step_ids": [], "dismissed": False}
            )
            cur["dismissed"] = True
            return self.status(account_id)


_STORE: Optional[OnboardingStore] = None
_LOCK = threading.Lock()


def get_onboarding_store() -> OnboardingStore:
    global _STORE
    with _LOCK:
        if _STORE is None:
            _STORE = OnboardingStore()
        return _STORE
