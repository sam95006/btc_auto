"""100k-scenario execution fuzz scale wrapper over the V1.1 fuzz harness.

Canonical engine remains ``AutonomousExecutionSimulatorV11`` via the existing
``backend.nexus_execution.fuzz_harness`` ScenarioRunner (no second authority).
"""
from __future__ import annotations

from typing import Any

from backend.nexus_execution.fuzz_harness import FuzzReport, run_fuzz
from backend.nexus_execution.orchestrator_adapter_v1 import (
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
)
from backend.nexus_execution.scale_.config import ScaleConfig, load_scale_config


def run_execution_fuzz_scale(
    *,
    config: ScaleConfig | None = None,
    target_scenarios: int | None = None,
    seed: int | None = None,
) -> FuzzReport:
    """Run deterministic execution fuzz at the configured scale target."""
    cfg = config or load_scale_config()
    return run_fuzz(
        seed=cfg.fuzz_seed if seed is None else seed,
        target_scenarios=cfg.fuzz_scenarios if target_scenarios is None else target_scenarios,
    )


def fuzz_scale_summary(report: FuzzReport, *, config: ScaleConfig) -> dict[str, Any]:
    return {
        "schema": "v10_execution_session_scale_fuzz",
        "adapter_id": ADAPTER_ID,
        "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
        "canonical_execution_engine_count": CANONICAL_EXECUTION_ENGINE_COUNT,
        "mode": config.mode,
        "target_scenarios": config.fuzz_scenarios,
        "generated_execution_scenario_count": report.generated_execution_scenario_count,
        "seed": report.seed,
        "invariants": report.invariants,
        "scenario_kind_count": len(report.scenario_breakdown),
        "exchange_write_attempt_count": report.exchange_write_attempt_count,
        "demo_order_count": report.demo_order_count,
        "mainnet": report.mainnet,
        "real_money": report.real_money,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "pass": (
            report.invariants.get("scenarios_with_violations", 1) == 0
            and report.exchange_write_attempt_count == 0
            and report.generated_execution_scenario_count == config.fuzz_scenarios
        ),
    }


__all__ = ["fuzz_scale_summary", "run_execution_fuzz_scale"]
