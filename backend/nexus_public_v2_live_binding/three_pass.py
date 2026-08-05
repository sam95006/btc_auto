"""Three-pass verification runner for PUB2-B."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_public_v2_live_binding.binder import bind_all_components
from backend.nexus_public_v2_live_binding.constants import (
    FAIL_RECOMMENDATION,
    PASS_RECOMMENDATION,
)
from backend.nexus_public_v2_live_binding.hard_bans import run_three_passes as run_hard_ban_three
from backend.nexus_public_v2_live_binding.verifier import verify_live_e2e_binding


def run_three_pass_verification(*, root: Path | str | None = None) -> dict[str, Any]:
    """Impl → adversarial → independent break attempts (three identical gates)."""
    root_path = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    payload = bind_all_components()

    pass_1 = verify_live_e2e_binding(root=root_path, payload=payload)
    pass_2 = verify_live_e2e_binding(root=root_path, payload=payload)
    pass_3 = verify_live_e2e_binding(root=root_path, payload=payload)
    bans = run_hard_ban_three(root_path)

    counters_match = (
        pass_1["counters"] == pass_2["counters"] == pass_3["counters"]
    )
    all_pass = (
        pass_1["status"] == "PASS"
        and pass_2["status"] == "PASS"
        and pass_3["status"] == "PASS"
        and bans["ok"]
        and counters_match
    )

    return {
        "three_pass_status": "PASS" if all_pass else "FAIL",
        "recommendation": PASS_RECOMMENDATION if all_pass else FAIL_RECOMMENDATION,
        "pass_count": 3,
        "pass_1": pass_1,
        "pass_2": pass_2,
        "pass_3": pass_3,
        "hard_ban_passes": bans,
        "counters_match": counters_match,
        "observed": pass_1["counters"],
        "required": {
            "hardcoded_live_value_count": 0,
            "fabricated_live_value_count": 0,
            "stale_without_indicator_count": 0,
            "unavailable_shown_as_zero_count": 0,
        },
        "component_count": payload.get("component_count"),
        "status_json_written": False,
    }
