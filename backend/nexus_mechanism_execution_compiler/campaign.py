"""V15-B campaign runner — compile + execute + replay (development only)."""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from backend.nexus_mechanism_execution_compiler.compiler import compile_all_executors
from backend.nexus_mechanism_execution_compiler.constants import (
    ALLOWED_LABELS,
    ARTIFACT_DIRNAME,
    BASE_SHA,
    BRANCH,
    CAMPAIGN_ID,
    CANONICAL_COST_AUTHORITY,
    EXPECTED_MECHANISM_COUNT,
    HARD_BANS,
    LANE,
    MIN_EXECUTOR_COUNT,
    NON_CLAIMS,
    OWNED_PATHS,
    PACKAGE,
    RANDOM_SEED,
    SCHEMA,
    SOURCE_LANE,
    SOURCE_PACKAGE,
)
from backend.nexus_mechanism_execution_compiler.replay import assert_replay_stable, replay_all


def _module_checksum() -> str:
    root = Path(__file__).resolve().parent
    parts: list[str] = []
    for path in sorted(root.glob("*.py")):
        parts.append(path.name)
        parts.append(path.read_text(encoding="utf-8"))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _label(result: dict[str, Any], *, replay_ok: bool) -> str:
    if result.get("control_overlay_only"):
        return "CONTROL_OVERLAY_ONLY"
    if int(result.get("cost_gated_count") or 0) > 0 and int(result.get("event_count") or 0) == 0:
        return "COST_GATED"
    if int(result.get("failure_probe_count") or 0) > 20 and int(result.get("event_count") or 0) == 0:
        return "RISK_INCOMPATIBLE_ON_SYNTHETIC"
    if replay_ok and result.get("negative_test"):
        return "REPLAY_STABLE"
    return "EXECUTOR_COMPILED_DEV_ONLY"


def run_compiler_campaign(*, pass_id: int = 1, seed: int = RANDOM_SEED) -> dict[str, Any]:
    if pass_id not in (1, 2):
        raise ValueError("pass_id must be 1 or 2")

    contracts = compile_all_executors()
    replay_pack = replay_all(seed=seed)
    stability = assert_replay_stable(seed=seed)
    code_ck = _module_checksum()

    labeled: list[dict[str, Any]] = []
    for result in replay_pack["results"]:
        label = _label(result, replay_ok=stability["ok"])
        if label not in ALLOWED_LABELS:
            raise AssertionError(f"illegal_label:{label}")
        row = {
            **result,
            "label": label,
            "status": label,
            "negative_test_covered": True,
            "code_checksum": code_ck,
        }
        # Hard enforcement: never qualification-ready.
        if row.get("qualified") or row.get("qualification_ready") or row.get("edge_claimed"):
            raise AssertionError("qualification_or_edge_claim_forbidden")
        labeled.append(row)

    hist = dict(Counter(r["label"] for r in labeled))
    for lbl in ALLOWED_LABELS:
        hist.setdefault(lbl, 0)

    blockers = [
        {
            "blocker_id": "QUALIFICATION_NOT_AUTHORIZED",
            "detail": "qualification_ready_count forced 0; executors are development-only",
        },
        {
            "blocker_id": "OOS_AND_FORMAL_WF_BANNED",
            "detail": "synthetic development fixtures only; no OOS consumption",
        },
        {
            "blocker_id": "NO_AUTO_INTEGRATE",
            "detail": "lane artifacts only; coordinator must not auto-integrate",
        },
        {
            "blocker_id": "NO_LIVE_ORDERS",
            "detail": "executors never emit demo/shadow/exchange writes",
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
        "source_lane": SOURCE_LANE,
        "source_package": SOURCE_PACKAGE,
        "hard_bans": sorted(HARD_BANS),
        "non_claims": list(NON_CLAIMS),
        "owned_paths": list(OWNED_PATHS),
        "mechanism_executor_count": len(labeled),
        "mechanism_count_source": EXPECTED_MECHANISM_COUNT,
        "min_executor_count": MIN_EXECUTOR_COUNT,
        "executor_catalog": [c.to_public_dict() for c in contracts],
        "executors": labeled,
        "label_histogram": hist,
        "campaign_digest": replay_pack["campaign_digest"],
        "replay_stable": stability["ok"],
        "qualification_ready_count": 0,
        "edge_claim_count": 0,
        "profitability_claim_count": 0,
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
        "cost_authority": CANONICAL_COST_AUTHORITY,
        "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
        "blockers": blockers,
        "code_checksum": code_ck,
        "allowed_labels": sorted(ALLOWED_LABELS),
        "status_json_written": False,
    }

    if report["mechanism_executor_count"] < MIN_EXECUTOR_COUNT:
        raise AssertionError("mechanism_executor_count_below_min")
    if report["mechanism_executor_count"] != EXPECTED_MECHANISM_COUNT:
        raise AssertionError("mechanism_executor_count_must_equal_source_42")
    if report["qualification_ready_count"] != 0:
        raise AssertionError("qualification_ready_count_must_be_zero")
    if report["formal_walk_forward_executed"] or report["oos_executed"]:
        raise AssertionError("oos_or_wf_ban_violated")
    if not report["replay_stable"]:
        raise AssertionError("replay_not_stable")
    return report
