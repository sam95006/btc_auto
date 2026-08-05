"""V14-E Cost and Execution Sensitivity Lab campaign runner."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.nexus_cost_sensitivity.classifier import (
    classify_candidate,
    enforce_no_qualification,
    label_histogram,
)
from backend.nexus_cost_sensitivity.constants import (
    ARTIFACT_DIRNAME,
    BASE_COMMIT,
    BRANCH,
    CAMPAIGN_ID,
    CANONICAL_COST_AUTHORITY,
    HARD_BANS,
    LANE,
    OWNED_PATHS,
    RANDOM_SEED,
    REQUIRED_COST_COMPONENTS,
    REQUIRED_OUTPUT_KEYS,
    SCHEMA,
    SENSITIVITY_DIMENSIONS,
)
from backend.nexus_cost_sensitivity.cost_consumer import assert_canonical_authority
from backend.nexus_cost_sensitivity.fixtures import (
    build_synthetic_candidates,
    candidate_as_dict,
)
from backend.nexus_cost_sensitivity.metrics import analyze_candidate
from backend.nexus_cost_sensitivity.scenarios import (
    assert_all_dimensions_covered,
    scenario_catalog,
)


def _module_checksum() -> str:
    root = Path(__file__).resolve().parent
    parts: list[str] = []
    for path in sorted(root.glob("*.py")):
        parts.append(path.name)
        parts.append(path.read_text(encoding="utf-8"))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def run_cost_sensitivity_lab(*, pass_id: int = 1) -> dict[str, Any]:
    """Run synthetic development cost/execution sensitivity campaign."""
    if pass_id not in (1, 2):
        raise ValueError("pass_id must be 1 or 2")

    authority = assert_canonical_authority()
    assert_all_dimensions_covered()
    candidates_raw = build_synthetic_candidates(seed=RANDOM_SEED)

    analyzed: list[dict[str, Any]] = []
    for cand in candidates_raw:
        result = analyze_candidate(cand)
        # Inject data-quality blocked fixture for negative-path coverage.
        if cand.candidate_id == "C08":
            result["data_quality_blocked"] = True
        label = classify_candidate(result)
        public = {
            **candidate_as_dict(cand),
            "label": label,
            "status": "DEVELOPMENT_REVIEW_ONLY",
            "qualified": False,
            "qualification_ready": False,
            "profitability_claimed": False,
            "qualified_claimed": False,
            "gross_expectancy": result["gross_expectancy"],
            "cost_components": result["cost_components"],
            "net_expectancy": result["net_expectancy"],
            "break_even_cost": result["break_even_cost"],
            "maximum_viable_spread": result["maximum_viable_spread"],
            "maximum_viable_slippage": result["maximum_viable_slippage"],
            "capacity_estimate": result["capacity_estimate"],
            "fragility_score": result["fragility_score"],
            "fragility_detail": result["fragility_detail"],
            "baseline": result["baseline"],
            "dimension_summaries": result["dimension_summaries"],
            "scenario_count": result["scenario_count"],
            "scenario_evaluations": result["scenario_evaluations"],
            "spread_probe": result["spread_probe"],
            "slippage_probe": result["slippage_probe"],
            "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
            "formal_walk_forward_executed": False,
            "oos_executed": False,
            "cost_authority": CANONICAL_COST_AUTHORITY,
            "cost_model_version": authority["cost_model_version"],
            "canonical_cost_formula_mutated": False,
            "required_outputs_present": all(k in result for k in REQUIRED_OUTPUT_KEYS),
        }
        analyzed.append(public)

    qrc = enforce_no_qualification(analyzed)
    hist = label_histogram(analyzed)

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "lane": LANE,
        "campaign_id": CAMPAIGN_ID,
        "pass_id": pass_id,
        "branch": BRANCH,
        "base_sha": BASE_COMMIT,
        "random_seed": RANDOM_SEED,
        "owned_paths": list(OWNED_PATHS),
        "artifact_dirname": ARTIFACT_DIRNAME,
        "sensitivity_dimensions": list(SENSITIVITY_DIMENSIONS),
        "scenario_catalog": scenario_catalog(),
        "scenario_point_count": len(scenario_catalog()),
        "required_output_keys": list(REQUIRED_OUTPUT_KEYS),
        "required_cost_components": list(REQUIRED_COST_COMPONENTS),
        "cost_model_version": authority["cost_model_version"],
        "cost_model_schema": authority["cost_model_schema"],
        "canonical_cost_authority": authority["canonical_cost_authority"],
        "canonical_cost_authority_count": authority["canonical_cost_authority_count"],
        "canonical_cost_formula_mutated": False,
        "candidate_count": len(analyzed),
        "candidates": analyzed,
        "label_histogram": hist,
        "qualification_ready_count": qrc,
        "cost_destroyed_count": hist.get("COST_DESTROYED", 0),
        "fragile_to_execution_count": hist.get("FRAGILE_TO_EXECUTION", 0),
        "capacity_limited_count": hist.get("CAPACITY_LIMITED", 0),
        "cost_sensitivity_observed_count": hist.get("COST_SENSITIVITY_OBSERVED", 0),
        "insufficient_sample_count": hist.get("INSUFFICIENT_SAMPLE", 0),
        "data_quality_blocked_count": hist.get("DATA_QUALITY_BLOCKED", 0),
        "development_review_only_count": hist.get("DEVELOPMENT_REVIEW_ONLY", 0),
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mainnet_client_created_count": 0,
        "profitability_claimed": False,
        "qualified_claimed": False,
        "pr27_merge_attempted": False,
        "auto_integrate_attempted": False,
        "hard_bans": sorted(HARD_BANS),
        "code_checksum": _module_checksum(),
        "blockers": [
            {
                "blocker_id": "QUALIFICATION_NOT_AUTHORIZED",
                "detail": "qualification_ready_count forced 0; research labels only",
            },
            {
                "blocker_id": "OOS_AND_FORMAL_WF_BANNED",
                "detail": "lab uses synthetic development fixtures only",
            },
            {
                "blocker_id": "NO_CANONICAL_COST_FORMULA_MUTATION",
                "detail": "consumes backend.nexus_execution.cost_model; impact is labeled research approx",
            },
            {
                "blocker_id": "NO_AUTO_INTEGRATE",
                "detail": "lane does not merge into PR #27 or parent tip",
            },
        ],
    }
    return report
