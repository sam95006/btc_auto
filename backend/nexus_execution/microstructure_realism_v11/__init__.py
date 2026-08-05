"""NEXUS V11 Execution Microstructure Realism — public facade (Lane B).

Extends simulated execution realism with synthetic order-book microstructure
while preserving a single canonical fill authority:

  backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11

routed via NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1.

Execution mode: SIMULATED_NO_EXCHANGE_WRITE.
Fill accuracy claim: SIMULATED_ONLY — no verified historical book accuracy.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import backend.nexus_execution.security_boundary as security_boundary
from backend.nexus_execution.book_model_v11 import BOOK_MODEL_VERSION, FILL_ACCURACY_CLAIM
from backend.nexus_execution.microstructure_realism_v11.adapter import (
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
    MicrostructureExecutionAdapterV11,
)
from backend.nexus_execution.microstructure_realism_v11.config import (
    DEFAULT_SCENARIOS,
    MicroConfig,
    load_micro_config,
)
from backend.nexus_execution.microstructure_realism_v11.harness import (
    HARNESS_VERSION,
    run_microstructure_harness,
)
from backend.nexus_execution.microstructure_realism_v11.scenarios import SCENARIO_KINDS

MICRO_SCHEMA = "v11_execution_microstructure_realism"
MICRO_PACKAGE = "NEXUS_V11_EXECUTION_MICROSTRUCTURE_REALISM"
PASS_STATUS = "NEXUS_V11_EXECUTION_MICROSTRUCTURE_REALISM_PASS"
INVALID_PREFIX = "NEXUS_V11_EXECUTION_MICROSTRUCTURE_REALISM_INVALID"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_microstructure_campaign(*, config: MicroConfig | None = None) -> dict[str, Any]:
    """Run the microstructure realism campaign and return a JSON-ready report."""
    security_boundary.reset_counters()
    cfg = config or load_micro_config()
    report = run_microstructure_harness(config=cfg)
    payload = report.as_dict()
    payload["recommendation"] = (
        PASS_STATUS if report.pass_ else f"{INVALID_PREFIX}:FUZZ_INVARIANTS"
    )
    payload["scenario_kind_count"] = len(SCENARIO_KINDS)
    payload["scenario_kinds"] = list(SCENARIO_KINDS)
    return payload


def write_microstructure_artifacts(
    out_dir: Path,
    *,
    campaign: dict[str, Any],
    secret_scan: dict[str, Any] | None = None,
    pass_number: int = 1,
) -> dict[str, Path]:
    """Persist immutable readiness artifacts under ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def _write(name: str, obj: object) -> Path:
        path = out_dir / name
        path.write_text(
            json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        paths[name] = path
        return path

    _write("fuzz_summary.json", campaign)
    if secret_scan is not None:
        _write("secret_scan.json", secret_scan)

    campaign_pass = bool(campaign.get("pass"))
    secret_pass = True if secret_scan is None else int(secret_scan.get("secret_leak_count", 0)) == 0
    write_ok = int(campaign.get("exchange_write_attempt_count", 1)) == 0
    count_ok = int(campaign.get("generated_execution_scenario_count", 0)) == int(
        campaign.get("target_scenarios", -1)
    )
    all_pass = campaign_pass and secret_pass and write_ok and count_ok

    status = {
        "schema": MICRO_SCHEMA,
        "package": MICRO_PACKAGE,
        "status": PASS_STATUS if all_pass else f"{INVALID_PREFIX}:AGGREGATE",
        "pass_number": pass_number,
        "adapter_id": ADAPTER_ID,
        "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
        "canonical_execution_engine_count": CANONICAL_EXECUTION_ENGINE_COUNT,
        "book_model_version": campaign.get("book_model_version", BOOK_MODEL_VERSION),
        "harness_version": campaign.get("harness_version", HARNESS_VERSION),
        "fill_accuracy_claim": campaign.get("fill_accuracy_claim", FILL_ACCURACY_CLAIM),
        "fuzz_scenarios_achieved": campaign.get("generated_execution_scenario_count"),
        "fuzz_scenarios_target": campaign.get("target_scenarios", DEFAULT_SCENARIOS),
        "fuzz_pass": campaign_pass,
        "secret_scan_pass": secret_pass,
        "exchange_write_attempt_count": campaign.get("exchange_write_attempt_count", 0),
        "demo_order_count": campaign.get("demo_order_count", 0),
        "mainnet": False,
        "real_money": False,
        "mode": campaign.get("mode", "FULL"),
        "execution_mode": "SIMULATED_NO_EXCHANGE_WRITE",
        "created_at": _utc(),
    }
    _write("microstructure_status.json", status)

    readiness = {
        "schema": f"{MICRO_SCHEMA}_readiness",
        "package": MICRO_PACKAGE,
        "recommendation": status["status"],
        "pass_number": pass_number,
        "fuzz": {
            "generated_execution_scenario_count": campaign.get("generated_execution_scenario_count"),
            "target_scenarios": campaign.get("target_scenarios"),
            "invariants": campaign.get("invariants"),
            "latency_summary": campaign.get("latency_summary"),
            "pass": campaign_pass,
        },
        "secret_scan": secret_scan,
        "exchange_write_attempt_count": status["exchange_write_attempt_count"],
        "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
        "adapter_id": ADAPTER_ID,
        "fill_accuracy_claim": status["fill_accuracy_claim"],
        "generated_at": _utc(),
    }
    _write("readiness_report.json", readiness)

    contracts = {
        "schema": f"{MICRO_SCHEMA}_contracts",
        "book_model_version": BOOK_MODEL_VERSION,
        "fill_accuracy_claim": FILL_ACCURACY_CLAIM,
        "contracts": [
            "order_book_snapshots",
            "top_of_book_spread",
            "depth_ladder",
            "queue_position_approximation",
            "market_impact",
            "latency_distribution",
            "partial_fill_progression",
            "cancel_replace_latency",
            "mark_index_divergence",
            "funding_timestamp",
            "liquidation_distance_degradation",
            "stale_book_rejection",
            "missing_book_rejection",
        ],
        "invariants": [
            "cost_bridge_exact",
            "position_qty_non_negative",
            "reduce_only_cannot_increase",
            "duplicate_intents_no_duplicate_exposure",
            "stale_or_missing_book_fail_closed",
            "no_candle_touch_equals_fill",
            "same_bar_ambiguity_adverse_first_or_blocked",
            "exchange_write_attempt_count_eq_0",
        ],
        "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
        "adapter_id": ADAPTER_ID,
    }
    _write("contracts_matrix.json", contracts)
    return paths


__all__ = [
    "ADAPTER_ID",
    "CANONICAL_EXECUTION_ENGINE",
    "CANONICAL_EXECUTION_ENGINE_COUNT",
    "DEFAULT_SCENARIOS",
    "INVALID_PREFIX",
    "MICRO_PACKAGE",
    "MICRO_SCHEMA",
    "MicrostructureExecutionAdapterV11",
    "PASS_STATUS",
    "load_micro_config",
    "run_microstructure_campaign",
    "write_microstructure_artifacts",
]
