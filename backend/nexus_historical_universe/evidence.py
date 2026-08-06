"""Evidence + immutable artifact writer for V17-E."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from backend.nexus_historical_universe.attacks import run_all_attacks
from backend.nexus_historical_universe.constants import (
    ARTIFACT_REL,
    ATTACK_IDS,
    BASE_COMMIT,
    BLOCKED_RECOMMENDATION,
    BRANCH,
    EVIDENCE_CLASS,
    EVIDENCE_PATH,
    EXECUTION_MODE,
    FAIL_RECOMMENDATION,
    FIXTURE_IDS,
    HARD_BANS,
    LABEL,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PROGRAM_ID,
    PROHIBITED_PATHS,
    SCHEMA,
    SCHEMA_VERSION,
    WORKTREE_PATH,
)
from backend.nexus_historical_universe.events import (
    build_contract_spec_timeline,
    build_listing_delisting_events,
)
from backend.nexus_historical_universe.fixture_proofs import run_all_fixtures
from backend.nexus_historical_universe.fixtures import fixture_catalog
from backend.nexus_historical_universe.hashutil import sha_obj, utc_now_iso
from backend.nexus_historical_universe.universe import reconstruct_universe
from backend.nexus_historical_universe.constants import (
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
)


def _git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def evaluate_lane(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(WORKTREE_PATH)
    head = _git_head(root)
    fixtures = run_all_fixtures()
    attacks = run_all_attacks()
    fixture_pass = sum(1 for f in fixtures if f.get("passed"))
    attack_blocked = sum(1 for a in attacks if a.get("attack_blocked"))
    attack_pass = sum(1 for a in attacks if a.get("passed"))
    survivors = [a["attack_id"] for a in attacks if a.get("survivor")]
    eras = {
        "ERA_2024_06_01_MS": reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED"),
        "ERA_2024_12_01_MS": reconstruct_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED"),
        "ERA_2025_03_01_MS": reconstruct_universe(ERA_2025_03_01_MS, retrieval_timestamp="FIXED"),
    }
    # Strip bulky full timelines from era summaries for evidence size
    era_summaries = {
        k: {
            "as_of_ms": v["as_of_ms"],
            "coins_existing": v["coins_existing"],
            "contracts_listed": v["contracts_listed"],
            "contracts_not_yet_listed": v["contracts_not_yet_listed"],
            "contracts_delisted": v["contracts_delisted"],
            "historical_eligible_universe": v["historical_eligible_universe"],
            "historical_excluded_universe": v["historical_excluded_universe"],
            "universe_checksum": v["universe_checksum"],
        }
        for k, v in eras.items()
    }

    all_ok = (
        fixture_pass == len(FIXTURE_IDS)
        and attack_pass == len(ATTACK_IDS)
        and attack_blocked == len(ATTACK_IDS)
        and len(survivors) == 0
    )
    if all_ok:
        recommendation = PASS_RECOMMENDATION
        status = "PASS"
    elif survivors:
        recommendation = BLOCKED_RECOMMENDATION
        status = "FAIL"
    else:
        recommendation = FAIL_RECOMMENDATION
        status = "FAIL"

    catalog = fixture_catalog()
    events = build_listing_delisting_events()
    specs = build_contract_spec_timeline()

    evidence = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "program_id": PROGRAM_ID,
        "status": status,
        "passed": all_ok,
        "recommendation": recommendation,
        "branch": BRANCH,
        "base_head": BASE_COMMIT,
        "commit": head,
        "lane_head": head,
        "worktree": str(root),
        "owned_paths": list(OWNED_PATHS),
        "prohibited_paths": list(PROHIBITED_PATHS),
        "hard_bans": list(HARD_BANS),
        "execution_mode": EXECUTION_MODE,
        "evidence_class": EVIDENCE_CLASS,
        "label": LABEL,
        "exchange_write": False,
        "mainnet": False,
        "real_money": False,
        "pr26_touched": False,
        "pr27_touched": False,
        "report_edited": False,
        "fixture_ids": list(FIXTURE_IDS),
        "fixtures": fixtures,
        "fixture_pass_count": fixture_pass,
        "fixture_total_count": len(FIXTURE_IDS),
        "attack_ids": list(ATTACK_IDS),
        "attacks": attacks,
        "attack_blocked_count": attack_blocked,
        "attack_pass_count": attack_pass,
        "attack_total_count": len(ATTACK_IDS),
        "survivors": survivors,
        "survivor_count": len(survivors),
        "era_summaries": era_summaries,
        "listing_delisting_events": {
            "event_count": events["event_count"],
            "events_checksum": events["events_checksum"],
            "events": events["events"],
        },
        "contract_spec_timeline": {
            "entry_count": specs["entry_count"],
            "timeline_checksum": specs["timeline_checksum"],
        },
        "fixture_catalog_checksum": catalog["catalog_checksum"],
        "today_survivor_symbols": catalog["today_survivor_symbols"],
        "builds": [
            "Historical Eligible Universe",
            "Historical Excluded Universe",
            "Listing/Delisting Events",
            "Contract Specification Timeline",
        ],
        "metrics": {
            "fixture_pass_count": fixture_pass,
            "attack_blocked_count": attack_blocked,
            "survivor_count": len(survivors),
            "exchange_write_attempt_count": 0,
            "mainnet_client_created_count": 0,
        },
    }
    evidence["evidence_checksum"] = sha_obj(
        {
            "status": status,
            "commit": head,
            "fixtures": [(f["fixture_id"], f["passed"]) for f in fixtures],
            "attacks": [(a["attack_id"], a["passed"], a["survivor"]) for a in attacks],
            "survivors": survivors,
        }
    )
    return evidence


def write_immutable_artifacts(evidence: dict[str, Any], *, repo_root: Path | None = None) -> Path:
    root = repo_root or Path(WORKTREE_PATH)
    art = root / ARTIFACT_REL
    art.mkdir(parents=True, exist_ok=True)
    (art / "survivorship_control_report.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    catalog = fixture_catalog()
    (art / "fixture_catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    events = build_listing_delisting_events()
    (art / "listing_delisting_events.json").write_text(
        json.dumps(events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    specs = build_contract_spec_timeline()
    (art / "contract_spec_timeline.json").write_text(
        json.dumps(specs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    eras = {}
    for name, ms in (
        ("era_2024_06_01", ERA_2024_06_01_MS),
        ("era_2024_12_01", ERA_2024_12_01_MS),
        ("era_2025_03_01", ERA_2025_03_01_MS),
    ):
        eras[name] = reconstruct_universe(ms, retrieval_timestamp="FIXED")
    (art / "historical_universe_eras.json").write_text(
        json.dumps(eras, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    summary = {
        "lane": LANE,
        "status": evidence["status"],
        "passed": evidence["passed"],
        "commit": evidence["commit"],
        "survivors": evidence["survivors"],
        "fixture_pass_count": evidence["fixture_pass_count"],
        "attack_blocked_count": evidence["attack_blocked_count"],
        "recommendation": evidence["recommendation"],
    }
    (art / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return art


def write_evidence_coordinator(evidence: dict[str, Any], *, path: str | Path | None = None) -> Path:
    out = Path(path or EVIDENCE_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
