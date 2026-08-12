"""Hard-ban enforcement for V16-F Lesson Validation Firewall."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_validation_firewall.constants import (
    BLOCK_REASONS_ACTIVE,
    HARD_BANS,
    REQUIRED_FALSE_FLAGS,
    SOT_FORMAL_WF,
    SOT_LESSON_PREVENTION,
    SOT_OOS,
    SOT_REAL_ACTIVE_ALLOWED,
    SOT_V2_3_COMPLETE,
    SOT_V2_3_TERMINAL,
)


class HardBanViolation(RuntimeError):
    """Raised when a lane hard ban is violated."""


def default_control_flags() -> dict[str, Any]:
    return {
        "real_lesson_active": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "production_mutated": False,
        "ai_self_promoted": False,
        "cherry_picked": False,
        "demo_order_count": 0,
        "demo_order_count_nonzero": False,
        "exchange_write_attempt_count": 0,
        "exchange_write_attempted": False,
        "mainnet": False,
        "real_money": False,
        "pr27_merged": False,
        "auto_integrated": False,
        "v23_complete": SOT_V2_3_COMPLETE,
        "formal_wf": SOT_FORMAL_WF,
        "oos": SOT_OOS,
        "lesson_prevention_status": SOT_LESSON_PREVENTION,
        "real_active_allowed": SOT_REAL_ACTIVE_ALLOWED,
    }


def assert_required_false_flags(flags: dict[str, Any] | None = None) -> dict[str, Any]:
    src = flags if flags is not None else default_control_flags()
    violations: list[str] = []
    for key in REQUIRED_FALSE_FLAGS:
        if key == "demo_order_count_nonzero":
            if bool(src.get("demo_order_count_nonzero")) or int(src.get("demo_order_count") or 0) != 0:
                violations.append(key)
            continue
        if key == "exchange_write_attempted":
            if bool(src.get("exchange_write_attempted")) or int(
                src.get("exchange_write_attempt_count") or 0
            ) != 0:
                violations.append(key)
            continue
        if bool(src.get(key)):
            violations.append(key)
    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "flags": {k: bool(src.get(k)) for k in REQUIRED_FALSE_FLAGS},
    }


def active_block_reasons() -> list[str]:
    reasons: list[str] = []
    if not SOT_V2_3_COMPLETE:
        reasons.append("V2_3_INCOMPLETE")
    if not SOT_FORMAL_WF:
        reasons.append("FORMAL_WF_FALSE")
    if not SOT_OOS:
        reasons.append("OOS_FALSE")
    if str(SOT_LESSON_PREVENTION).upper() != "READY":
        reasons.append("LESSON_PREVENTION_BLOCKED")
    if not SOT_REAL_ACTIVE_ALLOWED:
        reasons.append("REAL_ACTIVE_DISALLOWED_THIS_WINDOW")
    # Ensure canonical set is present.
    for r in BLOCK_REASONS_ACTIVE:
        if r not in reasons:
            reasons.append(r)
    return reasons


def refuse_real_lesson_active(lesson_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "MARK_REAL_LESSON_ACTIVE",
        "lesson_id": lesson_id,
        "real_lesson_active": False,
        "reason": "+".join(active_block_reasons()),
        "v23_terminal": SOT_V2_3_TERMINAL,
        "v23_complete": False,
        "formal_wf": False,
        "oos": False,
        "lesson_prevention": SOT_LESSON_PREVENTION,
    }


def refuse_ai_self_promote(actor: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "AI_SELF_PROMOTE",
        "actor": actor or "ai_agent",
        "ai_self_promoted": False,
        "reason": "AI_CANNOT_SELF_PROMOTE",
    }


def refuse_cherry_pick(lesson_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "FAVORABLE_ONLY_CHERRY_PICK",
        "lesson_id": lesson_id,
        "cherry_picked": False,
        "reason": "NO_FAVORABLE_ONLY_CHERRY_PICKING",
    }


def refuse_stage_skip(from_state: str, to_state: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "STAGE_SKIP",
        "from_state": from_state,
        "to_state": to_state,
        "reason": "NO_STAGE_SKIP",
    }


def refuse_formal_walk_forward(lesson_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "FORMAL_WALK_FORWARD",
        "lesson_id": lesson_id,
        "formal_walk_forward_executed": False,
        "reason": "FORMAL_WF_BANNED_V16_F_WINDOW",
    }


def refuse_oos_execution(lesson_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "OOS_EXECUTION",
        "lesson_id": lesson_id,
        "oos_executed": False,
        "reason": "OOS_EXECUTION_BANNED_V16_F_WINDOW",
    }


def refuse_production_mutation(target: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "PRODUCTION_MUTATION",
        "target": target,
        "production_mutated": False,
        "reason": "NO_PRODUCTION_MUTATION",
    }


def refuse_demo_order() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "DEMO_ORDER",
        "demo_order_count": 0,
        "reason": "DEMO_ORDERS_BANNED_V16_F",
    }


def refuse_exchange_write() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "EXCHANGE_WRITE",
        "exchange_write_attempt_count": 0,
        "reason": "EXCHANGE_WRITES_BANNED_V16_F",
    }


def refuse_status_json_report(path: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "WRITE_STATUS_JSON_REPORT",
        "path": path,
        "reason": "NO_STATUS_JSON_REPORT",
    }


def refuse_immutable_record_rewrite(record_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "REWRITE_IMMUTABLE_PROMOTION_RECORD",
        "record_id": record_id,
        "reason": "NO_IMMUTABLE_RECORD_REWRITE",
    }


def hard_ban_probe_matrix(lesson_id: str = "SYN_V16F_PROBE") -> dict[str, Any]:
    probes = {
        "force_real_active": refuse_real_lesson_active(lesson_id),
        "force_ai_self_promote": refuse_ai_self_promote("synthetic_ai"),
        "force_cherry_pick": refuse_cherry_pick(lesson_id),
        "force_stage_skip": refuse_stage_skip("CANDIDATE", "ACTIVE"),
        "force_walk_forward": refuse_formal_walk_forward(lesson_id),
        "force_oos": refuse_oos_execution(lesson_id),
        "force_production_mutation": refuse_production_mutation("risk_limits"),
        "force_demo": refuse_demo_order(),
        "force_exchange_write": refuse_exchange_write(),
        "force_status_json": refuse_status_json_report("v16_f_status.json"),
        "force_record_rewrite": refuse_immutable_record_rewrite("rec_probe"),
    }
    all_refused = all(
        (not p.get("allowed")) and (not p.get("executed", False)) for p in probes.values()
    )
    flag_check = assert_required_false_flags()
    return {
        "probes": probes,
        "all_refused": all_refused and flag_check["ok"],
        "hard_bans": list(HARD_BANS),
        "flags": default_control_flags(),
        "required_false_flags": flag_check,
        "active_block_reasons": active_block_reasons(),
    }


def assert_no_status_json_filenames(paths: list[str]) -> None:
    offenders = [
        p
        for p in paths
        if p.lower().endswith("_status.json")
        or p.lower().endswith("/status.json")
        or p.lower().endswith("\\status.json")
        or p.lower().endswith("report.json")
    ]
    if offenders:
        raise HardBanViolation(f"no_status_json_report:{','.join(offenders[:5])}")
