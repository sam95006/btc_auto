"""Two-pass verification runner for PUB-G."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_ui_trace.bindings import LIVE_COMPONENT_BINDINGS
from backend.nexus_public_ui_trace.constants import FAIL_RECOMMENDATION, PASS_RECOMMENDATION
from backend.nexus_public_ui_trace.verifier import verify_ui_data_traceability


def run_two_pass_verification(*, mode: str = "LIVE") -> dict[str, Any]:
    """Run identical verification twice; both must PASS with matching counters."""
    pass_1 = verify_ui_data_traceability(LIVE_COMPONENT_BINDINGS, mode=mode)
    pass_2 = verify_ui_data_traceability(LIVE_COMPONENT_BINDINGS, mode=mode)

    counters_match = pass_1["counters"] == pass_2["counters"]
    both_pass = pass_1["status"] == "PASS" and pass_2["status"] == "PASS"
    ok = both_pass and counters_match

    return {
        "two_pass_status": "PASS" if ok else "FAIL",
        "recommendation": PASS_RECOMMENDATION if ok else FAIL_RECOMMENDATION,
        "pass_1": pass_1,
        "pass_2": pass_2,
        "counters_match": counters_match,
        "required": {
            "visible_mock_value_count": 0,
            "unmapped_live_component_count": 0,
            "private_field_binding_count": 0,
            "stale_without_indicator": 0,
            "unavailable_fabrication": 0,
        },
        "observed": pass_1["counters"],
    }
