"""Hard-ban refuse APIs for V17-B Bronze Immutable Raw Data Lake."""
from __future__ import annotations

from typing import Any

from backend.nexus_bronze_immutable_raw_lake.constants import HARD_BANS


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


def refuse_historical_rewrite() -> None:
    raise HardBanViolation("no_historical_rewrite")


def refuse_ai_mutate_raw_payload() -> None:
    raise HardBanViolation("no_ai_mutate_raw_payload")


def refuse_non_utc() -> None:
    raise HardBanViolation("no_non_utc_timestamps")


def refuse_15y_history_claim() -> None:
    raise HardBanViolation("no_claim_15y_history_downloaded")


def refuse_full_history_ingest() -> None:
    raise HardBanViolation("no_full_history_ingest_this_round")


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
