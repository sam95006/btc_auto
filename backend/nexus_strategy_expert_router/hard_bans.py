"""Hard-ban refuse APIs for V16-D Strategy Expert Router."""
from __future__ import annotations

from typing import Any

from backend.nexus_strategy_expert_router.constants import HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a lane hard ban is violated."""


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": sorted(HARD_BANS),
        "enforced": True,
        "count": len(HARD_BANS),
    }


def refuse_ai_set_leverage() -> None:
    raise HardBanViolation("no_ai_set_leverage")


def refuse_ai_override_risk_gate() -> None:
    raise HardBanViolation("no_ai_override_risk_gate")


def refuse_status_json_lane_artifact() -> None:
    raise HardBanViolation("no_status_json_lane_artifact")


def refuse_status_report_artifact() -> None:
    raise HardBanViolation("no_status_report_artifact")


def refuse_per_minute_formal_param_thrash() -> None:
    raise HardBanViolation("no_per_minute_formal_param_thrash")


def refuse_exchange_write() -> None:
    raise HardBanViolation("no_exchange_write")


def refuse_demo_orders() -> None:
    raise HardBanViolation("no_demo_orders")


def refuse_shadow_orders() -> None:
    raise HardBanViolation("no_shadow_orders")


def refuse_mainnet_real_money() -> None:
    raise HardBanViolation("no_mainnet")


def refuse_oos_walkforward() -> None:
    raise HardBanViolation("no_oos_consumption")


def refuse_strategy_promotion_to_live() -> None:
    raise HardBanViolation("no_strategy_promotion_to_live")


def refuse_auto_integrate() -> None:
    raise HardBanViolation("no_auto_integrate_pr27")


def refuse_force_trade_when_defensive_wins() -> None:
    raise HardBanViolation("no_force_trade_when_defensive_wins")


def refuse_suppress_no_trade_sides() -> None:
    raise HardBanViolation("no_suppress_no_trade_sides")


def assert_no_status_json_filenames(paths: list[str]) -> None:
    offenders = [p for p in paths if p.lower().endswith("_status.json")]
    if offenders:
        raise HardBanViolation(f"no_status_json_lane_artifact:{','.join(offenders[:5])}")


def hard_ban_probe_matrix() -> dict[str, Any]:
    probes = [
        ("refuse_ai_set_leverage", refuse_ai_set_leverage),
        ("refuse_ai_override_risk_gate", refuse_ai_override_risk_gate),
        ("refuse_status_json_lane_artifact", refuse_status_json_lane_artifact),
        ("refuse_status_report_artifact", refuse_status_report_artifact),
        ("refuse_per_minute_formal_param_thrash", refuse_per_minute_formal_param_thrash),
        ("refuse_exchange_write", refuse_exchange_write),
        ("refuse_demo_orders", refuse_demo_orders),
        ("refuse_shadow_orders", refuse_shadow_orders),
        ("refuse_mainnet_real_money", refuse_mainnet_real_money),
        ("refuse_oos_walkforward", refuse_oos_walkforward),
        ("refuse_strategy_promotion_to_live", refuse_strategy_promotion_to_live),
        ("refuse_auto_integrate", refuse_auto_integrate),
        ("refuse_force_trade_when_defensive_wins", refuse_force_trade_when_defensive_wins),
        ("refuse_suppress_no_trade_sides", refuse_suppress_no_trade_sides),
    ]
    raised = 0
    for _name, fn in probes:
        try:
            fn()
        except HardBanViolation:
            raised += 1
    return {
        "probe_count": len(probes),
        "raised_count": raised,
        "all_raised": raised == len(probes),
    }
