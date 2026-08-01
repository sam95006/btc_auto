"""Bounded 12H V3 session controller — separate from 6H; phrase/founder gated."""
from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.v2_bounded_engine import new_12h_session_id
from backend.nexus_demo_execution.v3_policy import POLICY_VERSION, SESSION_DURATION_SEC, SESSION_GATE_NAME
from backend.nexus_demo_execution.v3_start_gate import evaluate_12h_machine_gate

_TRUE = {"1", "true", "yes", "on"}


@dataclass
class Bounded12HSession:
    """Minimal 12H controller shell: start/status/stop + leader uniqueness."""

    export_dir: Path
    data_root: Path
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    session_id: str = ""
    source_6h_session_id: str = ""
    _state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.export_dir = Path(self.export_dir)
        self.data_root = Path(self.data_root)
        self._state = {
            "status": "IDLE",
            "session_id": "",
            "source_6h_session_id": "",
            "policy_version": POLICY_VERSION,
            "thread_alive": False,
            "smoke_write_window_open": False,
            "session_write_enabled": False,
            "entries_total": 0,
            "automatic_extension": False,
            "deadline_ts": None,
            "started_at": None,
            "ended_at": None,
            "recommendation": "",
        }

    def start(self, *, source_6h_report: dict[str, Any], nonce: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive() and self._state.get("status") in {"RUNNING", "STARTING"}:
                return {
                    "ok": False,
                    "reason": "IDEMPOTENT_DUPLICATE_START_BLOCKED",
                    "session_id": self.session_id,
                    "status": self._state.get("status"),
                }
            gate_env = (os.environ.get("FOUNDER_GATE") or "").strip()
            if gate_env != SESSION_GATE_NAME:
                return {"ok": False, "reason": "FOUNDER_GATE_MISMATCH", "expected": SESSION_GATE_NAME, "got": gate_env}
            if (os.environ.get("FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3") or "").strip().lower() not in _TRUE:
                return {"ok": False, "reason": "FOUNDER_12H_NOT_APPROVED"}
            if (os.environ.get("MAINNET") or "").strip().lower() in _TRUE:
                return {"ok": False, "reason": "MAINNET_FORBIDDEN"}
            if (os.environ.get("REAL_MONEY") or "").strip().lower() in _TRUE:
                return {"ok": False, "reason": "REAL_MONEY_FORBIDDEN"}

            report = dict(source_6h_report or {})
            nonce = nonce or uuid.uuid4().hex[:8]
            proposed = new_12h_session_id(nonce)
            report["proposed_12h_session_id"] = proposed
            gate = evaluate_12h_machine_gate(report)
            if not gate.get("machine_gate_pass"):
                return {"ok": False, "reason": "MACHINE_GATE_BLOCKED", "machine_gate": gate}

            self.session_id = proposed
            self.source_6h_session_id = str(report.get("session_id") or "")
            now = time.time()
            self._stop.clear()
            self._state.update(
                {
                    "status": "STARTING",
                    "session_id": self.session_id,
                    "source_6h_session_id": self.source_6h_session_id,
                    "started_at": now,
                    "deadline_ts": now + SESSION_DURATION_SEC,
                    "smoke_write_window_open": False,  # opened only after flat preflight in full runner
                    "session_write_enabled": False,
                    "recommendation": "",
                    "machine_gate": gate,
                }
            )
            self._thread = threading.Thread(target=self._run_placeholder, name="bounded-12h-v3", daemon=True)
            self._thread.start()
            return redact_secrets(
                {
                    "ok": True,
                    "session_id": self.session_id,
                    "status": "STARTING",
                    "source_6h_session_id": self.source_6h_session_id,
                    "policy_version": POLICY_VERSION,
                    "note": "controller_armed_write_window_closed_until_preflight",
                }
            )

    def stop(self, reason: str = "OPERATOR_STOP") -> dict[str, Any]:
        self._stop.set()
        with self._lock:
            self._state["status"] = "KILLED" if reason else "COMPLETED"
            self._state["ended_at"] = time.time()
            self._state["smoke_write_window_open"] = False
            self._state["session_write_enabled"] = False
            self._state["stop_reason"] = reason
        return {"ok": True, "status": self._state["status"]}

    def status(self) -> dict[str, Any]:
        with self._lock:
            snap = dict(self._state)
            snap["thread_alive"] = bool(self._thread and self._thread.is_alive())
            if snap.get("deadline_ts"):
                snap["remaining_seconds"] = max(0, int(snap["deadline_ts"] - time.time()))
            snap["found"] = bool(snap.get("session_id"))
        return redact_secrets(snap)

    def _run_placeholder(self) -> None:
        """Placeholder loop: enforces deadline without opening write window until full runner lands."""
        with self._lock:
            self._state["status"] = "RUNNING"
        deadline = float(self._state.get("deadline_ts") or (time.time() + SESSION_DURATION_SEC))
        while not self._stop.is_set() and time.time() < deadline:
            time.sleep(5)
        with self._lock:
            self._state["smoke_write_window_open"] = False
            self._state["session_write_enabled"] = False
            self._state["status"] = "COMPLETED" if not self._stop.is_set() else self._state.get("status") or "KILLED"
            self._state["ended_at"] = time.time()
            self._state["recommendation"] = "DEMO_AUTONOMOUS_12H_V3_CONTROLLER_PLACEHOLDER_NO_WRITE"
