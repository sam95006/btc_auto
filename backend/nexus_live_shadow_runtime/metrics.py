"""Runtime metrics — real integers only (Founder §4.3). Never fabricate LIVE success."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


METRIC_KEYS: tuple[str, ...] = (
    "runtime_cycles_completed",
    "runtime_cycles_failed",
    "source_read_success_count",
    "source_read_failure_count",
    "live_records_ingested",
    "records_quarantined",
    "duplicate_records",
    "unresolved_duplicates",
    "universe_refresh_count",
    "total_contracts_seen",
    "eligible_contracts_latest",
    "observe_only_contracts_latest",
    "blocked_contracts_latest",
    "candidates_generated",
    "LONG_count",
    "SHORT_count",
    "WAIT_count",
    "ABSTAIN_count",
    "BLOCK_count",
    "shadow_opened_count",
    "shadow_closed_count",
    "actual_ordered_count",
    "actual_filled_count",
    "AI_requests",
    "AI_success",
    "AI_timeout",
    "AI_invalid_json",
    "deterministic_fallback_count",
    "provider_capacity_blocked_count",
    "busy_loop_count",
    "exchange_write_attempt_count",
    "mainnet_client_count",
    "demo_order_count",
    "runtime_restart_count",
)


@dataclass
class RuntimeMetrics:
    """Acceptance / evidence counters. actual_ordered/filled/busy_loop MUST stay 0."""

    runtime_cycles_completed: int = 0
    runtime_cycles_failed: int = 0
    source_read_success_count: int = 0
    source_read_failure_count: int = 0
    live_records_ingested: int = 0
    records_quarantined: int = 0
    duplicate_records: int = 0
    unresolved_duplicates: int = 0
    universe_refresh_count: int = 0
    total_contracts_seen: int = 0
    eligible_contracts_latest: int = 0
    observe_only_contracts_latest: int = 0
    blocked_contracts_latest: int = 0
    candidates_generated: int = 0
    LONG_count: int = 0
    SHORT_count: int = 0
    WAIT_count: int = 0
    ABSTAIN_count: int = 0
    BLOCK_count: int = 0
    shadow_opened_count: int = 0
    shadow_closed_count: int = 0
    actual_ordered_count: int = 0
    actual_filled_count: int = 0
    AI_requests: int = 0
    AI_success: int = 0
    AI_timeout: int = 0
    AI_invalid_json: int = 0
    deterministic_fallback_count: int = 0
    provider_capacity_blocked_count: int = 0
    busy_loop_count: int = 0
    exchange_write_attempt_count: int = 0
    mainnet_client_count: int = 0
    demo_order_count: int = 0
    runtime_restart_count: int = 0
    real_money: bool = False
    active_lesson_count: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def bump(self, key: str, n: int = 1) -> None:
        with self._lock:
            if not hasattr(self, key):
                raise KeyError(f"unknown_metric:{key}")
            if key in {"actual_ordered_count", "actual_filled_count", "busy_loop_count"}:
                if n != 0:
                    raise RuntimeError(f"forbidden_metric_bump:{key}")
                return
            setattr(self, key, int(getattr(self, key)) + int(n))

    def set_latest_universe(
        self,
        *,
        total: int,
        eligible: int,
        observe_only: int,
        blocked: int,
    ) -> None:
        with self._lock:
            self.total_contracts_seen = int(total)
            self.eligible_contracts_latest = int(eligible)
            self.observe_only_contracts_latest = int(observe_only)
            self.blocked_contracts_latest = int(blocked)

    def record_decision(self, side: str) -> None:
        side_u = str(side or "").upper()
        mapping = {
            "LONG": "LONG_count",
            "SHORT": "SHORT_count",
            "WAIT": "WAIT_count",
            "ABSTAIN": "ABSTAIN_count",
            "BLOCK": "BLOCK_count",
        }
        key = mapping.get(side_u, "ABSTAIN_count")
        self.bump(key)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            out: dict[str, Any] = {}
            for key in METRIC_KEYS:
                out[key] = int(getattr(self, key))
            out["real_money"] = False
            out["active_lesson_count"] = int(self.active_lesson_count)
            out["actual_ordered_count"] = 0
            out["actual_filled_count"] = 0
            out["busy_loop_count"] = 0
            return out

    def assert_safety_invariants(self) -> None:
        d = self.to_dict()
        assert d["actual_ordered_count"] == 0
        assert d["actual_filled_count"] == 0
        assert d["busy_loop_count"] == 0
        assert d["exchange_write_attempt_count"] == 0
        assert d["mainnet_client_count"] == 0
        assert d["demo_order_count"] == 0
        assert d["real_money"] is False
