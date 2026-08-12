"""Hard-ban refuse APIs for V16-B Counterfactual Replay Engine."""
from __future__ import annotations

from typing import Any

from backend.nexus_counterfactual_replay_v16.constants import HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a lane hard ban is violated."""


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "enforced": True,
        "count": len(HARD_BANS),
    }


def refuse_exchange_write() -> None:
    raise HardBanViolation("no_demo_shadow_exchange_write")


def refuse_mainnet_real_money() -> None:
    raise HardBanViolation("no_mainnet_real_money")


def refuse_oos_walkforward() -> None:
    raise HardBanViolation("no_oos_walkforward")


def refuse_auto_integrate() -> None:
    raise HardBanViolation("no_auto_integrate")


def refuse_future_leakage() -> None:
    raise HardBanViolation("no_future_leakage")


def refuse_rewrite_real_ledger() -> None:
    raise HardBanViolation("no_rewrite_real_ledger")


def refuse_counterfactual_as_real_performance() -> None:
    raise HardBanViolation("no_counterfactual_profit_as_real_performance")


def refuse_status_json_lane_artifact() -> None:
    raise HardBanViolation("no_status_json_lane_artifact")


def refuse_status_report_artifact() -> None:
    raise HardBanViolation("no_status_report_artifact")


def refuse_pit_bypass() -> None:
    raise HardBanViolation("no_pit_bypass")


def refuse_silent_impute() -> None:
    raise HardBanViolation("no_silent_impute_missing_bars")


def assert_no_status_json_filenames(paths: list[str]) -> None:
    offenders = [
        p
        for p in paths
        if p.lower().endswith("_status.json") or p.lower().endswith("/status.json")
    ]
    if offenders:
        raise HardBanViolation(f"no_status_json_lane_artifact:{','.join(offenders[:5])}")


def assert_no_status_report_filenames(paths: list[str]) -> None:
    banned_suffixes = (
        "_status.json",
        "status.json",
        "_status_report.json",
        "SUMMARY.md",
        "status_report.md",
        "lane_report.md",
    )
    offenders = []
    for p in paths:
        name = p.replace("\\", "/").split("/")[-1]
        lower = name.lower()
        if any(lower.endswith(s.lower()) or lower == s.lower() for s in banned_suffixes):
            offenders.append(p)
    if offenders:
        raise HardBanViolation(f"no_status_report_artifact:{','.join(offenders[:5])}")
