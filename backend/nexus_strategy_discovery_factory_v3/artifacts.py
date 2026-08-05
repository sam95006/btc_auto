"""Immutable artifact + runtime status writers for V13-C."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_strategy_discovery_factory_v3.constants import ARTIFACT_DIRNAME, SCHEMA


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
        "family_catalog": out_dir / "family_catalog.json",
        "label_histogram": out_dir / "label_histogram.json",
        "blockers": out_dir / "blockers.json",
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
    paths["family_catalog"].write_text(
        json.dumps(report.get("family_catalog") or [], indent=2, sort_keys=True) + "\n",
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
    paths["README"].write_text(
        "\n".join(
            [
                "# V13-C Cost-Aware Strategy Discovery Factory V3",
                "",
                "Development / synthetic / non-OOS only.",
                "No formal Walk-forward, no OOS consumption, no Demo, no qualification claims.",
                f"qualification_ready_count={summary.get('qualification_ready_count')}",
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
        "lane": "V13-C",
        "campaign": "COST_AWARE_STRATEGY_DISCOVERY_FACTORY_V3",
        "status": "NEXUS_V13_C_STRATEGY_DISCOVERY_PASS"
        if adversarial.get("pass_ok")
        else "NEXUS_V13_C_STRATEGY_DISCOVERY_BLOCKED",
        "pass": bool(adversarial.get("pass_ok")),
        "created_at": _utc(),
        "lane_head": head,
        "base_sha": "abd2195ef6d79f609dd261b5e9c5402599625a64",
        "branch": "feature/v13-strategy-discovery-factory-v3",
        "worktree": str(root),
        "mechanism_family_count": report.get("mechanism_family_count"),
        "candidate_configuration_count": report.get("candidate_configuration_count"),
        "development_promising_count": report.get("development_promising_count"),
        "cost_destroyed_count": report.get("cost_destroyed_count"),
        "rejected_count": report.get("rejected_count"),
        "qualification_ready_count": report.get("qualification_ready_count"),
        "label_histogram": report.get("label_histogram"),
        "required_cost_components": report.get("required_cost_components"),
        "cost_model_version": report.get("cost_model_version"),
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "profitability_claimed": False,
        "qualified_claimed": False,
        "pr27_merge_attempted": False,
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
    path = runtime_root / "v13_c_strategy_discovery_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
