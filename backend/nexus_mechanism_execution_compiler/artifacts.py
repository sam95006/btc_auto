"""Immutable artifact writers for V15-B — never writes *_status.json."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_mechanism_execution_compiler.constants import (
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


def build_summary_payload(
    report: dict[str, Any],
    adversarial_passes: list[dict[str, Any]],
    *,
    root: Path,
) -> dict[str, Any]:
    head = _git_head(root)
    pass_ok = all(bool(p.get("pass_ok")) for p in adversarial_passes)
    return {
        "schema": SCHEMA,
        "lane": "V15-B",
        "campaign": "MECHANISM_EXECUTION_COMPILER",
        "status": "NEXUS_V15_B_MECH_COMPILER_PASS" if pass_ok else "NEXUS_V15_B_MECH_COMPILER_BLOCKED",
        "pass": pass_ok,
        "pass_1_ok": bool(adversarial_passes[0].get("pass_ok")) if adversarial_passes else False,
        "pass_2_ok": bool(adversarial_passes[1].get("pass_ok")) if len(adversarial_passes) > 1 else False,
        "created_at": _utc(),
        "lane_head": head,
        "base_sha": BASE_SHA,
        "branch": BRANCH,
        "worktree": str(root),
        "mechanism_executor_count": report.get("mechanism_executor_count"),
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
        "critical_remaining": sum(int(p.get("critical_remaining") or 0) for p in adversarial_passes),
        "high_remaining": sum(int(p.get("high_remaining") or 0) for p in adversarial_passes),
        "code_checksum": report.get("code_checksum"),
        "campaign_digest": report.get("campaign_digest"),
        "non_claims": report.get("non_claims"),
        "data_lineage": report.get("data_lineage"),
        "status_json_written": False,
    }


def write_immutable_artifacts(
    report: dict[str, Any],
    adversarial_passes: list[dict[str, Any]],
    *,
    root: Path,
) -> dict[str, Path]:
    """Write campaign evidence artifacts. Explicitly does NOT write *_status.json."""
    out_dir = root / "artifacts" / "readiness" / "immutable" / ARTIFACT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary_payload(report, adversarial_passes, root=root)

    # Guard: refuse any path ending with _status.json
    forbidden = list(out_dir.glob("*_status.json")) + list(out_dir.glob("status.json"))
    for path in forbidden:
        path.unlink(missing_ok=True)

    paths = {
        "campaign_report": out_dir / "campaign_report.json",
        "adversarial_pass_1": out_dir / "adversarial_pass_1.json",
        "adversarial_pass_2": out_dir / "adversarial_pass_2.json",
        "campaign_summary": out_dir / "campaign_summary.json",
        "executor_catalog": out_dir / "executor_catalog.json",
        "label_histogram": out_dir / "label_histogram.json",
        "blockers": out_dir / "blockers.json",
        "README": out_dir / "README.md",
    }
    for key, path in paths.items():
        if key != "README" and path.name.endswith("_status.json"):
            raise RuntimeError(f"refused_status_json_path:{path}")

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
    paths["campaign_summary"].write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["executor_catalog"].write_text(
        json.dumps(report.get("executor_catalog") or [], indent=2, sort_keys=True) + "\n",
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
                "# V15-B Mechanism Execution Compiler",
                "",
                "Development-only deterministic executors compiled from V14-C mechanisms.",
                "No edge, profitability, or qualification claims.",
                "No formal walk-forward, Demo, exchange write, or auto-integrate.",
                "This lane does NOT write *_status.json report files.",
                f"mechanism_executor_count={summary.get('mechanism_executor_count')}",
                f"qualification_ready_count={summary.get('qualification_ready_count')}",
                f"campaign_digest={summary.get('campaign_digest')}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Final guard after write.
    leftover = [p.name for p in out_dir.glob("*status*.json")]
    if leftover:
        raise RuntimeError(f"status_json_leak:{leftover}")
    return paths
