"""Founder-private control plane V10 — start/status/pause/resume/stop/recover/kill/checkpoint/health/observability.

Fail-closed. No exchange writes. No public product surface.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_private_control.checkpoint import CheckpointStore
from backend.nexus_private_control.health import build_health, build_observability
from backend.nexus_private_control.modes import ALLOWED_MODES, ModeRejectedError, mode_contract, validate_mode
from backend.nexus_private_control.state_machine import (
    ControlPlaneStateMachine,
    InvalidTransitionError,
)
from backend.nexus_private_control.write_guard import ExchangeWriteForbidden, NoExchangeWriteGuard

SCHEMA_ID = "NEXUS_PRIVATE_CONTROL_PLANE_V10"


class ControlPlaneError(RuntimeError):
    """Operational failure on the private control plane. Fail-closed."""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class PrivateControlPlaneV10:
    """In-process Founder control surface for private-core allowed modes only."""

    CONTROLS: tuple[str, ...] = (
        "start",
        "status",
        "pause",
        "resume",
        "stop",
        "recover",
        "kill_switch",
        "checkpoint",
        "health",
        "observability",
    )

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._sm = ControlPlaneStateMachine()
        self._guard = NoExchangeWriteGuard()
        self._checkpoints = CheckpointStore(self.root / "checkpoints")
        self._mode: str | None = None
        self._run_id: str | None = None
        self._kill_switch_engaged = False
        self._kill_switch_reason: str | None = None
        self._checkpoint_count = 0
        self._commands_invoked: list[str] = []
        self._started_at: str | None = None
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_command(self, name: str) -> None:
        self._commands_invoked.append(name)

    def _assert_not_killed(self, command: str) -> None:
        if self._kill_switch_engaged and command not in {
            "status",
            "health",
            "observability",
            "checkpoint",
            "kill_switch",
            "stop",
        }:
            raise ControlPlaneError(f"kill_switch_blocks:{command}")

    def _fail_safe(self, reason: str, *, command: str) -> dict[str, Any]:
        self._last_error = reason
        try:
            if self._sm.state not in {"FAILED_SAFE", "KILLED", "STOPPED"}:
                self._sm.transition("FAILED_SAFE", command=command, reason=reason)
        except InvalidTransitionError:
            pass
        return self._status_unlocked(record=False)

    def _snapshot_payload(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_ID,
            "run_id": self._run_id,
            "mode": self._mode,
            "state": self._sm.state,
            "kill_switch_engaged": self._kill_switch_engaged,
            "kill_switch_reason": self._kill_switch_reason,
            "exchange_write_attempt_count": self._guard.exchange_write_attempt_count,
            "checkpoint_count": self._checkpoint_count,
            "started_at": self._started_at,
            "last_error": self._last_error,
            "mode_contract": mode_contract(),
            "transition_history": self._sm.history(),
        }

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def start(self, mode: str, *, run_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._record_command("start")
            self._assert_not_killed("start")
            try:
                validated = validate_mode(mode)
            except ModeRejectedError as exc:
                self._last_error = str(exc)
                raise ControlPlaneError(f"start_rejected:{exc}") from exc
            if self._sm.state not in {"IDLE"}:
                raise ControlPlaneError(f"start_invalid_state:{self._sm.state}")
            try:
                self._sm.transition("STARTING", command="start", reason=f"mode={validated}")
                self._mode = validated
                self._run_id = run_id or f"pcp_{uuid.uuid4().hex[:12]}"
                self._started_at = _utc()
                self._sm.transition("RUNNING", command="start", reason="started")
                # Initial checkpoint after start.
                self._checkpoint_unlocked()
                return self._status_unlocked(record=False)
            except InvalidTransitionError as exc:
                return self._fail_safe(str(exc), command="start")

    def _status_unlocked(self, *, record: bool = True) -> dict[str, Any]:
        if record:
            self._record_command("status")
        return {
            "schema": SCHEMA_ID,
            "created_at": _utc(),
            "run_id": self._run_id,
            "mode": self._mode,
            "state": self._sm.state,
            "is_terminal": self._sm.is_terminal,
            "kill_switch_engaged": self._kill_switch_engaged,
            "kill_switch_reason": self._kill_switch_reason,
            "exchange_write_attempt_count": self._guard.exchange_write_attempt_count,
            "checkpoint_count": self._checkpoint_count,
            "started_at": self._started_at,
            "last_error": self._last_error,
            "allowed_modes": sorted(ALLOWED_MODES),
            "controls": list(self.CONTROLS),
            "founder_private": True,
            "public_api_exposed": False,
            "exchange_writes_permitted": False,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_unlocked(record=True)

    def _checkpoint_unlocked(self) -> dict[str, Any]:
        self._record_command("checkpoint")
        if not self._run_id:
            raise ControlPlaneError("checkpoint_requires_run")
        meta = self._checkpoints.save(self._run_id, self._snapshot_payload())
        self._checkpoint_count += 1
        return {
            "schema": SCHEMA_ID,
            "command": "checkpoint",
            "created_at": _utc(),
            "checkpoint": meta,
            "state": self._sm.state,
            "exchange_write_attempt_count": self._guard.exchange_write_attempt_count,
        }

    def pause(self, reason: str = "") -> dict[str, Any]:
        with self._lock:
            self._record_command("pause")
            self._assert_not_killed("pause")
            try:
                self._sm.transition("PAUSED", command="pause", reason=reason or "pause")
            except InvalidTransitionError as exc:
                raise ControlPlaneError(str(exc)) from exc
            return self._status_unlocked(record=False)

    def resume(self, reason: str = "") -> dict[str, Any]:
        with self._lock:
            self._record_command("resume")
            self._assert_not_killed("resume")
            if self._sm.state != "PAUSED":
                raise ControlPlaneError(f"resume_invalid_state:{self._sm.state}")
            try:
                self._sm.transition("RUNNING", command="resume", reason=reason or "resume")
            except InvalidTransitionError as exc:
                raise ControlPlaneError(str(exc)) from exc
            return self._status_unlocked(record=False)

    def stop(self, reason: str = "") -> dict[str, Any]:
        with self._lock:
            self._record_command("stop")
            if self._sm.state in {"STOPPED", "KILLED", "FAILED_SAFE"}:
                return self._status_unlocked(record=False)
            if self._sm.state == "IDLE":
                raise ControlPlaneError("stop_invalid_state:IDLE")
            try:
                if self._sm.state != "STOPPING":
                    self._sm.transition("STOPPING", command="stop", reason=reason or "stop")
                self._sm.transition("STOPPED", command="stop", reason=reason or "stopped")
            except InvalidTransitionError as exc:
                return self._fail_safe(str(exc), command="stop")
            self._checkpoint_unlocked()
            return self._status_unlocked(record=False)

    def recover(self, reason: str = "") -> dict[str, Any]:
        with self._lock:
            self._record_command("recover")
            self._assert_not_killed("recover")
            if self._sm.state not in {"RUNNING", "PAUSED"}:
                raise ControlPlaneError(f"recover_invalid_state:{self._sm.state}")
            if not self._run_id:
                return self._fail_safe("recover_missing_run_id", command="recover")
            try:
                self._sm.transition("RECOVERING", command="recover", reason=reason or "recover")
                payload = self._checkpoints.load_latest(self._run_id)
                if payload is None:
                    return self._fail_safe("recover_no_checkpoint", command="recover")
                # Restore non-secret fields from last checkpoint.
                self._mode = payload.get("mode") or self._mode
                self._sm.transition("RUNNING", command="recover", reason="recovered_from_checkpoint")
                return {
                    **self._status_unlocked(record=False),
                    "recovery_status": "RECOVERED",
                    "recovered_checkpoint_seq": payload.get("checkpoint_seq"),
                }
            except InvalidTransitionError as exc:
                return self._fail_safe(str(exc), command="recover")

    def kill_switch(self, reason: str = "") -> dict[str, Any]:
        with self._lock:
            self._record_command("kill_switch")
            self._kill_switch_engaged = True
            self._kill_switch_reason = reason or "kill_switch"
            if self._sm.state not in {"KILLED", "STOPPED", "FAILED_SAFE"}:
                try:
                    self._sm.transition(
                        "KILLED",
                        command="kill_switch",
                        reason=self._kill_switch_reason,
                    )
                except InvalidTransitionError:
                    # From IDLE or STOPPING, force fail-safe if kill cannot land.
                    try:
                        if self._sm.state == "STOPPING":
                            self._sm.transition(
                                "KILLED",
                                command="kill_switch",
                                reason=self._kill_switch_reason,
                            )
                        elif self._sm.state == "IDLE":
                            self._sm.transition(
                                "FAILED_SAFE",
                                command="kill_switch",
                                reason=self._kill_switch_reason,
                            )
                    except InvalidTransitionError as exc:
                        self._last_error = str(exc)
            if self._run_id:
                self._checkpoint_unlocked()
            return {
                **self._status_unlocked(record=False),
                "kill_switch_status": "TRIGGERED",
            }

    def checkpoint(self) -> dict[str, Any]:
        with self._lock:
            return self._checkpoint_unlocked()

    def health(self) -> dict[str, Any]:
        with self._lock:
            self._record_command("health")
            return build_health(
                state=self._sm.state,
                mode=self._mode,
                kill_switch_engaged=self._kill_switch_engaged,
                exchange_write_attempt_count=self._guard.exchange_write_attempt_count,
                checkpoint_count=self._checkpoint_count,
                run_id=self._run_id,
            )

    def observability(self) -> dict[str, Any]:
        with self._lock:
            self._record_command("observability")
            return build_observability(
                state=self._sm.state,
                mode=self._mode,
                kill_switch_engaged=self._kill_switch_engaged,
                kill_switch_reason=self._kill_switch_reason,
                exchange_write_attempt_count=self._guard.exchange_write_attempt_count,
                checkpoint_count=self._checkpoint_count,
                transition_count=len(self._sm.history()),
                run_id=self._run_id,
                allowed_modes=sorted(ALLOWED_MODES),
                commands_invoked=list(self._commands_invoked),
            )

    # ------------------------------------------------------------------
    # Write trap surface (tests / red-team hooks)
    # ------------------------------------------------------------------

    def attempt_exchange_write(self, endpoint: str) -> None:
        """Any exchange write is forbidden — fail closed into FAILED_SAFE."""
        with self._lock:
            self._record_command("attempt_exchange_write")
            try:
                self._guard.attempt(endpoint)
            except ExchangeWriteForbidden as exc:
                self._fail_safe(str(exc), command="attempt_exchange_write")
                raise

    @property
    def guard(self) -> NoExchangeWriteGuard:
        return self._guard

    @property
    def state_machine(self) -> ControlPlaneStateMachine:
        return self._sm
