"""Immutable artifact writers for V15-H — no *_status.json."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_risk_capacity.constants import (
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


def build_campaign_summary(
    report: dict[str, Any],
    adversarial: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    """Campaign summary payload — intentionally NOT written as *_status.json."""
    head = _git_head(root)
    return {
        "schema": SCHEMA,
        "lane": LANE,
        "campaign": CAMPAIGN_ID,
        "result": "NEXUS_V15_H_RISK_CAPACITY_PASS"
        if adversarial.get("pass_ok")
        else "NEXUS_V15_H_RISK_CAPACITY_BLOCKED",
        "pass": bool(adversarial.get("pass_ok")),
        "created_at": _utc(),
        "lane_head": head,
        "base_sha": BASE_COMMIT,
        "branch": BRANCH,
        "worktree": str(root),
        "candidate_count": report.get("candidate_count"),
        "scenario_point_count": report.get("scenario_point_count"),
        "review_dimensions": report.get("review_dimensions"),
        "cost_destroyed_count": report.get("cost_destroyed_count"),
        "fragile_to_execution_count": report.get("fragile_to_execution_count"),
        "capacity_limited_count": report.get("capacity_limited_count"),
        "concentration_blocked_count": report.get("concentration_blocked_count"),
        "drawdown_unsafe_count": report.get("drawdown_unsafe_count"),
        "liquidation_unsafe_count": report.get("liquidation_unsafe_count"),
        "risk_capacity_observed_count": report.get("risk_capacity_observed_count"),
        "data_quality_blocked_count": report.get("data_quality_blocked_count"),
        "qualification_ready_count": report.get("qualification_ready_count"),
        "strategy_promoted_count": report.get("strategy_promoted_count"),
        "ai_override_applied_count": report.get("ai_override_applied_count"),
        "ai_override_attempted_count": report.get("ai_override_attempted_count"),
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
        "status_json_written": False,
        "hard_bans": report.get("hard_bans"),
        "blockers": report.get("blockers"),
        "adversarial_remaining_count": adversarial.get("remaining_count"),
        "adversarial_pass_ok": adversarial.get("pass_ok"),
        "pass_id": report.get("pass_id"),
        "code_checksum": report.get("code_checksum"),
    }


FORBIDDEN_ARTIFACT_NAMES = frozenset(
    {
        "status.json",
        "lane_status.json",
        "v15_h_status.json",
        "runtime_status.json",
    }
)


def write_immutable_artifacts(
    report: dict[str, Any],
    adversarial: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Path]:
    out_dir = root / "artifacts" / "readiness" / "immutable" / ARTIFACT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)

    # Enforce hard ban: never write *_status.json
    for banned in FORBIDDEN_ARTIFACT_NAMES:
        banned_path = out_dir / banned
        if banned_path.exists():
            banned_path.unlink()

    summary = build_campaign_summary(report, adversarial, root=root)
    paths = {
        "campaign_report": out_dir / "campaign_report.json",
        "adversarial_review": out_dir / "adversarial_review.json",
        "campaign_summary": out_dir / "campaign_summary.json",
        "scenario_catalog": out_dir / "scenario_catalog.json",
        "label_histogram": out_dir / "label_histogram.json",
        "blockers": out_dir / "blockers.json",
        "candidate_metrics": out_dir / "candidate_metrics.json",
        "hard_ban_probes": out_dir / "hard_ban_probes.json",
        "README": out_dir / "README.md",
    }
    for name in paths:
        if paths[name].name in FORBIDDEN_ARTIFACT_NAMES or paths[name].name.endswith(
            "_status.json"
        ):
            raise RuntimeError(f"STATUS_JSON_ARTIFACT_BANNED:{paths[name].name}")

    paths["campaign_report"].write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["adversarial_review"].write_text(
        json.dumps(adversarial, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["campaign_summary"].write_text(
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
    paths["hard_ban_probes"].write_text(
        json.dumps(report.get("hard_ban_probes") or {}, indent=2, sort_keys=True) + "\n",
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
            "capacity_estimate": c.get("capacity_estimate"),
            "fragility_score": c.get("fragility_score"),
            "concentration_review": c.get("concentration_review"),
            "drawdown_review": c.get("drawdown_review"),
            "liquidation_distance_review": c.get("liquidation_distance_review"),
            "data_quality_review": c.get("data_quality_review"),
            "deterministic_fingerprint": c.get("deterministic_fingerprint"),
            "ai_override_attempted": c.get("ai_override_attempted"),
            "ai_override_applied": c.get("ai_override_applied"),
            "strategy_promoted": c.get("strategy_promoted"),
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
                "# V15-H Risk and Capacity Review Engine",
                "",
                "Development / synthetic / non-OOS only.",
                "Deterministic candidate review; AI cannot override results.",
                "No strategy promotion. No qualification claims.",
                "No *_status.json artifacts (hard ban).",
                f"qualification_ready_count={summary.get('qualification_ready_count')}",
                f"strategy_promoted_count={summary.get('strategy_promoted_count')}",
                f"ai_override_applied_count={summary.get('ai_override_applied_count')}",
                f"canonical_cost_authority={summary.get('canonical_cost_authority')}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return paths
