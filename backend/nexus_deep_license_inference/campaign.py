"""Campaign runner for V17 deep license enforcement + public inference."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_deep_license_inference.constants import (
    ARTIFACT_REL,
    BRANCH,
    COVERAGE_AREAS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    NON_CLAIMS,
    PRIVATE_TIP_SHA,
    PROGRAM_ID,
    PUBLIC_BASE_SHA,
    SCHEMA_CAMPAIGN,
    SCHEMA_REDTEAM,
)
from backend.nexus_deep_license_inference.feature_repro_boundary import run_feature_repro_checks
from backend.nexus_deep_license_inference.hard_bans import hard_ban_inventory
from backend.nexus_deep_license_inference.inference_attacks import run_deep_inference_attacks
from backend.nexus_deep_license_inference.license_enforcement import run_license_enforcement_attacks
from backend.nexus_deep_license_inference.schema_fuzz import run_schema_fuzz_attacks


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_campaign() -> dict[str, Any]:
    license_r = run_license_enforcement_attacks()
    inference_r = run_deep_inference_attacks()
    schema_r = run_schema_fuzz_attacks()
    repro_r = run_feature_repro_checks()

    suites = {
        "license_enforcement": license_r,
        "public_inference": inference_r,
        "schema_fuzz": schema_r,
        "feature_repro_boundary": repro_r,
    }
    all_survivors: list[dict[str, Any]] = []
    attack_count = 0
    for suite in suites.values():
        attack_count += int(suite.get("attack_count", 0))
        for s in suite.get("survivors") or []:
            all_survivors.append(s)

    status = "PASS" if len(all_survivors) == 0 else "FAIL"
    return {
        "schema": SCHEMA_CAMPAIGN,
        "redteam_schema": SCHEMA_REDTEAM,
        "generated_at": utc_now(),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "program_id": PROGRAM_ID,
        "branch": BRANCH,
        "public_base_sha": PUBLIC_BASE_SHA,
        "private_tip_sha": PRIVATE_TIP_SHA,
        "coverage_areas": list(COVERAGE_AREAS),
        "hard_bans": list(HARD_BANS),
        "hard_ban_inventory": hard_ban_inventory(),
        "non_claims": list(NON_CLAIMS),
        "suites": suites,
        "attack_count": attack_count,
        "survivors": all_survivors,
        "survivor_count": len(all_survivors),
        "status": status,
    }


def write_campaign_artifacts(report: dict[str, Any], root: Path | None = None) -> Path:
    base = root or Path(__file__).resolve().parents[2]
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "deep_license_inference_campaign.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "schema": SCHEMA_REDTEAM,
        "status": report["status"],
        "survivor_count": report["survivor_count"],
        "survivors": report["survivors"],
        "attack_count": report["attack_count"],
        "coverage_areas": report["coverage_areas"],
        "generated_at": report["generated_at"],
    }
    (out_dir / "deep_license_inference_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
