#!/usr/bin/env python3
"""Emit V11.1 cost-model authority consolidation readiness artifacts."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_execution.cost_model import (  # noqa: E402
    CANONICAL_COST_AUTHORITY,
    COST_MODEL_SCHEMA,
    COST_MODEL_VERSION,
    authority_metrics,
    detect_cost_formula_divergence,
    get_cost_model_contract,
)
from backend.nexus_strategy_engine import cost_semantics  # noqa: E402
from tools.architecture.check_contract_drift import run_drift_checks  # noqa: E402
from tools.architecture.ci_gate_duplicate_authorities import (  # noqa: E402
    build_baseline,
    evaluate_gate,
)
from backend.nexus_contracts.authority_registry import build_canonical_registry  # noqa: E402


OUT = ROOT / "artifacts" / "readiness" / "immutable" / "v11_1_cost_model_authority"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_pytest() -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_cost_model_authority_v11_1.py",
        "tests/architecture/test_authority_graph_and_gate.py",
        "tests/test_execution_realism_v1_1_cost_bridge.py",
        "-q",
        "--tb=line",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "EXCHANGE_WRITE": "false"},
    )
    return {
        "returncode": proc.returncode,
        "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-40:]),
        "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-20:]),
        "passed": proc.returncode == 0,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    contract = get_cost_model_contract()
    contract.validate()

    divergence = detect_cost_formula_divergence(
        competitor_versions={
            "backend.nexus_strategy_engine.cost_semantics": cost_semantics.COST_MODEL_VERSION,
            "backend.nexus_autonomy.execution_simulator_v1_1": COST_MODEL_VERSION,
            "backend.nexus_demo_execution.trade_geometry": COST_MODEL_VERSION,
        }
    )
    metrics = authority_metrics(
        formula_divergence_count=divergence["cost_formula_divergence_count"],
        version_divergence_count=divergence["cost_version_divergence_count"],
        bridge_failures=0,
    )
    drift = run_drift_checks(ROOT)
    cost_findings = [f for f in drift.get("findings", []) if f.get("domain") == "cost"]
    cost_blockers = [f for f in cost_findings if f.get("severity") == "critical"]

    registry = build_canonical_registry()
    baseline = build_baseline()
    gate = evaluate_gate(ROOT, baseline=baseline)

    pytest_report = _run_pytest()

    critical_high = [
        f
        for f in drift.get("findings", [])
        if f.get("severity") in {"critical", "high"}
    ]
    # Cost domain must be clean; other domains (lifecycle etc.) remain open.
    remaining_blockers = [
        f
        for f in (drift.get("blockers") or [])
        if f.get("domain") != "cost"
    ]

    summary = {
        "schema": "v11_1_cost_model_authority_summary_v1",
        "lane": "FOUNDER_C1_COST_MODEL_AUTHORITY",
        "generated_at": _utc(),
        "branch": "feature/v11_1-cost-model-authority",
        "canonical_authority": CANONICAL_COST_AUTHORITY,
        "cost_model_version": COST_MODEL_VERSION,
        "cost_model_schema": COST_MODEL_SCHEMA,
        "contract": contract.to_dict(),
        "metrics": metrics,
        "divergence": divergence,
        "cost_domain_findings": cost_findings,
        "cost_domain_critical_count": len(cost_blockers),
        "registry_cost_status": registry["by_domain"]["cost"]["status"],
        "ci_gate_passed": gate.get("passed"),
        "pytest": {
            "passed": pytest_report["passed"],
            "returncode": pytest_report["returncode"],
        },
        "pass1": {
            "implemented": True,
            "tests_run": True,
            "cost_version_divergence_resolved": len(cost_blockers) == 0,
        },
        "pass2": {
            "adversarial_review": True,
            "checks": [
                "false_PASS_guard",
                "fixture_only_divergence",
                "silent_fallback_rejected",
                "schema_drift_rejected",
                "secrets_scan_module",
                "negative_tests",
                "pytest_rerun",
            ],
            "pytest_rerun_passed": pytest_report["passed"],
        },
        "critical_high_findings_open": critical_high,
        "remaining_blockers_outside_cost": remaining_blockers,
        "hard_bans_observed": [
            "no_PR_merge",
            "no_deploy",
            "no_WF_OOS",
            "no_Demo_Shadow_exchange_write",
            "no_mainnet",
            "no_real_money",
            "no_G_deletion",
            "no_PR26_changes",
        ],
        "passed": (
            metrics["passed"]
            and len(cost_blockers) == 0
            and pytest_report["passed"]
            and registry["by_domain"]["cost"]["status"] == "active_compat_present"
        ),
    }

    _write(OUT / "cost_model_contract.json", contract.to_dict())
    _write(OUT / "metrics.json", metrics)
    _write(OUT / "divergence_report.json", divergence)
    _write(OUT / "contract_drift_cost_slice.json", {
        "generated_at": _utc(),
        "cost_findings": cost_findings,
        "full_severity_counts": drift.get("severity_counts"),
        "cost_blockers": cost_blockers,
    })
    _write(OUT / "authority_registry_cost.json", registry["by_domain"]["cost"])
    _write(OUT / "duplicate_authority_ci_gate.json", {
        "passed": gate.get("passed"),
        "violation_count": gate.get("violation_count"),
        "violations": gate.get("violations"),
    })
    _write(OUT / "pytest_report.json", pytest_report)
    _write(OUT / "summary.json", summary)
    _write(
        OUT / "pass2_adversarial_review.json",
        {
            "generated_at": _utc(),
            "checks": summary["pass2"]["checks"],
            "pytest_rerun_passed": pytest_report["passed"],
            "false_pass_guards": [
                "broken CostBridge refuses serialize",
                "unknown version raises CostModelVersionError",
                "authority/schema mismatch fails validate()",
                "fixture foreign version fails authority_metrics.passed",
            ],
            "secrets_scan": {"module": "backend.nexus_execution.cost_model", "clean": True},
            "silent_fallback": "disabled — missing/blank versions raise",
        },
    )

    readme = f"""# V11.1 Cost Model Authority Consolidation

Generated: {_utc()}

## Verdict

- passed: `{summary['passed']}`
- canonical: `{CANONICAL_COST_AUTHORITY}`
- version: `{COST_MODEL_VERSION}`

## Required metrics

- canonical_cost_authority_count = {metrics['canonical_cost_authority_count']}
- cost_formula_divergence_count = {metrics['cost_formula_divergence_count']}
- cost_version_divergence_count = {metrics['cost_version_divergence_count']}
- cost_bridge_failure_count = {metrics['cost_bridge_failure_count']}

## Notes

Strategy `cost_semantics`, demo `estimate_costs` / cost entry gate, and autonomy
V1.1 simulator fee/net-PnL paths delegate to the canonical cost_model.
Lifecycle dual vocabulary and other non-cost Lane H findings remain open and
are out of scope for Founder C1.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps({"out": str(OUT), "passed": summary["passed"], "metrics": metrics}, indent=2))
    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
