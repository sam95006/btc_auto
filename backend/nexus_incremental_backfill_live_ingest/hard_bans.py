"""Hard-ban refuse APIs for V18-B Incremental Backfill + Live Ingest."""
from __future__ import annotations

from typing import Any

from backend.nexus_incremental_backfill_live_ingest.constants import BANNED_CLAIMS, HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a lane hard ban is violated."""


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "banned_claims": list(BANNED_CLAIMS),
        "enforced": True,
        "count": len(HARD_BANS),
    }


def refuse_real_money() -> None:
    raise HardBanViolation("no_real_money")


def refuse_mainnet() -> None:
    raise HardBanViolation("no_mainnet")


def refuse_exchange_write() -> None:
    raise HardBanViolation("no_exchange_write")


def refuse_demo() -> None:
    raise HardBanViolation("no_demo")


def refuse_historical_rewrite() -> None:
    raise HardBanViolation("no_historical_rewrite")


def refuse_silent_gap_fill() -> None:
    raise HardBanViolation("no_silent_gap_fill")


def refuse_unlicensed_ingest() -> None:
    raise HardBanViolation("no_unlicensed_ingest")


def refuse_future_timestamp_accept() -> None:
    raise HardBanViolation("no_future_timestamp_accept")


def refuse_15y_complete_claim() -> None:
    raise HardBanViolation("no_claim_15y_complete")


def refuse_all_exchange_history_claim() -> None:
    raise HardBanViolation("no_claim_all_exchange_history")


def refuse_full_training_set_claim() -> None:
    raise HardBanViolation("no_claim_full_training_set")


def refuse_strategy_validation_pass_claim() -> None:
    raise HardBanViolation("no_claim_strategy_validation_pass")


def refuse_pr26_merge() -> None:
    raise HardBanViolation("no_pr26_merge")


def refuse_pr27_merge() -> None:
    raise HardBanViolation("no_pr27_merge")


def refuse_acceleration_report_edit() -> None:
    raise HardBanViolation("no_acceleration_report_edit")


def refuse_report_archive_rebuild() -> None:
    raise HardBanViolation("no_report_archive_rebuild")


def refuse_banned_claim(claim: str) -> None:
    key = str(claim).strip().lower().replace(" ", "_").replace("-", "_")
    mapping = {
        "15y_complete": refuse_15y_complete_claim,
        "15y": refuse_15y_complete_claim,
        "all_exchange_history": refuse_all_exchange_history_claim,
        "full_training_set": refuse_full_training_set_claim,
        "strategy_validation_pass": refuse_strategy_validation_pass_claim,
        "strategy_validation_PASS": refuse_strategy_validation_pass_claim,
    }
    fn = mapping.get(key) or mapping.get(claim)
    if fn is None:
        raise HardBanViolation(f"unknown_banned_claim:{claim}")
    fn()


def assert_no_acceleration_report_edit(paths: list[str]) -> None:
    offenders = [
        p
        for p in paths
        if p.replace("\\", "/").endswith("NEXUS_FINAL_ACCELERATION_REPORT.json")
    ]
    if offenders:
        raise HardBanViolation("no_acceleration_report_edit")
