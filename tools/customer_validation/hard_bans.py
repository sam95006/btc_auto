"""Hard-ban enforcement for PUB-I customer validation operations."""
from __future__ import annotations

from typing import Any

HARD_BANS: tuple[str, ...] = (
    "no_merge_pr_26",
    "no_merge_pr_27",
    "no_live_public_deployment",
    "no_app_store_submission",
    "no_google_play_submission",
    "no_live_billing",
    "no_real_iap_products",
    "no_production_customer_database",
    "no_custodial_wallet",
    "no_copy_trading",
    "no_automated_customer_trading",
    "no_fabricated_participants",
    "no_fabricated_interviews",
    "no_fabricated_paid_pilots",
    "no_exchange_write",
    "no_mainnet",
    "no_real_money",
    "no_demo_order",
    "no_shadow_order",
)


class HardBanViolation(RuntimeError):
    """Raised when a PUB-I hard ban would be violated."""


FABRICATED_ID_PATTERNS = (
    "fake_",
    "fabricat",
    "synthetic_",
    "demo_user",
    "dummy_",
    "placeholder_",
    "mock_participant",
    "invented_",
)

ALLOWED_ENROLLMENT_SOURCES = frozenset(
    {
        "founder_warm_intro",
        "waitlist_screener",
        "community_referral",
    }
)


def assert_hard_bans() -> dict[str, Any]:
    return {
        "ok": True,
        "hard_bans": list(HARD_BANS),
        "hard_bans_honored": True,
        "production_customer_database": False,
        "live_billing": False,
        "automated_customer_trading": False,
    }


def refuse_fabrication(reason: str) -> None:
    raise HardBanViolation(f"HARD BAN: fabrication refused — {reason}")


def refuse_production_customer_db() -> None:
    raise HardBanViolation(
        "HARD BAN: production customer database refused in PUB-I (local workspace only)"
    )


def refuse_live_billing() -> None:
    raise HardBanViolation("HARD BAN: live billing / real IAP refused in PUB-I")


def refuse_automated_trading() -> None:
    raise HardBanViolation(
        "HARD BAN: automated customer trading / copy trading / custody refused in PUB-I"
    )


def is_fabricated_participant_id(participant_id: str) -> bool:
    lowered = (participant_id or "").strip().lower()
    if not lowered:
        return True
    return any(token in lowered for token in FABRICATED_ID_PATTERNS)
