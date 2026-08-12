"""Immutable artifact + runtime status writers for V14-E."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_cost_sensitivity.constants import (
    ARTIFACT_DIRNAME,
    BASE_COMMIT,
    BRANCH,
    CAMPAIGN_ID,
    LANE,
    SCHEMA,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head(root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "UNKNOWN"


def write_immutable_artifacts(
    report: dict[str, Any],
    adversarial: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Path]:
    out_dir = root / "artifacts" / "readiness" / "immutable" / ARTIFACT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = build_status_payload(report, adversarial, root=root)
    paths = {
        "campaign_report": out_dir / "campaign_report.json",
        "adversarial_review": out_dir / "adversarial_review.json",
        "status": out_dir / "status.json",
        "scenario_catalog": out_dir / "scenario_catalog.json",
        "label_histogram": out_dir / "label_histogram.json",
        "blockers": out_dir / "blockers.json",
        "candidate_metrics": out_dir / "candidate_metrics.json",
        "README": out_dir / "README.md",
    }
    paths["campaign_report"].write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["adversarial_review"].write_text(
        json.dumps(adversarial, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["status"].write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["scenario_catalog"].write_text(
        json.dumps(report.get("scenario_catalog") or [], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["label_histogram"].write_text(
        json.dumps(report.get("label_histogram") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["blockers"].write_text(
        json.dumps(report.get("blockers") or [], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    slim_candidates = [
        {
            "candidate_id": c.get("candidate_id"),
            "mechanism_family": c.get("mechanism_family"),
            "label": c.get("label"),
            "gross_expectancy": c.get("gross_expectancy"),
            "net_expectancy": c.get("net_expectancy"),
            "break_even_cost": c.get("break_even_cost"),
            "maximum_viable_spread": c.get("maximum_viable_spread"),
            "maximum_viable_slippage": c.get("maximum_viable_slippage"),
            "capacity_estimate": c.get("capacity_estimate"),
            "fragility_score": c.get("fragility_score"),
            "cost_components": c.get("cost_components"),
        }
        for c in report.get("candidates") or []
    ]
    paths["candidate_metrics"].write_text(
        json.dumps(slim_candidates, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["README"].write_text(
        "\n".join(
            [
                "# V14-E Cost and Execution Sensitivity Lab",
                "",
                "Development / synthetic / non-OOS only.",
                "Consumes canonical cost authority; does not mutate CostBridge formulas.",
                "No formal Walk-forward, no OOS consumption, no Demo, no qualification claims.",
                "No auto-integrate into PR #27.",
                f"qualification_ready_count={summary.get('qualification_ready_count')}",
                f"canonical_cost_authority={summary.get('canonical_cost_authority')}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return paths


def build_status_payload(
    report: dict[str, Any],
    adversarial: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    head = _git_head(root)
    return {
        "schema": SCHEMA,
        "lane": LANE,
        "campaign": CAMPAIGN_ID,
        "status": "NEXUS_V14_E_COST_SENSITIVITY_PASS"
        if adversarial.get("pass_ok")
        else "NEXUS_V14_E_COST_SENSITIVITY_BLOCKED",
        "pass": bool(adversarial.get("pass_ok")),
        "created_at": _utc(),
        "lane_head": head,
        "base_sha": BASE_COMMIT,
        "branch": BRANCH,
        "worktree": str(root),
        "candidate_count": report.get("candidate_count"),
        "scenario_point_count": report.get("scenario_point_count"),
        "sensitivity_dimensions": report.get("sensitivity_dimensions"),
        "cost_destroyed_count": report.get("cost_destroyed_count"),
        "fragile_to_execution_count": report.get("fragile_to_execution_count"),
        "capacity_limited_count": report.get("capacity_limited_count"),
        "cost_sensitivity_observed_count": report.get("cost_sensitivity_observed_count"),
        "qualification_ready_count": report.get("qualification_ready_count"),
        "label_histogram": report.get("label_histogram"),
        "required_cost_components": report.get("required_cost_components"),
        "required_output_keys": report.get("required_output_keys"),
        "cost_model_version": report.get("cost_model_version"),
        "canonical_cost_authority": report.get("canonical_cost_authority"),
        "canonical_cost_authority_count": report.get("canonical_cost_authority_count"),
        "canonical_cost_formula_mutated": False,
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
        "hard_bans": report.get("hard_bans"),
        "blockers": report.get("blockers"),
        "adversarial_remaining_count": adversarial.get("remaining_count"),
        "adversarial_pass_ok": adversarial.get("pass_ok"),
        "pass_id": report.get("pass_id"),
        "code_checksum": report.get("code_checksum"),
    }


def write_runtime_status(
    summary: dict[str, Any],
    *,
    runtime_root: Path,
) -> Path:
    path = runtime_root / "v14_e_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
