"""10,000-scenario deterministic fuzz suite + readiness artifact generation."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_execution import security_boundary
from backend.nexus_execution.fuzz_harness import run_fuzz, write_readiness_artifacts


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_fuzz_10k_scenarios_pass_and_write_readiness():
    security_boundary.reset_counters()
    report = run_fuzz(seed=20260805, target_scenarios=10_000)

    assert report.generated_execution_scenario_count == 10_000
    assert report.invariants["scenarios_with_violations"] == 0, report.invariants
    assert report.exchange_write_attempt_count == 0
    assert report.demo_order_count == 0
    assert report.mainnet is False
    assert report.real_money is False
    # Every declared scenario kind must have executed at least once.
    from backend.nexus_execution.fuzz_harness import SCENARIO_KINDS
    for kind in SCENARIO_KINDS:
        assert kind in report.scenario_breakdown, f"missing scenario kind {kind}"
        assert report.scenario_breakdown[kind]["count"] > 0
        assert report.scenario_breakdown[kind]["invariant_violations"] == 0, kind
    # Cost bridge samples all reconcile.
    assert report.cost_bridge_sample
    for sample in report.cost_bridge_sample:
        assert sample["cost_bridge_ok"] is True

    paths = write_readiness_artifacts(REPO_ROOT, report=report)
    for path in paths.values():
        assert path.is_file(), path
    # Structural sanity on the readiness_report.json.
    readiness = json.loads(paths["readiness_report"].read_text(encoding="utf-8"))
    assert readiness["recommendation"] == "NEXUS_EXECUTION_SIMULATOR_V11_PASS"
    assert readiness["generated_execution_scenario_count"] == 10_000
    assert readiness["exchange_write_attempt_count"] == 0
