"""Evidence writer for V17 deep PIT / survivorship wave."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.nexus_deep_pit_survivorship.campaign import run_campaign, write_artifacts
from backend.nexus_deep_pit_survivorship.constants import EVIDENCE_PATH, SCHEMA, WORKTREE_PATH


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_evidence(
    *,
    repo_root: Path | None = None,
    tests: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path(WORKTREE_PATH)
    campaign = run_campaign(repo_root=root)
    artifact_paths = write_artifacts(campaign, repo_root=root)
    evidence = {
        "schema": "v17_deep_pit_survivorship_evidence_v1",
        "module_schema": SCHEMA,
        "generated_at": campaign["generated_at"],
        "lane": campaign["lane"],
        "lane_name": campaign["lane_name"],
        "program_id": campaign["program_id"],
        "status": campaign["status"],
        "passed": campaign["passed"],
        "HEAD": campaign["HEAD"],
        "base": campaign["base"],
        "branch": campaign["branch"],
        "worktree": campaign["worktree"],
        "coverage_areas": campaign["coverage_areas"],
        "owned_paths": campaign["owned_paths"],
        "hard_bans": campaign["hard_bans"],
        "non_claims": campaign["non_claims"],
        "survivor_count": campaign["survivor_count"],
        "survivors": campaign["survivors"],
        "attack_count": campaign["attack_count"],
        "blocked_count": campaign["blocked_count"],
        "property_case_count": campaign["property_case_count"],
        "future_leakage_redteam": {
            "attack_count": campaign["sections"]["future_leakage"]["attack_count"],
            "blocked_count": campaign["sections"]["future_leakage"]["blocked_count"],
            "survivor_count": campaign["sections"]["future_leakage"]["survivor_count"],
            "pass": campaign["sections"]["future_leakage"]["pass"],
            "survivors": campaign["sections"]["future_leakage"]["survivors"],
            "base_attack_count": campaign["sections"]["future_leakage"]["base"]["attack_count"],
            "expanded_attack_count": campaign["sections"]["future_leakage"]["expanded"]["attack_count"],
        },
        "sections_pass": {
            "property_as_known_at": campaign["sections"]["property_as_known_at"]["pass"],
            "mutation_as_known_at": campaign["sections"]["mutation_as_known_at"]["pass"],
            "timestamp_edges": campaign["sections"]["timestamp_edges"]["pass"],
            "symbol_collision": campaign["sections"]["symbol_collision"]["pass"],
            "listing_delisting": campaign["sections"]["listing_delisting"]["pass"],
            "future_leakage": campaign["sections"]["future_leakage"]["pass"],
            "axis_mutation_blocked": campaign["sections"]["axis_mutation"]["blocked"],
        },
        "artifacts": {
            "artifact_dir": str(root / "artifacts" / "readiness" / "immutable" / "v17_deep_pit_survivorship"),
            "files": artifact_paths,
        },
        "tests": tests
        or {
            "suite": "tests/deep_pit_survivorship/",
            "passed": None,
            "failed": None,
            "new_tests_count": None,
        },
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
        "campaign_checksum": campaign["campaign_checksum"],
    }
    return evidence


def write_evidence(
    evidence: dict[str, Any],
    *,
    path: str | Path = EVIDENCE_PATH,
) -> dict[str, Any]:
    fp = Path(path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    body = dict(evidence)
    body.pop("evidence_sha256", None)
    text = json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    digest = _sha_text(text)
    body["evidence_sha256"] = digest
    text2 = json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fp.write_text(text2, encoding="utf-8")
    return body
