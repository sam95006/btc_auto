"""Persist exit policy chosen at order time (for future trades; do not retrofit live open trade)."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_EXIT_HIERARCHY = (
    "HARD_STOP",
    "TAKE_PROFIT",
    "STRATEGY_INVALIDATION",
    "SIGNAL_REVERSAL",
    "TIME_STOP",
    "SYSTEM_HEALTH_EMERGENCY",
    "MANUAL_KILL_SWITCH",
)


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
    protective_stop_plan: dict[str, Any] = field(default_factory=dict)
    take_profit_plan: dict[str, Any] = field(default_factory=dict)
    persisted: bool = False

    def is_complete(self) -> bool:
        return bool(
            self.symbol
            and self.side
            and self.strategy
            and self.max_hold_ms > 0
            and self.time_stop_enabled
            and self.invalidation_rule
            and self.exit_hierarchy
            and self.protective_stop_plan
            and self.take_profit_plan
            and self.persisted
        )

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
            "protectiveStopPlan": dict(self.protective_stop_plan),
            "takeProfitPlan": dict(self.take_profit_plan),
            "persisted": self.persisted,
            "exitPolicyPersisted": self.is_complete(),
        }


def _path() -> Path | None:
    try:
        from backend.nexus_research.boot_identity import research_data_dir

        root = research_data_dir()
        if root is not None:
            return root / "exit_policy_records.jsonl"
    except Exception:
        pass
    # Ephemeral fallback so the hard gate can still persist within a process
    # when NEXUS_DATA_DIR is not configured (unit tests / local dry-run).
    import tempfile

    return Path(tempfile.gettempdir()) / "nexus_demo_exit_policy_records.jsonl"


_LOCK = threading.Lock()
_MEMORY: list[ExitPolicyRecord] = []


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
    protective_stop_plan: dict[str, Any] | None = None,
    take_profit_plan: dict[str, Any] | None = None,
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
        protective_stop_plan=dict(protective_stop_plan or {}),
        take_profit_plan=dict(take_profit_plan or {}),
        persisted=False,
    )
    path = _path()
    with _LOCK:
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                # Mark persisted before serialize so the on-disk row is authoritative.
                rec.persisted = True
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
            except Exception:
                rec.persisted = False
        _MEMORY.append(rec)
    return rec


def latest_exit_policy(symbol: str) -> ExitPolicyRecord | None:
    sym = str(symbol or "").upper()
    if not sym:
        return None
    with _LOCK:
        for rec in reversed(_MEMORY):
            if rec.symbol.upper() == sym:
                return rec
        path = _path()
        if path is None or not path.exists():
            return None
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return None
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except Exception:
                continue
            if str(raw.get("symbol") or "").upper() != sym:
                continue
            return ExitPolicyRecord(
                symbol=str(raw.get("symbol") or ""),
                side=str(raw.get("side") or ""),
                strategy=str(raw.get("strategy") or ""),
                signal_id=str(raw.get("signalId") or ""),
                max_hold_ms=int(raw.get("maxHoldMs") or 0),
                time_stop_enabled=bool(raw.get("timeStopEnabled")),
                invalidation_rule=str(raw.get("invalidationRule") or ""),
                exit_hierarchy=tuple(raw.get("exitHierarchy") or DEFAULT_EXIT_HIERARCHY),
                created_at_ms=int(raw.get("createdAtMs") or 0),
                order_link_id=str(raw.get("orderLinkId") or ""),
                protective_stop_plan=dict(raw.get("protectiveStopPlan") or {}),
                take_profit_plan=dict(raw.get("takeProfitPlan") or {}),
                persisted=bool(raw.get("persisted", True)),
            )
    return None
