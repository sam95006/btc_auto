"""Component health for single-service consolidation (UI failure must not stop supervisor)."""
from __future__ import annotations

import os
import time
from typing import Any

_STATE: dict[str, Any] = {
    "web_health": "UNKNOWN",
    "market_worker_health": "UNKNOWN",
    "execution_worker_health": "UNKNOWN",
    "position_supervisor_health": "UNKNOWN",
    "learning_worker_health": "UNKNOWN",
    "persistence_health": "UNKNOWN",
    "updated_at": None,
}


def set_component(name: str, status: str) -> None:
    if name in _STATE:
        _STATE[name] = status
        _STATE["updated_at"] = time.time()


def snapshot() -> dict[str, Any]:
    single = (os.environ.get("NEXUS_SINGLE_SERVICE") or "").strip().lower() in {"1", "true", "yes", "on"}
    exec_bad = _STATE.get("execution_worker_health") in {"UNHEALTHY", "DOWN", "ERROR"}
    pos_bad = _STATE.get("position_supervisor_health") in {"UNHEALTHY", "DOWN", "ERROR"}
    persist_bad = _STATE.get("persistence_health") in {"UNHEALTHY", "DOWN", "ERROR"}
    new_entry_blocked = bool(exec_bad or pos_bad or persist_bad)
    return {
        "single_service": single,
        "one_service": single,
        "one_execution_owner": True,
        "stage3_dependency_required": not single,
        "external_control_plane_dependency_required": not single,
        "components": {k: v for k, v in _STATE.items() if k.endswith("_health") or k == "updated_at"},
        "new_entry_blocked": new_entry_blocked,
        "exchange_write": False,
        "mainnet": False,
        "real_money": False,
    }
