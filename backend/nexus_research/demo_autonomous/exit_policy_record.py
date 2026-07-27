"""Persist exit policy chosen at order time (for future trades; do not retrofit live open trade)."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ExitPolicyRecord:
    symbol: str
    side: str
    strategy: str
    signal_id: str
    max_hold_ms: int
    time_stop_enabled: bool
    invalidation_rule: str
    exit_hierarchy: tuple[str, ...]
    created_at_ms: int
    order_link_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "strategy": self.strategy,
            "signalId": self.signal_id,
            "maxHoldMs": self.max_hold_ms,
            "timeStopEnabled": self.time_stop_enabled,
            "invalidationRule": self.invalidation_rule,
            "exitHierarchy": list(self.exit_hierarchy),
            "createdAtMs": self.created_at_ms,
            "orderLinkId": self.order_link_id,
        }


DEFAULT_EXIT_HIERARCHY = (
    "HARD_STOP",
    "TAKE_PROFIT",
    "STRATEGY_INVALIDATION",
    "SIGNAL_REVERSAL",
    "TIME_STOP",
    "SYSTEM_HEALTH_EMERGENCY",
    "MANUAL_KILL_SWITCH",
)


def _path() -> Path | None:
    try:
        from backend.nexus_research.boot_identity import research_data_dir

        root = research_data_dir()
        if root is None:
            return None
        return root / "exit_policy_records.jsonl"
    except Exception:
        return None


_LOCK = threading.Lock()


def record_exit_policy(
    *,
    symbol: str,
    side: str,
    strategy: str,
    signal_id: str = "",
    max_hold_ms: int = 6 * 60 * 60 * 1000,
    time_stop_enabled: bool = True,
    invalidation_rule: str = "regime_or_signal_invalidation",
    order_link_id: str = "",
) -> ExitPolicyRecord:
    rec = ExitPolicyRecord(
        symbol=symbol,
        side=side,
        strategy=strategy,
        signal_id=signal_id,
        max_hold_ms=max_hold_ms,
        time_stop_enabled=time_stop_enabled,
        invalidation_rule=invalidation_rule,
        exit_hierarchy=DEFAULT_EXIT_HIERARCHY,
        created_at_ms=int(time.time() * 1000),
        order_link_id=order_link_id,
    )
    path = _path()
    with _LOCK:
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
            except Exception:
                pass
    return rec
