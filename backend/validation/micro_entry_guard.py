"""Phase 3.0 — single-shot micro entry validation guard (CLI arm only)."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.micro_validation_config import (
    ALLOWED_MICRO_SYMBOLS,
    BLOCKED_MICRO_FLEETS,
    MICRO_VALIDATION_ALLOW_PARTIAL,
    MICRO_VALIDATION_ALLOW_REARM,
    MICRO_VALIDATION_DECISION_SOURCE,
    MICRO_VALIDATION_ENABLED,
    MICRO_VALIDATION_FLEET,
    MICRO_VALIDATION_MAX_HOLD_MIN,
    MICRO_VALIDATION_MAX_LEVERAGE,
    MICRO_VALIDATION_MAX_MARGIN_USD,
    MICRO_VALIDATION_REQUIRE_REFLECTION,
    MICRO_VALIDATION_SIDE,
    MICRO_VALIDATION_SL_USD,
    MICRO_VALIDATION_STRATEGY_KEY,
    MICRO_VALIDATION_SYMBOL,
    MICRO_VALIDATION_TP_ENABLED,
    MICRO_VALIDATION_TP_USD,
    is_micro_validation_entry,
    micro_validation_active,
)

STATES = (
    "IDLE",
    "ARMED",
    "ENTRY_SENT",
    "POSITION_OPEN",
    "EXIT_PENDING",
    "VERIFYING",
    "COMPLETED",
    "FAILED",
    "RESET_FOR_SIZING_REPAIR",
)

TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "IDLE", "RESET_FOR_SIZING_REPAIR"})


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_ts(value: str) -> Optional[float]:
    if not value:
        return None
    for parser in (
        lambda raw: datetime.fromisoformat(str(raw)),
        lambda raw: datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            return parser(value).timestamp()
        except Exception:
            continue
    return None


class MicroEntryGuard:
    def __init__(self, runtime_store=None):
        self._store = runtime_store
        self._state: Dict[str, Any] = {}
        self.last_error = ""
        self.reload()

    def _rs(self):
        if self._store is None:
            from backend.services.runtime_store import runtime_store as rs

            self._store = rs
        return self._store

    def reload(self) -> Dict[str, Any]:
        self._state = dict(self._rs().load_micro_validation_state() or {})
        if not self._state:
            self._state = self._default_state()
        return dict(self._state)

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._state)

    def _default_state(self) -> Dict[str, Any]:
        return {
            "state": "IDLE",
            "symbol": MICRO_VALIDATION_SYMBOL,
            "side": MICRO_VALIDATION_SIDE,
            "fleet": MICRO_VALIDATION_FLEET,
            "margin_usd": MICRO_VALIDATION_MAX_MARGIN_USD,
            "leverage": MICRO_VALIDATION_MAX_LEVERAGE,
            "entry_consumed": False,
            "entry_time": "",
            "exit_time": "",
            "position_id": "",
            "session_id": "",
            "failure_reason": "",
            "verification": {},
            "report": {},
            "sizing_repair_reset_used": False,
            "updated_at": _now(),
        }

    def _save(self) -> None:
        self._state["updated_at"] = _now()
        self._rs().save_micro_validation_state(self._state)

    def is_session_active(self) -> bool:
        state = str(self._state.get("state") or "IDLE").upper()
        return state not in TERMINAL_STATES or state == "ARMED"

    def session_in_progress(self) -> bool:
        state = str(self._state.get("state") or "IDLE").upper()
        return state in {"ARMED", "ENTRY_SENT", "POSITION_OPEN", "EXIT_PENDING", "VERIFYING"}

    def should_block_ai_entries(self) -> bool:
        if not micro_validation_active():
            return False
        from config.micro_validation_config import MICRO_VALIDATION_PAUSE_AI_ENTRIES

        if not MICRO_VALIDATION_PAUSE_AI_ENTRIES:
            return False
        return self.session_in_progress() or str(self._state.get("state") or "").upper() == "ARMED"

    def can_arm(self) -> bool:
        self.last_error = ""
        if not micro_validation_active():
            self.last_error = "NEXUS_MICRO_VALIDATION_ENABLED=0"
            return False
        state = str(self._state.get("state") or "IDLE").upper()
        if state == "RESET_FOR_SIZING_REPAIR":
            if self._state.get("entry_consumed"):
                self.last_error = "entry_already_consumed"
                return False
        elif state in {"IDLE"}:
            if self._state.get("entry_consumed"):
                self.last_error = "entry_already_consumed"
                return False
        elif state == "COMPLETED" and MICRO_VALIDATION_ALLOW_REARM:
            if self._state.get("entry_consumed"):
                self.last_error = "entry_already_consumed"
                return False
        elif state == "FAILED":
            self.last_error = "rearm_not_allowed_run_reset_for_sizing_repair"
            return False
        else:
            self.last_error = f"session_busy:{state}"
            return False
        symbol = str(MICRO_VALIDATION_SYMBOL or "").upper()
        if symbol not in ALLOWED_MICRO_SYMBOLS:
            self.last_error = f"symbol_not_allowed:{symbol}"
            return False
        if str(MICRO_VALIDATION_FLEET or "").upper() in BLOCKED_MICRO_FLEETS:
            self.last_error = "fleet_not_allowed"
            return False
        return True

    def arm(self, session_id: str = "") -> Dict[str, Any]:
        if not self.can_arm():
            raise ValueError(self.last_error or "cannot_arm")
        sid = session_id or f"micro_{int(time.time())}"
        self._state = {
            **self._default_state(),
            "state": "ARMED",
            "session_id": sid,
            "symbol": MICRO_VALIDATION_SYMBOL,
            "side": MICRO_VALIDATION_SIDE,
            "fleet": MICRO_VALIDATION_FLEET,
        }
        self._save()
        return dict(self._state)

    def build_entry_request(self) -> Dict[str, Any]:
        symbol = str(self._state.get("symbol") or MICRO_VALIDATION_SYMBOL).upper()
        fleet = str(self._state.get("fleet") or MICRO_VALIDATION_FLEET).upper()
        side = str(self._state.get("side") or MICRO_VALIDATION_SIDE).upper()
        margin = min(float(self._state.get("margin_usd") or MICRO_VALIDATION_MAX_MARGIN_USD), MICRO_VALIDATION_MAX_MARGIN_USD)
        leverage = min(int(self._state.get("leverage") or MICRO_VALIDATION_MAX_LEVERAGE), MICRO_VALIDATION_MAX_LEVERAGE)
        return {
            "fleet": fleet,
            "symbol": symbol,
            "symbol_override": symbol,
            "side": side,
            "margin": round(margin, 4),
            "leverage": leverage,
            "reason": "micro_validation_p30_entry",
            "decision_source": MICRO_VALIDATION_DECISION_SOURCE,
            "proposer": MICRO_VALIDATION_DECISION_SOURCE,
            "strategy_key": MICRO_VALIDATION_STRATEGY_KEY,
            "raw_confidence": 0.72,
            "adjusted_confidence": 0.72,
            "pyramid_add": False,
            "market_type": "futures",
            "capital_pool": "fleet",
            "micro_validation_session_id": self._state.get("session_id"),
        }

    def validate_request(self, request) -> tuple[bool, str]:
        request = dict(request or {})
        if not is_micro_validation_entry(request):
            return False, "not_micro_validation_entry"
        if str(self._state.get("state") or "").upper() not in {"ARMED", "ENTRY_SENT"}:
            return False, "micro_session_not_armed"
        if self._state.get("entry_consumed"):
            return False, "micro_entry_consumed"
        symbol = str(request.get("symbol") or request.get("symbol_override") or "").upper()
        if symbol != str(self._state.get("symbol") or MICRO_VALIDATION_SYMBOL).upper():
            return False, "micro_symbol_mismatch"
        if str(request.get("side") or "").upper() != str(self._state.get("side") or MICRO_VALIDATION_SIDE).upper():
            return False, "micro_side_mismatch"
        if request.get("pyramid_add"):
            return False, "micro_pyramid_forbidden"
        if float(request.get("margin") or 0.0) > MICRO_VALIDATION_MAX_MARGIN_USD + 1e-6:
            return False, "micro_margin_exceeded"
        if int(request.get("leverage") or 0) > MICRO_VALIDATION_MAX_LEVERAGE:
            return False, "micro_leverage_exceeded"
        if str(request.get("fleet") or "").upper() in BLOCKED_MICRO_FLEETS:
            return False, "micro_fleet_forbidden"
        return True, "ok"

    def clamp_request(self, request) -> Dict[str, Any]:
        request = dict(request or {})
        request["margin"] = round(min(float(request.get("margin") or MICRO_VALIDATION_MAX_MARGIN_USD), MICRO_VALIDATION_MAX_MARGIN_USD), 4)
        request["leverage"] = min(int(request.get("leverage") or MICRO_VALIDATION_MAX_LEVERAGE), MICRO_VALIDATION_MAX_LEVERAGE)
        request["pyramid_add"] = False
        request["decision_source"] = MICRO_VALIDATION_DECISION_SOURCE
        request["strategy_key"] = MICRO_VALIDATION_STRATEGY_KEY
        return request

    def mark_entry_sent(self) -> None:
        self._state["state"] = "ENTRY_SENT"
        self._state["entry_consumed"] = True
        self._state["entry_time"] = _now()
        self._save()

    def mark_position_open(self, position_id: str = "") -> None:
        self._state["state"] = "POSITION_OPEN"
        if position_id:
            self._state["position_id"] = position_id
        if not self._state.get("entry_time"):
            self._state["entry_time"] = _now()
        self._save()

    def mark_exit_pending(self) -> None:
        self._state["state"] = "EXIT_PENDING"
        self._save()

    def mark_verifying(self, exit_time: str = "") -> None:
        self._state["state"] = "VERIFYING"
        self._state["exit_time"] = exit_time or _now()
        self._save()

    def evaluate_exit(self, position) -> Optional[Dict[str, Any]]:
        position = dict(position or {})
        state = str(self._state.get("state") or "").upper()
        if state not in {"ENTRY_SENT", "POSITION_OPEN"}:
            return None
        symbol = str(position.get("symbol") or "").upper()
        if symbol != str(self._state.get("symbol") or "").upper():
            return None
        unrealized = float(position.get("unrealized_pnl", 0.0) or 0.0)
        opened_at = position.get("opened_at") or self._state.get("entry_time") or ""
        opened_ts = _parse_ts(str(opened_at))
        if opened_ts and (time.time() - opened_ts) >= MICRO_VALIDATION_MAX_HOLD_MIN * 60.0:
            return {
                "type": "full",
                "reason": "micro_validation_max_hold",
                "exit_class": "timeout",
            }
        if unrealized <= -float(MICRO_VALIDATION_SL_USD):
            return {
                "type": "full",
                "reason": "micro_validation_stop_loss",
                "exit_class": "stop_loss",
            }
        if MICRO_VALIDATION_TP_ENABLED and MICRO_VALIDATION_TP_USD > 0 and unrealized >= float(MICRO_VALIDATION_TP_USD):
            return {
                "type": "full",
                "reason": "micro_validation_take_profit",
                "exit_class": "take_profit",
            }
        return None

    def verify_chain(self, runtime_store=None) -> Dict[str, Any]:
        rs = runtime_store or self._rs()
        symbol = str(self._state.get("symbol") or MICRO_VALIDATION_SYMBOL).upper()
        trades = [row for row in rs.recent_trade_results(limit=200) if str(row.get("symbol") or "").upper() == symbol]
        reflections = [row for row in rs.recent_reflection_records(limit=200) if str(row.get("symbol") or "").upper() == symbol]
        patches = [
            row
            for row in rs.list_applied_learning_patches(limit=200)
            if str((row.get("symbol_lesson") or {}).get("symbol") or "").upper() == symbol
        ]
        opens = [t for t in trades if str(t.get("event") or "").upper() == "OPEN"]
        closes = [t for t in trades if str(t.get("event") or "").upper() in {"CLOSE", "PARTIAL", "EXCHANGE_CLOSE", "LIQUIDATION"}]
        latest_close = closes[0] if closes else {}
        close_pnl = float(latest_close.get("pnl", 0.0) or 0.0)
        tier_a = bool(opens and closes)
        tier_b = bool(
            tier_a
            and latest_close
            and close_pnl < 0
            and reflections
            and patches
            and float(patches[0].get("confidence_penalty") or 0.0) > 0
        )
        require_reflection = bool(MICRO_VALIDATION_REQUIRE_REFLECTION)
        has_close_result = bool(closes)
        reflection_missing_fail = bool(require_reflection and has_close_result and not reflections)
        patch_missing_fail = bool(require_reflection and has_close_result and close_pnl < 0 and not patches)
        passed = tier_b if require_reflection else tier_a
        if reflection_missing_fail or patch_missing_fail:
            passed = False
        verification = {
            "symbol": symbol,
            "tier_a": tier_a,
            "tier_b": tier_b,
            "passed": passed,
            "require_reflection": require_reflection,
            "reflection_missing_fail": reflection_missing_fail,
            "patch_missing_fail": patch_missing_fail,
            "open_count": len(opens),
            "close_count": len(closes),
            "reflection_count": len(reflections),
            "patch_count": len(patches),
            "latest_open": opens[0] if opens else None,
            "latest_close": latest_close or None,
            "latest_reflection": reflections[0] if reflections else None,
            "latest_patch": patches[0] if patches else None,
            "confidence_penalty": float(patches[0].get("confidence_penalty") or 0.0) if patches else 0.0,
        }
        self._state["verification"] = verification
        self._save()
        return verification

    def build_report(self, verification: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        verification = verification or dict(self._state.get("verification") or {})
        symbol = str(self._state.get("symbol") or MICRO_VALIDATION_SYMBOL).upper()
        latest_close = verification.get("latest_close") or {}
        latest_reflection = verification.get("latest_reflection") or {}
        latest_patch = verification.get("latest_patch") or {}
        tier_a = bool(verification.get("tier_a"))
        tier_b = bool(verification.get("tier_b"))
        passed = bool(verification.get("passed"))
        reflection_pipeline_verified = tier_b and passed
        report = {
            "session_id": self._state.get("session_id"),
            "symbol": symbol,
            "state": self._state.get("state"),
            "entry_time": self._state.get("entry_time") or (verification.get("latest_open") or {}).get("timestamp"),
            "exit_time": self._state.get("exit_time") or latest_close.get("timestamp"),
            "trade_result": latest_close or verification.get("latest_open"),
            "reflection_record": latest_reflection,
            "applied_patch": latest_patch,
            "confidence_penalty": verification.get("confidence_penalty", 0.0),
            "tier_a_pass": tier_a,
            "tier_b_pass": tier_b,
            "recommend_lift_defensive": False,
            "reflection_pipeline_verified": reflection_pipeline_verified,
            "failure_reason": self._state.get("failure_reason") or "",
            "verification": verification,
            "generated_at": _now(),
        }
        self._state["report"] = report
        self._save()
        return report

    def complete(self, verification: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        verification = verification or self.verify_chain()
        report = self.build_report(verification)
        if verification.get("passed"):
            self._state["state"] = "COMPLETED"
        else:
            self._state["state"] = "FAILED"
            reasons: List[str] = []
            if verification.get("reflection_missing_fail"):
                reasons.append("trade_result_without_reflection")
            if verification.get("patch_missing_fail"):
                reasons.append("loss_without_applied_patch")
            if not verification.get("tier_a"):
                reasons.append("missing_open_or_close")
            if MICRO_VALIDATION_REQUIRE_REFLECTION and not verification.get("tier_b"):
                reasons.append("tier_b_incomplete")
            self._state["failure_reason"] = ",".join(reasons) or "verification_failed"
        self._save()
        return report

    def fail(self, reason: str) -> Dict[str, Any]:
        self._state["state"] = "FAILED"
        self._state["failure_reason"] = str(reason or "unknown")[:240]
        self._save()
        return dict(self._state)

    def reset_for_sizing_repair(self) -> tuple[bool, str]:
        """One-time reset after Phase 3.1 sizing repair (FAILED → RESET_FOR_SIZING_REPAIR)."""
        state = str(self._state.get("state") or "IDLE").upper()
        if state != "FAILED":
            return False, f"reset_requires_failed_state:{state}"
        if bool(self._state.get("sizing_repair_reset_used")):
            return False, "sizing_repair_reset_already_used"
        self._state["sizing_repair_reset_used"] = True
        self._state["state"] = "RESET_FOR_SIZING_REPAIR"
        self._state["failure_reason"] = ""
        self._state["entry_consumed"] = False
        self._state["entry_time"] = ""
        self._state["exit_time"] = ""
        self._state["position_id"] = ""
        self._state["session_id"] = ""
        self._state["verification"] = {}
        self._state["report"] = {}
        self._save()
        return True, "ok"

    def disarm_runtime_flag_note(self) -> str:
        return "Set NEXUS_MICRO_VALIDATION_ENABLED=0 after session; Defensive Mode remains ON."


_guard: Optional[MicroEntryGuard] = None


def get_micro_entry_guard() -> MicroEntryGuard:
    global _guard
    if _guard is None:
        _guard = MicroEntryGuard()
    else:
        _guard.reload()
    return _guard
