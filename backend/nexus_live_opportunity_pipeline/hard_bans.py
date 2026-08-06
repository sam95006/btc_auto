"""Hard-ban probes for V18-D Live Opportunity Pipeline."""
from __future__ import annotations

from typing import Any

from backend.nexus_live_opportunity_pipeline.constants import HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a hard ban is violated."""


def refuse_exchange_write() -> None:
    raise HardBanViolation("no_exchange_write")


def refuse_demo_orders() -> None:
    raise HardBanViolation("no_demo_orders")


def refuse_mainnet() -> None:
    raise HardBanViolation("no_mainnet")


def refuse_ai_override_data_trust() -> None:
    raise HardBanViolation("no_ai_override_data_trust")


def refuse_ai_override_risk() -> None:
    raise HardBanViolation("no_ai_override_risk")


def refuse_candidate_as_trade_signal() -> None:
    raise HardBanViolation("candidate_is_not_trade_signal")


def refuse_actual_ordered_true() -> None:
    raise HardBanViolation("actual_ordered_must_be_false")


def refuse_actual_filled_true() -> None:
    raise HardBanViolation("actual_filled_must_be_false")


def assert_shadow_flags(decision: dict[str, Any]) -> None:
    if decision.get("actual_ordered") is not False:
        refuse_actual_ordered_true()
    if decision.get("actual_filled") is not False:
        refuse_actual_filled_true()
    if decision.get("is_trade_signal") is True:
        refuse_candidate_as_trade_signal()
    if decision.get("exchange_order_id") not in (None, ""):
        refuse_exchange_write()


def hard_ban_inventory() -> dict[str, Any]:
    return {"enforced": True, "hard_bans": sorted(HARD_BANS)}


def hard_ban_probe_matrix() -> dict[str, Any]:
    probes: dict[str, bool] = {}
    for name, fn in (
        ("no_exchange_write", refuse_exchange_write),
        ("no_demo_orders", refuse_demo_orders),
        ("no_mainnet", refuse_mainnet),
        ("no_ai_override_data_trust", refuse_ai_override_data_trust),
        ("no_ai_override_risk", refuse_ai_override_risk),
        ("candidate_is_not_trade_signal", refuse_candidate_as_trade_signal),
        ("actual_ordered_must_be_false", refuse_actual_ordered_true),
        ("actual_filled_must_be_false", refuse_actual_filled_true),
    ):
        raised = False
        try:
            fn()
        except HardBanViolation:
            raised = True
        probes[name] = raised
    return {"probes": probes, "all_raised": all(probes.values())}
