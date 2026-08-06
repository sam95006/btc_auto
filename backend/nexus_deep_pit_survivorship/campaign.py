"""Campaign orchestrator for V17 deep PIT / survivorship / collision attacks."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_deep_pit_survivorship.constants import (
    ARTIFACT_REL,
    BASE_SHA,
    BRANCH,
    COVERAGE_AREAS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    NON_CLAIMS,
    OWNED_PATHS,
    PACKAGE,
    PROGRAM_ID,
    SCHEMA,
    SCHEMA_CAMPAIGN,
    WORKTREE_PATH,
)
from backend.nexus_deep_pit_survivorship.future_leakage_expand import run_expanded_future_leakage_redteam
from backend.nexus_deep_pit_survivorship.hard_bans import hard_ban_inventory
from backend.nexus_deep_pit_survivorship.listing_delisting_attacks import run_listing_delisting_attacks
from backend.nexus_deep_pit_survivorship.property_attacks import (
    inject_mutated_revision_axes,
    run_mutation_as_known_at_campaign,
    run_property_as_known_at_campaign,
)
from backend.nexus_deep_pit_survivorship.symbol_collision_attacks import run_symbol_collision_attacks
from backend.nexus_deep_pit_survivorship.timestamp_edges import run_timestamp_edge_attacks
from backend.nexus_pit_revision_v17.fixtures import T0


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _git_head(repo_root: Path) -> str:
    head = repo_root / ".git"
    # worktree: .git may be a file
    try:
        import subprocess

        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), stderr=subprocess.DEVNULL, text=True
        )
        return out.strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def run_campaign(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(WORKTREE_PATH)
    property_report = run_property_as_known_at_campaign()
    mutation_report = run_mutation_as_known_at_campaign()
    axis_mutation = inject_mutated_revision_axes(as_known_at=T0 + 3 * 86_400_000)
    timestamp_report = run_timestamp_edge_attacks()
    collision_report = run_symbol_collision_attacks()
    listing_report = run_listing_delisting_attacks()
    leakage_report = run_expanded_future_leakage_redteam()

    sections = {
        "property_as_known_at": property_report,
        "mutation_as_known_at": mutation_report,
        "axis_mutation": axis_mutation,
        "timestamp_edges": timestamp_report,
        "symbol_collision": collision_report,
        "listing_delisting": listing_report,
        "future_leakage": leakage_report,
    }

    survivors: list[str] = []
    for name, section in sections.items():
        if name == "axis_mutation":
            if section.get("survivor"):
                survivors.append(section["attack_id"])
            continue
        if not section.get("pass", False):
            survivors.extend(section.get("survivors") or [])

    # Aggregate attack counts (expanded + deep only; base included inside leakage combined).
    attack_count = (
        int(mutation_report.get("attack_count") or 0)
        + int(timestamp_report.get("attack_count") or 0)
        + int(collision_report.get("attack_count") or 0)
        + int(listing_report.get("attack_count") or 0)
        + int(leakage_report.get("attack_count") or 0)
        + (1 if axis_mutation else 0)
    )
    blocked_count = (
        int(mutation_report.get("blocked_count") or 0)
        + int(timestamp_report.get("blocked_count") or 0)
        + int(collision_report.get("blocked_count") or 0)
        + int(listing_report.get("blocked_count") or 0)
        + int(leakage_report.get("blocked_count") or 0)
        + (1 if axis_mutation.get("blocked") else 0)
    )

    passed = len(survivors) == 0 and property_report.get("pass") and mutation_report.get("pass")
    head = _git_head(root)
    bans = hard_ban_inventory()

    report: dict[str, Any] = {
        "schema": SCHEMA_CAMPAIGN,
        "module_schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "program_id": PROGRAM_ID,
        "package": PACKAGE,
        "branch": BRANCH,
        "base": BASE_SHA,
        "HEAD": head,
        "worktree": str(root),
        "owned_paths": list(OWNED_PATHS),
        "coverage_areas": list(COVERAGE_AREAS),
        "hard_bans": list(HARD_BANS),
        "hard_ban_inventory": bans,
        "non_claims": list(NON_CLAIMS),
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "survivor_count": len(survivors),
        "survivors": survivors,
        "attack_count": attack_count,
        "blocked_count": blocked_count,
        "property_case_count": property_report.get("case_count"),
        "sections": sections,
        "fixture_only": True,
        "real_market_data": False,
        "exchange_write": False,
        "mainnet": False,
        "real_money": False,
        "formal_wf_executed": False,
        "oos_claimed": False,
        "pr26_touched": False,
        "pr27_touched": False,
        "report_edited": False,
        "exchange_write_attempt_count": 0,
        "mainnet_client_count": 0,
    }
    report["campaign_checksum"] = _sha_obj(
        {k: v for k, v in report.items() if k not in {"campaign_checksum", "sections"}}
    )
    return report


def write_artifacts(report: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, str]:
    root = repo_root or Path(WORKTREE_PATH)
    art = root / ARTIFACT_REL
    art.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    files = {
        "campaign.json": report,
        "property_as_known_at.json": report["sections"]["property_as_known_at"],
        "mutation_as_known_at.json": report["sections"]["mutation_as_known_at"],
        "timestamp_edges.json": report["sections"]["timestamp_edges"],
        "symbol_collision.json": report["sections"]["symbol_collision"],
        "listing_delisting.json": report["sections"]["listing_delisting"],
        "future_leakage.json": report["sections"]["future_leakage"],
        "summary.json": {
            "status": report["status"],
            "HEAD": report["HEAD"],
            "survivor_count": report["survivor_count"],
            "survivors": report["survivors"],
            "attack_count": report["attack_count"],
            "blocked_count": report["blocked_count"],
            "coverage_areas": report["coverage_areas"],
            "campaign_checksum": report["campaign_checksum"],
        },
    }
    sha_map: dict[str, str] = {}
    for name, payload in files.items():
        fp = art / name
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        fp.write_text(text, encoding="utf-8")
        paths[name] = str(fp)
        sha_map[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    (art / "sha256.json").write_text(
        json.dumps(sha_map, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["sha256.json"] = str(art / "sha256.json")
    return paths
