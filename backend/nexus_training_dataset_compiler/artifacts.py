"""Immutable artifact writers for V17-H Training Dataset Compiler."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_training_dataset_compiler.constants import (
    ARTIFACT_DIRNAME,
    BASE_SHA,
    BRANCH,
    HARD_BANS,
    LANE,
    NON_CLAIMS,
    PACKAGE,
    SCHEMA,
)
from backend.nexus_training_dataset_compiler.compiler import compile_campaign
from backend.nexus_training_dataset_compiler.redteam import run_contamination_redteam


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_summary_payload(
    campaign: dict[str, Any],
    redteam: dict[str, Any],
    *,
    root: Path,
    head: str | None = None,
) -> dict[str, Any]:
    status = "PASS" if (
        campaign.get("contamination_survivors") == 0
        and redteam.get("survivor_count") == 0
        and redteam.get("status") == "PASS"
        and campaign.get("formal_walk_forward_executed") is False
        and campaign.get("untouched_oos_executed") is False
        and campaign.get("llm_sole_tick_consumer") is False
    ) else "FAIL"
    return {
        "schema": SCHEMA,
        "package": PACKAGE,
        "lane": LANE,
        "branch": BRANCH,
        "base_sha": BASE_SHA,
        "head": head,
        "generated_at": _utc_now(),
        "status": status,
        "sample_count": campaign.get("sample_count"),
        "trainable_count": campaign.get("trainable_count"),
        "reserved_count": campaign.get("reserved_count"),
        "by_split": campaign.get("by_split"),
        "by_target": campaign.get("by_target"),
        "campaign_digest": campaign.get("campaign_digest"),
        "hard_bans": sorted(HARD_BANS),
        "non_claims": list(NON_CLAIMS),
        "labels_only": True,
        "offline_benchmark_interface_ready": True,
        "llm_sole_tick_consumer": False,
        "formal_walk_forward_executed": False,
        "untouched_oos_executed": False,
        "real_promotion_executed": False,
        "real_lesson_activated": False,
        "mainnet_touched": False,
        "real_money_touched": False,
        "pr26_merge_attempted": False,
        "pr27_merge_attempted": False,
        "report_updated": False,
        "contamination_redteam": {
            "attack_count": redteam.get("attack_count"),
            "survivor_count": redteam.get("survivor_count"),
            "survivors": redteam.get("survivors"),
            "status": redteam.get("status"),
        },
        "worktree": str(root),
    }


def write_immutable_artifacts(
    campaign: dict[str, Any] | None = None,
    redteam: dict[str, Any] | None = None,
    *,
    root: Path,
    head: str | None = None,
) -> dict[str, Path]:
    campaign = campaign or compile_campaign(pass_id=3)
    redteam = redteam or run_contamination_redteam()
    summary = build_summary_payload(campaign, redteam, root=root, head=head)
    out_dir = root / "artifacts" / "readiness" / "immutable" / ARTIFACT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "summary": out_dir / "summary.json",
        "campaign": out_dir / "campaign.json",
        "contamination_redteam": out_dir / "contamination_redteam.json",
        "split_matrix": out_dir / "split_matrix.json",
        "schema": out_dir / "schema.json",
    }
    paths["summary"].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths["campaign"].write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths["contamination_redteam"].write_text(
        json.dumps(redteam, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["split_matrix"].write_text(
        json.dumps(
            {
                "schema": f"{SCHEMA}_split_matrix",
                "by_split": campaign.get("by_split"),
                "trainable_sample_ids": campaign.get("trainable_sample_ids"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["schema"].write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "splits": [
                    "DEVELOPMENT",
                    "VALIDATION",
                    "WALK_FORWARD_RESERVED",
                    "OOS_RESERVED",
                    "SHADOW",
                    "DEMO",
                    "REAL_PRIVATE",
                ],
                "target_labels": [
                    "REGIME",
                    "VOL_FORECAST",
                    "LIQUIDITY_STRESS",
                    "CANDIDATE_RANKING",
                    "STRATEGY_ROUTING",
                    "ABSTENTION",
                    "ERROR_CLASSIFICATION",
                    "COUNTERFACTUAL",
                ],
                "consumer_roles": ["NUMERIC_STAT_MODEL", "LLM_REASONER"],
                "llm_sole_tick_consumer": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    # Hard ban: never write *_status.json
    status_candidates = [
        Path(r"D:\NEXUS_RUNTIME") / "v17_h_status.json",
        root / "v17_h_status.json",
    ]
    for p in status_candidates:
        if p.exists():
            raise RuntimeError(f"status_json_must_not_exist:{p}")
    return paths
