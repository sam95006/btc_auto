"""V16-E three-pass campaign — compile Reflection fixtures into CANDIDATE lessons."""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from backend.nexus_lesson_compiler.compiler import compile_all_lessons
from backend.nexus_lesson_compiler.constants import (
    ARTIFACT_DIRNAME,
    BASE_SHA,
    BRANCH,
    CAMPAIGN_ID,
    EXPECTED_FIXTURE_COUNT,
    HARD_BANS,
    LANE,
    LESSON_STATUS_CANDIDATE,
    MIN_LESSON_COUNT,
    NON_CLAIMS,
    OWNED_PATHS,
    PACKAGE,
    RANDOM_SEED,
    SCHEMA,
)


def _module_checksum() -> str:
    root = Path(__file__).resolve().parent
    parts: list[str] = []
    for path in sorted(root.glob("*.py")):
        parts.append(path.name)
        parts.append(path.read_text(encoding="utf-8"))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _campaign_digest(lessons: list[dict[str, Any]], code_ck: str) -> str:
    payload = {
        "lessons": [row["compile_digest"] for row in lessons],
        "code_checksum": code_ck,
        "seed": RANDOM_SEED,
    }
    blob = str(sorted(payload["lessons"])) + "|" + code_ck + "|" + str(RANDOM_SEED)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def run_compiler_campaign(*, pass_id: int = 1, seed: int = RANDOM_SEED) -> dict[str, Any]:
    if pass_id not in (1, 2, 3):
        raise ValueError("pass_id must be 1, 2, or 3")

    rules = compile_all_lessons()
    code_ck = _module_checksum()
    labeled: list[dict[str, Any]] = []
    for rule in rules:
        row = rule.to_public_dict()
        row["label"] = "LESSON_CANDIDATE_COMPILED"
        row["qualified"] = False
        row["qualification_ready"] = False
        row["edge_claimed"] = False
        row["profitability_claimed"] = False
        row["active"] = False
        row["data_lineage"] = "SYNTHETIC_DEVELOPMENT_FIXTURE"
        row["code_checksum"] = code_ck
        if row["status"] != LESSON_STATUS_CANDIDATE:
            raise AssertionError("non_candidate_emit_forbidden")
        if row["mutates_production_risk"] or row["mutates_production_leverage"]:
            raise AssertionError("production_mutation_emit_forbidden")
        labeled.append(row)

    hist = dict(Counter(r["label"] for r in labeled))
    digest = _campaign_digest(labeled, code_ck)

    blockers = [
        {
            "blocker_id": "LESSONS_CANDIDATE_ONLY",
            "detail": "All compiled lessons remain CANDIDATE; ACTIVE real lessons banned",
        },
        {
            "blocker_id": "NO_PRODUCTION_RISK_LEVERAGE_MUTATION",
            "detail": "Compiler refuses rules that mutate production risk or leverage",
        },
        {
            "blocker_id": "OOS_AND_FORMAL_WF_BANNED",
            "detail": "Development fixtures only; no OOS consumption or formal WF",
        },
        {
            "blocker_id": "NO_AUTO_INTEGRATE",
            "detail": "Lane artifacts only; coordinator must not auto-integrate",
        },
        {
            "blocker_id": "PROMOTION_PIPELINE_OWNED_BY_V16_F",
            "detail": "Promotion past CANDIDATE is V16-F Lesson Validation Firewall only",
        },
    ]

    report = {
        "schema": SCHEMA,
        "package": PACKAGE,
        "campaign_id": CAMPAIGN_ID,
        "artifact_dirname": ARTIFACT_DIRNAME,
        "lane": LANE,
        "branch": BRANCH,
        "base_sha": BASE_SHA,
        "pass_id": pass_id,
        "seed": seed,
        "hard_bans": sorted(HARD_BANS),
        "non_claims": list(NON_CLAIMS),
        "owned_paths": list(OWNED_PATHS),
        "lesson_count": len(labeled),
        "fixture_count": EXPECTED_FIXTURE_COUNT,
        "min_lesson_count": MIN_LESSON_COUNT,
        "lessons": labeled,
        "lesson_catalog": [r.to_public_dict() for r in rules],
        "label_histogram": hist,
        "campaign_digest": digest,
        "replay_stable": True,
        "qualification_ready_count": 0,
        "edge_claim_count": 0,
        "profitability_claim_count": 0,
        "active_lesson_count": 0,
        "candidate_lesson_count": len(labeled),
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
        "pr26_merge_attempted": False,
        "pr27_merge_attempted": False,
        "auto_integrate_attempted": False,
        "auto_integrate": False,
        "private_core_deploy_attempted": False,
        "production_risk_mutated": False,
        "production_leverage_mutated": False,
        "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
        "blockers": blockers,
        "code_checksum": code_ck,
        "status_json_written": False,
    }

    if report["lesson_count"] < MIN_LESSON_COUNT:
        raise AssertionError("lesson_count_below_min")
    if report["lesson_count"] != EXPECTED_FIXTURE_COUNT:
        raise AssertionError("lesson_count_must_equal_fixture_count")
    if report["active_lesson_count"] != 0:
        raise AssertionError("active_lessons_forbidden")
    if report["qualification_ready_count"] != 0:
        raise AssertionError("qualification_ready_count_must_be_zero")
    if report["formal_walk_forward_executed"] or report["oos_executed"]:
        raise AssertionError("oos_or_wf_ban_violated")
    if report["production_risk_mutated"] or report["production_leverage_mutated"]:
        raise AssertionError("production_mutation_ban_violated")
    if not report["replay_stable"]:
        raise AssertionError("replay_not_stable")
    return report
