"""Automatic Demo Session rotation — Demo-only, single-owner, no risk increase.

Never calls Mainnet. Never raises risk limits on rotate/renew.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.nexus_research.demo_autonomous.session_authorization import (
    CAPITAL_POLICY_VERSION,
    DEFAULT_MAX_RISK_PCT,
    LEVERAGE_POLICY_VERSION,
    AuthorizationError,
    AuthorizationValidator,
    get_authorization_validator,
)


def _audit_path() -> Path | None:
    try:
        from backend.nexus_research.boot_identity import research_data_dir

        root = research_data_dir()
        if root is None:
            return None
        return root / "session_rotation_audit.jsonl"
    except Exception:
        return None


@dataclass
class SessionExpiryPreflight:
    """Readiness checks before rotation."""

    owner_count: int = 1
    policy_leverage_ok: bool = True
    policy_capital_ok: bool = True
    risk_not_increased: bool = True
    emergency_stop: bool = False
    reconcile_ok: bool = True
    position_count: int = 0
    open_order_count: int = 0
    ambiguous: bool = False
    notes: list[str] = field(default_factory=list)

    def allow_full_rotation(self) -> tuple[bool, str | None]:
        if self.emergency_stop:
            return False, "emergency_stop"
        if self.owner_count != 1:
            return False, "owner_count_not_1"
        if not self.policy_leverage_ok or not self.policy_capital_ok:
            return False, "policy_version_mismatch"
        if not self.risk_not_increased:
            return False, "risk_limit_increase_blocked"
        if self.ambiguous:
            return False, "ambiguous_state"
        if not self.reconcile_ok:
            return False, "reconcile_failed"
        return True, None

    def to_dict(self) -> dict[str, Any]:
        ok, reason = self.allow_full_rotation()
        return {
            "allowFullRotation": ok,
            "blockReason": reason,
            "ownerCount": self.owner_count,
            "policyLeverageOk": self.policy_leverage_ok,
            "policyCapitalOk": self.policy_capital_ok,
            "riskNotIncreased": self.risk_not_increased,
            "emergencyStop": self.emergency_stop,
            "reconcileOk": self.reconcile_ok,
            "positionCount": self.position_count,
            "openOrderCount": self.open_order_count,
            "ambiguous": self.ambiguous,
            "notes": list(self.notes),
        }


@dataclass
class RotationResult:
    ok: bool
    mode: str  # FULL_ROTATION | POSITION_CONTINUITY | SKIPPED | FAILED
    rotation_id: str
    old_session_id: str | None = None
    new_session_id: str | None = None
    new_entries_paused: bool = False
    error: str | None = None
    preflight: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "rotationId": self.rotation_id,
            "oldSessionId": self.old_session_id,
            "newSessionId": self.new_session_id,
            "newEntriesPaused": self.new_entries_paused,
            "error": self.error,
            "preflight": self.preflight,
            "mainnetUsed": False,
            "secretSafe": True,
        }


class SingleOwnerRotationLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._holder: str | None = None

    def acquire(self, rotation_id: str) -> bool:
        with self._lock:
            if self._holder is not None:
                return False
            self._holder = rotation_id
            return True

    def release(self, rotation_id: str) -> None:
        with self._lock:
            if self._holder == rotation_id:
                self._holder = None


class RotationIdempotencyGuard:
    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def begin(self, key: str) -> bool:
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True


class RotationAuditTrail:
    def append(self, event: dict[str, Any]) -> None:
        path = _audit_path()
        payload = dict(event)
        payload["tsMs"] = int(time.time() * 1000)
        payload["secretSafe"] = True
        payload["mainnetUsed"] = False
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass


@dataclass
class PositionAwareSessionContinuity:
    """When flat → full rotate; when open → renew authority, pause new entries."""

    new_entries_paused: bool = False
    last_rotation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "newEntriesPaused": self.new_entries_paused,
            "lastRotationId": self.last_rotation_id,
        }


class AutonomousDemoSessionRotator:
    """Safe Demo-only session rotator with single-owner + idempotency guards."""

    PRE_EXPIRY_MS = 5 * 60 * 1000

    def __init__(
        self,
        *,
        auth: AuthorizationValidator | None = None,
        owner_count_fn: Callable[[], int] | None = None,
    ) -> None:
        self.auth = auth or get_authorization_validator()
        self.owner_count_fn = owner_count_fn or (lambda: 1)
        self.lock = SingleOwnerRotationLock()
        self.idem = RotationIdempotencyGuard()
        self.audit = RotationAuditTrail()
        self.continuity = PositionAwareSessionContinuity()
        self._lock = threading.Lock()

    def build_preflight(
        self,
        *,
        position_count: int,
        open_order_count: int,
        reconcile_ok: bool = True,
        ambiguous: bool = False,
    ) -> SessionExpiryPreflight:
        sess = self.auth.session
        pf = SessionExpiryPreflight(
            owner_count=int(self.owner_count_fn()),
            position_count=position_count,
            open_order_count=open_order_count,
            reconcile_ok=reconcile_ok,
            ambiguous=ambiguous,
        )
        if sess is None:
            pf.notes.append("session_missing")
            return pf
        pf.policy_leverage_ok = sess.leverage_policy_version == LEVERAGE_POLICY_VERSION
        pf.policy_capital_ok = sess.capital_policy_version == CAPITAL_POLICY_VERSION
        pf.risk_not_increased = sess.max_risk_per_trade_pct <= DEFAULT_MAX_RISK_PCT + 1e-12
        pf.emergency_stop = bool(sess.emergency_stopped)
        return pf

    def should_rotate(self, now_ms: int | None = None) -> bool:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        sess = self.auth.session
        if sess is None:
            return False
        if sess.emergency_stopped:
            return False
        if sess.is_expired(now):
            return True
        return (sess.expires_at_ms - now) <= self.PRE_EXPIRY_MS

    def rotate_if_needed(
        self,
        *,
        position_count: int,
        open_order_count: int,
        reconcile_ok: bool = True,
        ambiguous: bool = False,
        ttl_ms: int = 6 * 60 * 60 * 1000,
        force: bool = False,
    ) -> RotationResult:
        rotation_id = uuid.uuid4().hex[:16]
        if not force and not self.should_rotate():
            return RotationResult(
                ok=True,
                mode="SKIPPED",
                rotation_id=rotation_id,
                error="not_near_expiry",
            )

        sess = self.auth.session
        old_id = (sess.session_id if sess else None) or None
        idem_key = f"{old_id or 'none'}:{sess.expires_at_ms if sess else 0}"
        if not self.idem.begin(idem_key):
            return RotationResult(
                ok=True,
                mode="SKIPPED",
                rotation_id=rotation_id,
                old_session_id=old_id,
                error="duplicate_rotation_request",
            )

        if not self.lock.acquire(rotation_id):
            return RotationResult(
                ok=False,
                mode="FAILED",
                rotation_id=rotation_id,
                old_session_id=old_id,
                error="rotation_lock_held",
            )

        try:
            pf = self.build_preflight(
                position_count=position_count,
                open_order_count=open_order_count,
                reconcile_ok=reconcile_ok,
                ambiguous=ambiguous,
            )
            allow, reason = pf.allow_full_rotation()
            if not allow and reason not in ("session_missing",):
                # Still allow position continuity renew if only flat-rotation blocked by positions
                if reason in ("emergency_stop", "owner_count_not_1", "policy_version_mismatch", "risk_limit_increase_blocked", "ambiguous_state", "reconcile_failed"):
                    self.audit.append(
                        {"event": "rotation_blocked", "rotationId": rotation_id, "reason": reason, **pf.to_dict()}
                    )
                    return RotationResult(
                        ok=False,
                        mode="FAILED",
                        rotation_id=rotation_id,
                        old_session_id=old_id,
                        error=reason,
                        preflight=pf.to_dict(),
                    )

            if sess is None:
                return RotationResult(
                    ok=False,
                    mode="FAILED",
                    rotation_id=rotation_id,
                    error="session_missing",
                    preflight=pf.to_dict(),
                )

            # Renew / issue next Demo session — never raise risk.
            try:
                try:
                    new_sess = self.auth.renew(ttl_ms=ttl_ms)
                except AuthorizationError:
                    new_sess = self.auth.issue(
                        ttl_ms=ttl_ms,
                        max_risk_per_trade_pct=min(
                            sess.max_risk_per_trade_pct, DEFAULT_MAX_RISK_PCT
                        ),
                        auto_send=sess.auto_send,
                        max_consecutive_losses=sess.max_consecutive_losses,
                        risk_tier=sess.risk_tier,
                    )
            except Exception as exc:  # noqa: BLE001
                self.audit.append(
                    {"event": "rotation_exception", "rotationId": rotation_id, "error": type(exc).__name__}
                )
                return RotationResult(
                    ok=False,
                    mode="FAILED",
                    rotation_id=rotation_id,
                    old_session_id=old_id,
                    error=type(exc).__name__,
                    preflight=pf.to_dict(),
                )

            if position_count > 0:
                self.continuity.new_entries_paused = True
                mode = "POSITION_CONTINUITY"
            else:
                self.continuity.new_entries_paused = False
                mode = "FULL_ROTATION"
            self.continuity.last_rotation_id = rotation_id

            result = RotationResult(
                ok=True,
                mode=mode,
                rotation_id=rotation_id,
                old_session_id=old_id,
                new_session_id=new_sess.session_id,
                new_entries_paused=self.continuity.new_entries_paused,
                preflight=pf.to_dict(),
            )
            self.audit.append({"event": "rotation_ok", **result.to_dict()})
            return result
        finally:
            self.lock.release(rotation_id)

    def clear_new_entries_pause_if_flat(self, position_count: int) -> None:
        if position_count <= 0:
            self.continuity.new_entries_paused = False


_ROTATOR: AutonomousDemoSessionRotator | None = None
_ROTATOR_LOCK = threading.Lock()


def get_session_rotator() -> AutonomousDemoSessionRotator:
    global _ROTATOR
    with _ROTATOR_LOCK:
        if _ROTATOR is None:
            _ROTATOR = AutonomousDemoSessionRotator()
        return _ROTATOR
