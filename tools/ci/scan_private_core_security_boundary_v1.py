#!/usr/bin/env python3
"""CI scanner: fail build on Private Core security boundary violations."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")


def main() -> int:
    from backend.nexus_autonomy.security_import_graph_v1 import build_import_graph
    from backend.nexus_autonomy.security_boundary_v1 import evaluate_security_boundary

    graph = build_import_graph(root=ROOT)
    status = evaluate_security_boundary(root=ROOT)
    report = {
        "import_graph_passed": graph.to_dict().get("passed"),
        "violation_count": len(graph.violations),
        "recommendation": status.get("recommendation"),
        "exchange_write_attempt_count": status.get("exchange_write_attempt_count"),
        "secret_leak_count": status.get("secret_leak_count"),
    }
    print(json.dumps(report, indent=2))
    if graph.violations:
        return 2
    if status.get("recommendation") != "NEXUS_PRIVATE_SECURITY_BOUNDARY_V1_PASS":
        return 1
    if int(status.get("exchange_write_attempt_count") or 0) != 0:
        return 3
    if int(status.get("secret_leak_count") or 0) != 0:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
