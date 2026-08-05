"""Immutable artifact + runtime status writers for V14-C Mechanism Lab V4."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_mechanism_lab_v4.constants import (
    ARTIFACT_DIRNAME,
    BASE_SHA,
    BRANCH,
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


def build_status_payload(
    report: dict[str, Any],
    adversarial_passes: list[dict[str, Any]],
    *,
    root: Path,
) -> dict[str, Any]:
    head = _git_head(root)
    pass_ok = all(bool(p.get("pass_ok")) for p in adversarial_passes)
    return {
        "schema": SCHEMA,
        "lane": "V14-C",
        "campaign": "STRATEGY_MECHANISM_LAB_V4",
        "status": "NEXUS_V14_C_MECHANISM_LAB_PASS" if pass_ok else "NEXUS_V14_C_MECHANISM_LAB_BLOCKED",
        "pass": pass_ok,
        "pass_1_ok": bool(adversarial_passes[0].get("pass_ok")) if adversarial_passes else False,
        "pass_2_ok": bool(adversarial_passes[1].get("pass_ok")) if len(adversarial_passes) > 1 else False,
        "created_at": _utc(),
        "lane_head": head,
        "base_sha": BASE_SHA,
        "branch": BRANCH,
        "worktree": str(root),
        "mechanism_count": report.get("mechanism_count"),
        "mechanism_family_count": report.get("mechanism_family_count"),
        "qualification_ready_count": 0,
        "edge_claim_count": 0,
        "profitability_claim_count": 0,
        "label_histogram": report.get("label_histogram"),
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mainnet_touch_count": 0,
        "profitability_claimed": False,
        "edge_claimed": False,
        "qualified_claimed": False,
        "pr27_merge_attempted": False,
        "auto_integrate_attempted": False,
        "auto_integrate": False,
        "hard_bans": report.get("hard_bans"),
        "blockers": report.get("blockers"),
        "adversarial_remaining_count": sum(int(p.get("remaining_count") or 0) for p in adversarial_passes),
        "code_checksum": report.get("code_checksum"),
        "non_claims": report.get("non_claims"),
        "data_lineage": (report.get("data_lineage") or {}).get("data_lineage"),
    }


def write_immutable_artifacts(
    report: dict[str, Any],
    adversarial_passes: list[dict[str, Any]],
    *,
    root: Path,
) -> dict[str, Path]:
    out_dir = root / "artifacts" / "readiness" / "immutable" / ARTIFACT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_status_payload(report, adversarial_passes, root=root)
    paths = {
        "campaign_report": out_dir / "campaign_report.json",
        "adversarial_pass_1": out_dir / "adversarial_pass_1.json",
        "adversarial_pass_2": out_dir / "adversarial_pass_2.json",
        "status": out_dir / "status.json",
        "mechanism_catalog": out_dir / "mechanism_catalog.json",
        "label_histogram": out_dir / "label_histogram.json",
        "blockers": out_dir / "blockers.json",
        "README": out_dir / "README.md",
    }
    paths["campaign_report"].write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    p1 = adversarial_passes[0] if adversarial_passes else {}
    p2 = adversarial_passes[1] if len(adversarial_passes) > 1 else {}
    paths["adversarial_pass_1"].write_text(
        json.dumps(p1, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["adversarial_pass_2"].write_text(
        json.dumps(p2, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["status"].write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["mechanism_catalog"].write_text(
        json.dumps(report.get("mechanism_catalog") or [], indent=2, sort_keys=True) + "\n",
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
                "# V14-C Strategy Mechanism Lab V4",
                "",
                "Synthetic / development / non-OOS only.",
                "No edge, profitability, or qualification claims.",
                "No formal walk-forward, Demo, exchange write, or auto-integrate.",
                f"mechanism_count={summary.get('mechanism_count')}",
                f"qualification_ready_count={summary.get('qualification_ready_count')}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return paths


def write_runtime_status(
    summary: dict[str, Any],
    *,
    runtime_root: Path,
) -> Path:
    path = runtime_root / "v14_c_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
