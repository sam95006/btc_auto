"""Hard-ban refuse APIs for V15-I Lesson Replay Lab."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_replay_v15.constants import HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a lane hard ban is violated."""


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "enforced": True,
        "count": len(HARD_BANS),
    }


def refuse_exchange_write() -> None:
    raise HardBanViolation("no_demo_shadow_exchange_write")


def refuse_mainnet_real_money() -> None:
    raise HardBanViolation("no_mainnet_real_money")


def refuse_oos_walkforward() -> None:
    raise HardBanViolation("no_oos_walkforward")


def refuse_pr27_merge() -> None:
    raise HardBanViolation("no_pr27_merge")


def refuse_auto_integrate() -> None:
    raise HardBanViolation("no_auto_integrate")


def refuse_v23_complete_claim() -> None:
    raise HardBanViolation("no_v23_complete_claim")


def refuse_profitability_claim() -> None:
    raise HardBanViolation("no_profitability_claim")


def refuse_fabricated_ai_learning() -> None:
    raise HardBanViolation("no_fabricated_ai_learning")


def refuse_fixture_as_real_policy_effect() -> None:
    raise HardBanViolation("no_fixture_as_real_policy_effect_proof")


def refuse_real_lesson_prevention_while_incomplete() -> None:
    raise HardBanViolation("no_real_lesson_prevention_until_v23_verified")


def refuse_status_json_lane_artifact() -> None:
    raise HardBanViolation("no_status_json_lane_artifact")


def refuse_risk_mutation(effect: str | None = None) -> None:
    raise HardBanViolation(
        f"no_risk_leverage_size_stop_promotion_mutation:{effect or 'unspecified'}"
    )


def assert_no_status_json_filenames(paths: list[str]) -> None:
    offenders = [p for p in paths if p.lower().endswith("_status.json") or p.lower().endswith("status.json")]
    # Allow only if somehow empty; any *_status.json is banned for this lane.
    offenders = [p for p in paths if p.lower().endswith("_status.json")]
    if offenders:
        raise HardBanViolation(f"no_status_json_lane_artifact:{','.join(offenders[:5])}")
