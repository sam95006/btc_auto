"""Hard bans for V17-C silver symbol identity lane."""
from __future__ import annotations

from typing import Any

from backend.nexus_silver_symbol_identity.constants import HARD_BANS


class HardBanViolation(ValueError):
    pass


def refuse_exchange_write(*, exchange_write: bool = False) -> None:
    if exchange_write:
        raise HardBanViolation("no_exchange_write")


def refuse_mainnet(*, mainnet: bool = False) -> None:
    if mainnet:
        raise HardBanViolation("no_mainnet_client")


def refuse_pr_integration(*, pr26: bool = False, pr27: bool = False) -> None:
    if pr26:
        raise HardBanViolation("no_auto_integration_into_PR26")
    if pr27:
        raise HardBanViolation("no_auto_integration_into_PR27")


def assert_hard_bans_declared() -> dict[str, Any]:
    required = {
        "no_exchange_write",
        "no_mainnet_client",
        "no_real_money",
        "no_auto_integration_into_PR26",
        "no_auto_integration_into_PR27",
        "no_erase_delisted_instruments",
        "no_collapse_cross_exchange_symbols",
        "no_collapse_spot_perp_identity",
        "no_silent_rename_without_lineage",
        "no_drop_stablecoin_depeg_periods",
        "no_fixture_as_real_performance",
    }
    missing = sorted(required - set(HARD_BANS))
    return {"ok": not missing, "missing": missing, "hard_bans": list(HARD_BANS)}
