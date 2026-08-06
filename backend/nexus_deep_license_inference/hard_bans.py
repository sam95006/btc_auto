"""Hard bans for V17 deep license / inference lane."""
from __future__ import annotations

from typing import Any

from backend.nexus_deep_license_inference.constants import HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a hard-banned capability is attempted."""


def refuse_exchange_write() -> None:
    raise HardBanViolation("exchange_write_banned")


def refuse_mainnet() -> None:
    raise HardBanViolation("mainnet_banned")


def refuse_real_money() -> None:
    raise HardBanViolation("real_money_banned")


def refuse_pr26_merge() -> None:
    raise HardBanViolation("pr26_merge_banned")


def refuse_pr27_merge() -> None:
    raise HardBanViolation("pr27_merge_banned")


def refuse_restricted_license_live(status: str) -> None:
    raise HardBanViolation(f"restricted_license_as_live_banned:{status}")


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "exchange_write": False,
        "mainnet": False,
        "real_money": False,
        "pr26_merged": False,
        "pr27_merged": False,
        "report_edited": False,
        "restricted_license_as_live": False,
        "private_gold_factory_exposed_in_public_tree": False,
    }
