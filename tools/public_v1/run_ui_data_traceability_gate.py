#!/usr/bin/env python3
"""PUB-G two-pass UI data traceability gate. Prints JSON to stdout. No *_status.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_public_ui_trace.ast_guard import scan_forbidden_imports
from backend.nexus_public_ui_trace.bindings import binding_rows, catalog_component_count
from backend.nexus_public_ui_trace.constants import (
    BASE_HEAD,
    BRANCH,
    HARD_BANS,
    LANE,
    PROGRAM_ID,
)
from backend.nexus_public_ui_trace.two_pass import run_two_pass_verification


def main() -> int:
    result = run_two_pass_verification(mode="LIVE")
    violations = scan_forbidden_imports(ROOT)
    payload = {
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "branch": BRANCH,
        "base_head": BASE_HEAD,
        "hard_bans": list(HARD_BANS),
        "component_count": catalog_component_count(),
        "binding_row_count": len(binding_rows()),
        "ast_forbidden_import_count": len(violations),
        "ast_violations": violations,
        "two_pass": result,
        "visible_mock_value_count": result["observed"]["visible_mock_value_count"],
        "unmapped_live_component_count": result["observed"]["unmapped_live_component_count"],
        "private_field_binding_count": result["observed"]["private_field_binding_count"],
        "stale_without_indicator": result["observed"]["stale_without_indicator"],
        "unavailable_fabrication": result["observed"]["unavailable_fabrication"],
        "status_json_written": False,
    }
    ok = (
        result["two_pass_status"] == "PASS"
        and payload["ast_forbidden_import_count"] == 0
        and payload["visible_mock_value_count"] == 0
        and payload["unmapped_live_component_count"] == 0
        and payload["private_field_binding_count"] == 0
        and payload["stale_without_indicator"] == 0
        and payload["unavailable_fabrication"] == 0
    )
    payload["gate_status"] = "PASS" if ok else "FAIL"
    payload["recommendation"] = result["recommendation"]
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
