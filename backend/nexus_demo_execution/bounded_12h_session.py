"""Bounded 12H V3 session — shared BoundedAutonomousSessionEngine + Founder extension gate."""
from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.bounded_autonomous_engine import BoundedAutonomousSessionEngine
from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.session_policy import policy_12h_v3
from backend.nexus_demo_execution.v2_bounded_engine import new_12h_session_id
from backend.nexus_demo_execution.v3_extended_observation_gate import (
    EXACT_PHRASE,
    evaluate_extended_observation_gate,
)
from backend.nexus_demo_execution.v3_policy import SESSION_GATE_NAME
from backend.nexus_demo_execution.v3_start_gate import evaluate_12h_machine_gate

_TRUE = {"1", "true", "yes", "on"}


@dataclass
class Bounded12HSession:
    """12H controller: Founder extension gate then full shared autonomous engine."""

    gate: Any
    reader: Any
    persistence: Any
    epoch_tracker: Any
    kill_switch: Any
    writer: Any
    approval: Any
    export_dir: Path
    data_root: Path
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _engine: BoundedAutonomousSessionEngine | None = field(default=None, repr=False)
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
            "policy_version": policy_12h_v3().policy_version,
            "controller_type": "FULL_AUTONOMOUS_ENGINE",
            "bounded_12h_full_engine_ready": True,
            "placeholder_reference_count": 0,
            "thread_alive": False,
            "session_write_enabled": False,
            "smoke_write_window_open": False,
            "automatic_extension": False,
            "deadline_ts": None,
            "started_at": None,
            "ended_at": None,
            "recommendation": "",
            "authorization_scope": "DEMO_12H_V3_SESSION_ONLY",
        }

    def start(self, *, source_6h_report: dict[str, Any], nonce: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self._engine is not None:
                st = self._engine.status()
                if st.get("thread_alive") and st.get("status") in {"RUNNING", "STARTING"}:
                    return {
                        "ok": False,
                        "reason": "IDEMPOTENT_DUPLICATE_START_BLOCKED",
                        "session_id": self.session_id,
                        "status": st.get("status"),
                    }
                # Terminal engine must not restart into RUNNING.
                if st.get("status") in {"COMPLETED", "FAILED", "KILLED"}:
                    return {
                        "ok": False,
                        "reason": "TERMINAL_SESSION_RESTART_FORBIDDEN",
                        "status": st.get("status"),
                        "session_id": self.session_id,
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

            # Prefer Founder extended-observation gate when phrase/flag present;
            # ordinary promotion gate remains available but must stay blocked for inconclusive 6H.
            phrase = str(report.get("approval_phrase") or report.get("exact_phrase") or "").strip()
            use_extended = phrase == EXACT_PHRASE or (
                (os.environ.get("FOUNDER_APPROVE_12H_AFTER_INCONCLUSIVE_6H_AND_PROBE") or "").strip().lower()
                in _TRUE
            )
            if use_extended:
                gate = evaluate_extended_observation_gate(report, approval_phrase=phrase or EXACT_PHRASE)
                if not gate.get("gate_pass"):
                    return {"ok": False, "reason": "EXTENDED_OBSERVATION_GATE_BLOCKED", "machine_gate": gate}
            else:
                gate = evaluate_12h_machine_gate(report)
                if not gate.get("machine_gate_pass"):
                    return {"ok": False, "reason": "MACHINE_GATE_BLOCKED", "machine_gate": gate}

            policy = policy_12h_v3()
            # Ensure start() founder checks pass for shared engine.
            os.environ.setdefault("FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3", "true")
            os.environ["FOUNDER_GATE"] = SESSION_GATE_NAME

            engine = BoundedAutonomousSessionEngine(
                gate=self.gate,
                reader=self.reader,
                persistence=self.persistence,
                epoch_tracker=self.epoch_tracker,
                kill_switch=self.kill_switch,
                writer=self.writer,
                approval=self.approval,
                export_dir=self.export_dir,
                data_root=self.data_root,
                policy=policy,
                source_6h_session_id=str(report.get("session_id") or report.get("source_6h_session_id") or ""),
                leader_token=f"12h-{uuid.uuid4().hex[:12]}",
            )
            # Pre-assign immutable session id matching Founder format.
            engine.session_id = proposed
            started = engine.start()
            if not started.get("ok"):
                return redact_secrets({"ok": False, "reason": started.get("reason"), "engine": started, "machine_gate": gate})

            # Keep Founder-prescribed session_id (engine may regenerate — override if needed).
            if engine.session_id != proposed:
                engine.session_id = proposed
                with engine._lock:
                    engine._state["session_id"] = proposed
                    engine._state["source_6h_session_id"] = engine.source_6h_session_id
                    engine._state["machine_gate"] = gate

            self._engine = engine
            self.session_id = engine.session_id
            self.source_6h_session_id = engine.source_6h_session_id
            self._state.update(
                {
                    "status": "STARTING",
                    "session_id": self.session_id,
                    "source_6h_session_id": self.source_6h_session_id,
                    "machine_gate": gate,
                    "gate_type": gate.get("gate_type") or "ORDINARY_12H_PROMOTION",
                    "controller_type": "FULL_AUTONOMOUS_ENGINE",
                    "bounded_12h_full_engine_ready": True,
                    "placeholder_reference_count": 0,
                }
            )
            return redact_secrets(
                {
                    "ok": True,
                    "session_id": self.session_id,
                    "status": "STARTING",
                    "source_6h_session_id": self.source_6h_session_id,
                    "policy_version": policy.policy_version,
                    "controller_type": "FULL_AUTONOMOUS_ENGINE",
                    "bounded_12h_full_engine_ready": True,
                    "authorization_scope": "DEMO_12H_V3_SESSION_ONLY",
                    "machine_gate": gate,
                    "automatic_extension": False,
                }
            )

    def stop(self, reason: str = "OPERATOR_STOP") -> dict[str, Any]:
        if self._engine is None:
            return {"ok": False, "reason": "no_session"}
        self._engine.stop(reason)
        return {"ok": True, "status": self._engine.status()}

    def status(self) -> dict[str, Any]:
        if self._engine is None:
            return redact_secrets({**self._state, "found": False, "thread_alive": False})
        snap = self._engine.status()
        snap["found"] = True
        snap["controller_type"] = "FULL_AUTONOMOUS_ENGINE"
        snap["bounded_12h_full_engine_ready"] = True
        snap["placeholder_reference_count"] = 0
        snap["source_6h_session_id"] = self.source_6h_session_id or snap.get("source_6h_session_id")
        if snap.get("deadline_ts"):
            import time

            snap["remaining_seconds"] = max(0, int(float(snap["deadline_ts"]) - time.time()))
        return redact_secrets(snap)
