"""Scan member-facing subscription surfaces for execution-control exposures.

Exit 0 when member_execution_control_count == 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_public_subscription_boundary.constants import (  # noqa: E402
    MEMBER_BUYABLE_PRODUCT_IDS,
)
from backend.nexus_public_subscription_boundary.execution_control import (  # noqa: E402
    count_member_execution_controls,
)
from backend.nexus_public_subscription_boundary.nav import (  # noqa: E402
    MOBILE_NAV_PRODUCT_MAP,
    WEB_NAV_PRODUCT_MAP,
)
from backend.nexus_public_subscription_boundary.service import (  # noqa: E402
    SubscriptionBoundaryService,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    args = parser.parse_args()

    svc = SubscriptionBoundaryService()
    foundation = svc.foundation_status()
    scan = count_member_execution_controls(
        buyable_catalog=MEMBER_BUYABLE_PRODUCT_IDS,
        entitled_products=MEMBER_BUYABLE_PRODUCT_IDS,
        nav_destinations=list(WEB_NAV_PRODUCT_MAP.values())
        + list(MOBILE_NAV_PRODUCT_MAP.values()),
        audit_granted_products=[],
    )
    payload = {
        "scanner": "tools/public/scan_member_execution_controls.py",
        "scanner_version": "pub17-d-v1",
        "member_execution_control_count": scan["member_execution_control_count"],
        "survivors": scan["survivors"],
        "status": scan["status"],
        "foundation_count": foundation["member_execution_control_count"],
        "live_billing_enabled": False,
        "pr26_merged": False,
        "pr27_merged": False,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"member_execution_control_count={payload['member_execution_control_count']} "
            f"status={payload['status']}"
        )
    return 0 if payload["member_execution_control_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
