"""Hard-ban enforcement for V16-H Decision Memory Graph."""
from __future__ import annotations

from typing import Any

from backend.nexus_decision_memory_graph.constants import HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a lane hard ban is violated."""


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "enforced": True,
        "count": len(HARD_BANS),
        "lane": "V16-H",
    }


def refuse_pr26_merge() -> None:
    raise HardBanViolation("no_pr26_merge")


def refuse_pr27_merge() -> None:
    raise HardBanViolation("no_pr27_merge")


def refuse_demo_orders() -> None:
    raise HardBanViolation("no_demo_orders")


def refuse_shadow_orders() -> None:
    raise HardBanViolation("no_shadow_orders")


def refuse_exchange_writes() -> None:
    raise HardBanViolation("no_exchange_writes")


def refuse_mainnet() -> None:
    raise HardBanViolation("no_mainnet")


def refuse_real_money() -> None:
    raise HardBanViolation("no_real_money")


def refuse_secret_storage() -> None:
    raise HardBanViolation("no_secret_storage")


def refuse_private_field_leak() -> None:
    raise HardBanViolation("no_private_field_leak_to_public")


def refuse_required_external_db() -> None:
    raise HardBanViolation("no_required_external_graph_db")


def refuse_status_json() -> None:
    raise HardBanViolation("no_status_json_lane_reports")


def refuse_fabricated_learning() -> None:
    raise HardBanViolation("no_fabricated_ai_learning")


def refuse_profitability_claim() -> None:
    raise HardBanViolation("no_profitability_claims")


def refuse_auto_integrate() -> None:
    raise HardBanViolation("no_auto_integrate")


def refuse_ledger_rewrite() -> None:
    raise HardBanViolation("no_rewrite_real_ledger")


def refuse_future_leakage() -> None:
    raise HardBanViolation("no_future_leakage_in_pit")


def hard_ban_probe_matrix() -> dict[str, Any]:
    probes: dict[str, Any] = {}
    actions = {
        "force_pr26": refuse_pr26_merge,
        "force_pr27": refuse_pr27_merge,
        "force_demo": refuse_demo_orders,
        "force_shadow": refuse_shadow_orders,
        "force_exchange": refuse_exchange_writes,
        "force_mainnet": refuse_mainnet,
        "force_real_money": refuse_real_money,
        "force_secret_storage": refuse_secret_storage,
        "force_private_leak": refuse_private_field_leak,
        "force_external_db": refuse_required_external_db,
        "force_status_json": refuse_status_json,
        "force_fabricated_learning": refuse_fabricated_learning,
        "force_profit_claim": refuse_profitability_claim,
        "force_auto_integrate": refuse_auto_integrate,
        "force_ledger_rewrite": refuse_ledger_rewrite,
        "force_future_leak": refuse_future_leakage,
    }
    all_refused = True
    for name, fn in actions.items():
        try:
            fn()
            probes[name] = {"refused": False, "error": None}
            all_refused = False
        except HardBanViolation as exc:
            probes[name] = {"refused": True, "error": str(exc), "allowed": False}
    return {
        "probes": probes,
        "all_refused": all_refused,
        "hard_bans": list(HARD_BANS),
    }
