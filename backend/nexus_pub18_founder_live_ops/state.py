"""In-memory Founder live-ops control plane state (process-local)."""
from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

_lock = threading.RLock()


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_STATE: dict[str, Any] = {
    "ingest_paused": False,
    "disabled_providers": [],
    "disabled_sources": [],
    "read_only_degraded": False,
    "emergency_read_only_stop": False,
    "audit_log": [],
    "updated_at": None,
}


def get_state() -> dict[str, Any]:
    with _lock:
        return deepcopy(_STATE)


def reset_state() -> None:
    with _lock:
        _STATE["ingest_paused"] = False
        _STATE["disabled_providers"] = []
        _STATE["disabled_sources"] = []
        _STATE["read_only_degraded"] = False
        _STATE["emergency_read_only_stop"] = False
        _STATE["audit_log"] = []
        _STATE["updated_at"] = _utc()


def _append_audit(action: str, detail: dict[str, Any] | None = None) -> None:
    entry = {"at": _utc(), "action": action, "detail": detail or {}}
    _STATE["audit_log"] = list(_STATE["audit_log"][-99:]) + [entry]
    _STATE["updated_at"] = entry["at"]


def set_ingest_paused(paused: bool) -> dict[str, Any]:
    with _lock:
        _STATE["ingest_paused"] = bool(paused)
        _append_audit("pause_ingest" if paused else "resume_ingest")
        return deepcopy(_STATE)


def disable_provider(provider_id: str) -> dict[str, Any]:
    with _lock:
        pid = str(provider_id or "").strip()
        if not pid:
            raise ValueError("provider_id_required")
        providers = list(_STATE["disabled_providers"])
        if pid not in providers:
            providers.append(pid)
        _STATE["disabled_providers"] = providers
        _append_audit("disable_provider", {"provider_id": pid})
        return deepcopy(_STATE)


def disable_source(source_id: str) -> dict[str, Any]:
    with _lock:
        sid = str(source_id or "").strip()
        if not sid:
            raise ValueError("source_id_required")
        sources = list(_STATE["disabled_sources"])
        if sid not in sources:
            sources.append(sid)
        _STATE["disabled_sources"] = sources
        _append_audit("disable_source", {"source_id": sid})
        return deepcopy(_STATE)


def force_read_only_degraded(enabled: bool = True) -> dict[str, Any]:
    with _lock:
        _STATE["read_only_degraded"] = bool(enabled)
        if enabled:
            _STATE["emergency_read_only_stop"] = True
            _STATE["ingest_paused"] = True
        _append_audit("force_read_only_degraded_mode", {"enabled": bool(enabled)})
        return deepcopy(_STATE)
