"""Hard bans for V17 deep PIT / survivorship / collision lane."""
from __future__ import annotations

from typing import Any

from backend.nexus_deep_pit_survivorship.constants import HARD_BANS, LEAP_SECOND_POLICY


class HardBanViolation(RuntimeError):
    """Raised when a hard-banned capability is attempted."""


def refuse_exchange_write() -> None:
    raise HardBanViolation("exchange_write_banned")


def refuse_mainnet() -> None:
    raise HardBanViolation("mainnet_banned")


def refuse_real_money() -> None:
    raise HardBanViolation("real_money_banned")


def refuse_formal_walk_forward() -> dict[str, Any]:
    return {"allowed": False, "executed": False, "reason": "formal_walk_forward_banned"}


def refuse_untouched_oos() -> dict[str, Any]:
    return {"allowed": False, "executed": False, "reason": "untouched_oos_banned"}


def refuse_pr26_merge() -> None:
    raise HardBanViolation("pr26_merge_banned")


def refuse_pr27_merge() -> None:
    raise HardBanViolation("pr27_merge_banned")


def refuse_tz_local_as_known_at(*, tz_name: str) -> None:
    raise HardBanViolation(f"no_tz_local_as_known_at:{tz_name}")


def refuse_leap_second_aware_claim(*, claimed: bool = True) -> None:
    if claimed:
        raise HardBanViolation(
            f"no_leap_second_aware_claim:policy={LEAP_SECOND_POLICY}"
        )


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "exchange_write": False,
        "mainnet": False,
        "real_money": False,
        "formal_walk_forward": False,
        "untouched_oos": False,
        "pr26_merged": False,
        "pr27_merged": False,
        "report_edited": False,
        "leap_second_policy": LEAP_SECOND_POLICY,
    }
