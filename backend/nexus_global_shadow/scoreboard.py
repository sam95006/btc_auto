"""Global Market Shadow operational scoreboard (no fleet_health)."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow.contracts import now_ms

CAPABILITY_STATES = frozenset(
    {"NOT_STARTED", "IN_PROGRESS", "IMPLEMENTED", "TESTED", "EVIDENCE_VERIFIED", "BLOCKED"}
)


class GlobalMarketShadowScoreboard:
    """Operational scoreboard for wave2 shadow pipeline."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {
            "universe_worker_health": "DISABLED",
            "market_worker_health": "DISABLED",
            "review_worker_health": "DISABLED",
            "portfolio_worker_health": "DISABLED",
            "lifecycle_worker_health": "DISABLED",
            "replay_worker_health": "DISABLED",
            "data_freshness": "UNKNOWN",
            "markets_scanned": 0,
            "markets_eligible": 0,
            "markets_excluded": 0,
            "candidate_count": 0,
            "six_role_review_count": 0,
            "risk_critic_pass_count": 0,
            "risk_critic_block_count": 0,
            "portfolio_selected_count": 0,
            "open_shadow_positions": 0,
            "pending_shadow_intents": 0,
            "closed_shadow_positions": 0,
            "outcomes_complete": 0,
            "reflections_complete": 0,
            "learning_patches": 0,
            "replay_runs": 0,
            "walk_forward_folds": 0,
            "oos_runs": 0,
            "evidence_integrity": "UNKNOWN",
            "test_status": "NOT_STARTED",
            "last_updated_at": now_ms(),
            "capabilities": {},
        }

    def update_funnel(
        self,
        *,
        scanned: int = 0,
        eligible: int = 0,
        excluded: int = 0,
        candidates: int = 0,
        reviewed: int = 0,
        risk_pass: int = 0,
        risk_block: int = 0,
        selected: int = 0,
    ) -> None:
        self._data["markets_scanned"] = scanned
        self._data["markets_eligible"] = eligible
        self._data["markets_excluded"] = excluded
        self._data["candidate_count"] = candidates
        self._data["six_role_review_count"] = reviewed
        self._data["risk_critic_pass_count"] = risk_pass
        self._data["risk_critic_block_count"] = risk_block
        self._data["portfolio_selected_count"] = selected
        self._data["last_updated_at"] = now_ms()

    def set_capability(self, name: str, state: str) -> None:
        if state not in CAPABILITY_STATES:
            state = "IN_PROGRESS"
        caps = self._data.setdefault("capabilities", {})
        caps[name] = state

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def assert_no_fleet_health(self) -> bool:
        return "fleet_health" not in self._data
