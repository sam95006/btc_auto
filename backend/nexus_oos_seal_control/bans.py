"""Hard-ban enforcement for V15-G OOS Reservation and Seal Control."""
from __future__ import annotations

from typing import Any

from backend.nexus_oos_seal_control.constants import BLOCK_REASON, HARD_BANS, REQUIRED_FALSE_FLAGS


def default_control_flags() -> dict[str, Any]:
    return {
        "Founder_authorization_present": False,
        "founder_authorization_present": False,
        "formal_walk_forward_executed": False,
        "oos_reserved": False,
        "oos_downloaded": False,
        "oos_executed": False,
        "oos_consumed": False,
        "oos_reservation_created": False,
        "oos_touched": False,
        "strategy_selected": False,
        "strategy_promoted": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "pr27_merged": False,
        "mainnet": False,
        "real_money": False,
        "auto_integrated": False,
        "qualification_ready_count": 0,
    }


def assert_required_false_flags(flags: dict[str, Any] | None = None) -> dict[str, Any]:
    src = flags if flags is not None else default_control_flags()
    violations = [k for k in REQUIRED_FALSE_FLAGS if bool(src.get(k))]
    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "flags": {k: bool(src.get(k)) for k in REQUIRED_FALSE_FLAGS},
    }


def refuse_real_oos_reservation(plan_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "REAL_OOS_RESERVATION",
        "plan_id": plan_id,
        "reason": BLOCK_REASON,
        "oos_reserved": False,
        "oos_downloaded": False,
        "oos_executed": False,
        "oos_consumed": False,
    }


def refuse_oos_download(plan_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "OOS_DOWNLOAD",
        "plan_id": plan_id,
        "reason": "OOS_DOWNLOAD_BANNED_V15_G",
        "oos_downloaded": False,
        "oos_reserved": False,
    }


def refuse_oos_execution(plan_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "OOS_EXECUTION",
        "plan_id": plan_id,
        "reason": "OOS_EXECUTION_BANNED_V15_G",
        "oos_executed": False,
        "oos_consumed": False,
    }


def refuse_oos_consumption(plan_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "OOS_CONSUMPTION",
        "plan_id": plan_id,
        "reason": "OOS_CONSUMPTION_BANNED_V15_G",
        "oos_consumed": False,
        "oos_executed": False,
    }


def refuse_formal_walk_forward(plan_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "FORMAL_WALK_FORWARD",
        "plan_id": plan_id,
        "reason": "FORMAL_WALK_FORWARD_BANNED_V15_G",
        "formal_walk_forward_executed": False,
    }


def refuse_select() -> dict[str, Any]:
    return {"allowed": False, "selected": False, "reason": "STRATEGY_SELECTION_BANNED_V15_G"}


def refuse_promote() -> dict[str, Any]:
    return {"allowed": False, "promoted": False, "reason": "STRATEGY_PROMOTION_BANNED_V15_G"}


def refuse_demo() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "DEMO_ORDER",
        "reason": "DEMO_ORDERS_BANNED_V15_G",
        "demo_order_count": 0,
    }


def refuse_exchange_write() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "EXCHANGE_WRITE",
        "reason": "EXCHANGE_WRITES_BANNED_V15_G",
        "exchange_write_attempt_count": 0,
    }


def refuse_auto_integrate() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "AUTO_INTEGRATE",
        "reason": "AUTO_INTEGRATE_BANNED_V15_G",
        "auto_integrated": False,
    }


def hard_ban_probe_matrix(plan_id: str = "SYN_V15G_PROBE") -> dict[str, Any]:
    probes = {
        "force_real_oos_reservation": refuse_real_oos_reservation(plan_id),
        "force_oos_download": refuse_oos_download(plan_id),
        "force_oos_execution": refuse_oos_execution(plan_id),
        "force_oos_consumption": refuse_oos_consumption(plan_id),
        "force_walk_forward": refuse_formal_walk_forward(plan_id),
        "force_select": refuse_select(),
        "force_promote": refuse_promote(),
        "force_demo": refuse_demo(),
        "force_exchange_write": refuse_exchange_write(),
        "force_auto_integrate": refuse_auto_integrate(),
    }
    all_refused = all(not p.get("allowed") and not p.get("executed", False) for p in probes.values())
    flag_check = assert_required_false_flags()
    return {
        "probes": probes,
        "all_refused": all_refused and flag_check["ok"],
        "hard_bans": list(HARD_BANS),
        "flags": default_control_flags(),
        "required_false_flags": flag_check,
    }
