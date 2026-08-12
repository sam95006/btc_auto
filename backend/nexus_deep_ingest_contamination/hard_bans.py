"""Hard bans for V17 deep ingest / contamination lane."""
from __future__ import annotations

from typing import Any

from backend.nexus_deep_ingest_contamination.constants import HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a hard-banned capability is attempted."""


def refuse_exchange_write() -> None:
    raise HardBanViolation("exchange_write_banned")


def refuse_mainnet() -> None:
    raise HardBanViolation("mainnet_banned")


def refuse_real_money() -> None:
    raise HardBanViolation("real_money_banned")


def refuse_formal_walk_forward() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "reason": "formal_walk_forward_banned_this_round",
    }


def refuse_untouched_oos() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "reason": "untouched_oos_banned_this_round",
    }


def refuse_15y_history_claim(*, claimed: bool = True) -> None:
    if claimed:
        raise HardBanViolation("claim_15y_history_downloaded_banned")


def refuse_silent_corrupt_resume() -> None:
    raise HardBanViolation("silent_corrupt_resume_banned")


def refuse_pr26_merge() -> None:
    raise HardBanViolation("pr26_merge_banned")


def refuse_pr27_merge() -> None:
    raise HardBanViolation("pr27_merge_banned")


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "exchange_write": False,
        "mainnet": False,
        "real_money": False,
        "formal_walk_forward": False,
        "untouched_oos": False,
        "claims_15y_history_downloaded": False,
        "pr26_merged": False,
        "pr27_merged": False,
        "report_edited": False,
    }
