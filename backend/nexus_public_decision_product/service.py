"""Public service surface for PUB2-A Decision Product E2E."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_decision_product.constants import HARD_BANS, LANE, LANE_NAME
from backend.nexus_public_decision_product.hard_bans import run_three_passes
from backend.nexus_public_decision_product.journey import journey_meta, run_customer_journey


def service_meta() -> dict[str, Any]:
    return journey_meta()


def run_e2e(*, decision_id: str | None = None) -> dict[str, Any]:
    return run_customer_journey(decision_id=decision_id)


def three_pass_report(root: str | None = None) -> dict[str, Any]:
    from pathlib import Path

    repo = Path(root) if root else Path(__file__).resolve().parents[2]
    report = run_three_passes(repo)
    report["lane"] = LANE
    report["lane_name"] = LANE_NAME
    report["hard_bans"] = list(HARD_BANS)
    return report
