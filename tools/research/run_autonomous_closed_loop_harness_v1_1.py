#!/usr/bin/env python3
"""Run Autonomous Closed-Loop Harness V1.1 and write immutable package."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/readiness/immutable/autonomous_closed_loop_harness_v1_1"


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    from backend.nexus_autonomy.closed_loop_harness_v1_1 import run_harness
    from backend.nexus_autonomy.process_classification import CANONICAL_CLASSES

    result = run_harness()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "closed_loop_harness_status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (OUT / "scenario_matrix_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (OUT / "state_machine_contract.json").write_text(
        json.dumps(
            {
                "canonical_classes": list(CANONICAL_CLASSES),
                "state_machine_status": result.get("state_machine_status"),
                "orphan_lifecycle_count": result.get("orphan_lifecycle_count"),
                "label": result.get("label"),
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "idempotency_result.json").write_text(
        json.dumps(
            {
                "cross_candidate_idempotency_status": result.get("cross_candidate_idempotency_status"),
                "duplicate_intent_idempotency_status": result.get("duplicate_intent_idempotency_status"),
                "orphan_lifecycle_count": result.get("orphan_lifecycle_count"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "taxonomy_result.json").write_text(
        json.dumps(
            {
                "BAD_PROCESS_WIN_test_status": result.get("BAD_PROCESS_WIN_test_status"),
                "UNDETERMINED_test_status": result.get("UNDETERMINED_test_status"),
                "canonical_classification_count": result.get("canonical_classification_count"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: result[k] for k in result if k != "scenarios"}, indent=2))
    return 0 if result.get("recommendation") == "NEXUS_AUTONOMOUS_HARNESS_V1_1_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
