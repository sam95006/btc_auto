"""Hard-ban refuse APIs for V16-A Trade Error Ontology."""
from __future__ import annotations

from typing import Any

from backend.nexus_trade_error_ontology_v1.constants import HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a lane hard ban is violated."""


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "enforced": True,
        "count": len(HARD_BANS),
    }


def refuse_real_money() -> None:
    raise HardBanViolation("no_real_money")


def refuse_mainnet() -> None:
    raise HardBanViolation("no_mainnet")


def refuse_exchange_write() -> None:
    raise HardBanViolation("no_exchange_write")


def refuse_oos() -> None:
    raise HardBanViolation("no_oos")


def refuse_walkforward() -> None:
    raise HardBanViolation("no_walkforward")


def refuse_fabricated_ai_learning() -> None:
    raise HardBanViolation("no_fabricated_ai_learning")


def refuse_pr26_merge() -> None:
    raise HardBanViolation("no_pr26_merge")


def refuse_pr27_merge() -> None:
    raise HardBanViolation("no_pr27_merge")


def refuse_ai_override() -> None:
    raise HardBanViolation("no_ai_override_of_deterministic_class")


def refuse_status_json_lane_artifact() -> None:
    raise HardBanViolation("no_status_json_lane_artifact")


def refuse_acceleration_report_edit() -> None:
    raise HardBanViolation("no_acceleration_report_edit")


def assert_no_status_json_filenames(paths: list[str]) -> None:
    offenders = [p for p in paths if p.lower().endswith("_status.json")]
    if offenders:
        raise HardBanViolation(f"no_status_json_lane_artifact:{','.join(offenders[:5])}")


def assert_no_acceleration_report_edit(paths: list[str]) -> None:
    offenders = [
        p
        for p in paths
        if p.replace("\\", "/").endswith("NEXUS_FINAL_ACCELERATION_REPORT.json")
    ]
    if offenders:
        raise HardBanViolation("no_acceleration_report_edit")
