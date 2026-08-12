"""Three-pass campaign runner for V16-G Uncertainty and Abstention Engine."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.nexus_uncertainty_abstention.adversarial import run_fail_open_attacks
from backend.nexus_uncertainty_abstention.constants import (
    BASE_COMMIT,
    BRANCH,
    CAMPAIGN_ID,
    HARD_BANS,
    LANE,
    OWNED_PATHS,
    PASS_COUNT,
    RANDOM_SEED,
    SCHEMA,
    VERDICTS,
)
from backend.nexus_uncertainty_abstention.engine import apply_ai_suggestion, evaluate_raw
from backend.nexus_uncertainty_abstention.fixtures import (
    clone_case,
    expected_verdict,
    fixture_catalog,
)
from backend.nexus_uncertainty_abstention.hard_bans import (
    env_hard_ban_guard,
    hard_ban_probe_matrix,
    scan_owned_paths_for_banned_claims,
)


def _module_checksum() -> str:
    root = Path(__file__).resolve().parent
    parts: list[str] = []
    for path in sorted(root.glob("*.py")):
        parts.append(path.name)
        parts.append(path.read_text(encoding="utf-8"))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    if "raw" in case:
        result = evaluate_raw(case["raw"])
    else:
        result = evaluate_raw(clone_case(case))
    # Adversarial AI suggestion on every case — must never mutate verdict.
    result = apply_ai_suggestion(
        result,
        {
            "verdict": "ALLOW",
            "execution_allowed": True,
            "size_multiplier": 1.0,
            "uncertainty_score": 0.0,
        },
    )
    result["expected_verdict"] = expected_verdict(str(case["case_id"]))
    result["case_id"] = case["case_id"]
    result["match_expected"] = result["verdict"] == result["expected_verdict"]
    result["ai_override_applied"] = bool(result.get("ai_override_applied"))
    return result


def run_pass(pass_id: int) -> dict[str, Any]:
    if pass_id not in (1, 2, 3):
        raise ValueError("pass_id must be 1, 2, or 3")

    cases = fixture_catalog()
    results = [_evaluate_case(c) for c in cases]
    histogram = {v: 0 for v in VERDICTS}
    for r in results:
        histogram[r["verdict"]] = histogram.get(r["verdict"], 0) + 1

    attacks = run_fail_open_attacks()
    bans = hard_ban_probe_matrix()
    env = env_hard_ban_guard()

    mismatches = [r for r in results if not r["match_expected"]]
    ai_applied = sum(1 for r in results if r.get("ai_override_applied"))
    allow_on_bad_data = [
        r
        for r in results
        if r.get("bad_data_blocked") and r["verdict"] in {"ALLOW", "ALLOW_REDUCED"}
    ]

    pass_ok = (
        len(mismatches) == 0
        and ai_applied == 0
        and len(allow_on_bad_data) == 0
        and attacks["pass"] is True
        and bans["all_refused"] is True
        and env["ok"] is True
        and all(r.get("fail_closed") for r in results)
    )

    return {
        "schema": SCHEMA,
        "lane": LANE,
        "campaign_id": CAMPAIGN_ID,
        "pass_id": pass_id,
        "branch": BRANCH,
        "base_sha": BASE_COMMIT,
        "random_seed": RANDOM_SEED,
        "owned_paths": list(OWNED_PATHS),
        "case_count": len(results),
        "results": results,
        "verdict_histogram": histogram,
        "mismatch_count": len(mismatches),
        "mismatches": [
            {"case_id": m["case_id"], "got": m["verdict"], "expected": m["expected_verdict"]}
            for m in mismatches
        ],
        "ai_override_applied_count": ai_applied,
        "ai_override_attempted_count": sum(
            1 for r in results if r.get("ai_override_attempted")
        ),
        "allow_on_bad_data_count": len(allow_on_bad_data),
        "fail_open_review": attacks,
        "hard_ban_probes": bans,
        "env_guard": env,
        "hard_bans": sorted(HARD_BANS),
        "status_json_written": False,
        "lane_report_written": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "strategy_promoted": False,
        "profitability_claimed": False,
        "qualified_claimed": False,
        "code_checksum": _module_checksum(),
        "pass_ok": pass_ok,
        "blockers": _blockers(pass_ok, mismatches, attacks, bans, env),
    }


def _blockers(
    pass_ok: bool,
    mismatches: list[dict[str, Any]],
    attacks: dict[str, Any],
    bans: dict[str, Any],
    env: dict[str, Any],
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = [
        {
            "blocker_id": "NO_STATUS_JSON",
            "detail": "V16-G must not emit *_status.json or lane report artifacts",
        },
        {
            "blocker_id": "FAIL_OPEN_BANNED",
            "detail": "provider/json/stale/contradiction/missing always fail closed",
        },
        {
            "blocker_id": "CONSENSUS_CANNOT_OVERRIDE_BAD_DATA",
            "detail": "data_agreement hard gate dominates multi-channel consensus",
        },
        {
            "blocker_id": "NO_EXCHANGE_OR_OOS",
            "detail": "engine is decision-gating only; no orders / OOS / promotion",
        },
    ]
    if not pass_ok:
        if mismatches:
            blockers.append(
                {
                    "blocker_id": "FIXTURE_MISMATCH",
                    "detail": f"{len(mismatches)} fixture verdict mismatches",
                }
            )
        if not attacks.get("pass"):
            blockers.append(
                {
                    "blocker_id": "FAIL_OPEN_PROBE_FAILED",
                    "detail": "one or more fail-open attacks were not blocked",
                }
            )
        if not bans.get("all_refused"):
            blockers.append(
                {
                    "blocker_id": "HARD_BAN_PROBE_FAILED",
                    "detail": "hard-ban probe matrix incomplete",
                }
            )
        if not env.get("ok"):
            blockers.append(
                {
                    "blocker_id": "ENV_HARD_BAN_VIOLATION",
                    "detail": ",".join(env.get("violations") or []),
                }
            )
    return blockers


def run_three_passes(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Execute founder-required THREE PASSES; all must pass."""
    root = repo_root or Path(__file__).resolve().parents[2]
    passes = [run_pass(i) for i in range(1, PASS_COUNT + 1)]
    claim_scan = scan_owned_paths_for_banned_claims(root)

    # Pass integrity: checksums must match across passes (deterministic).
    checksums = {p["code_checksum"] for p in passes}
    histograms = [tuple(sorted(p["verdict_histogram"].items())) for p in passes]
    deterministic = len(checksums) == 1 and len(set(histograms)) == 1

    all_ok = (
        all(p["pass_ok"] for p in passes)
        and claim_scan["ok"]
        and deterministic
        and PASS_COUNT == 3
    )

    return {
        "schema": SCHEMA,
        "lane": LANE,
        "campaign_id": CAMPAIGN_ID,
        "branch": BRANCH,
        "base_sha": BASE_COMMIT,
        "pass_count": PASS_COUNT,
        "passes": passes,
        "all_passes_ok": all_ok,
        "deterministic": deterministic,
        "banned_claim_scan": claim_scan,
        "status_json_written": False,
        "lane_report_written": False,
        "code_checksum": next(iter(checksums)),
        "final_status": "PASS" if all_ok else "FAIL",
        "blockers": passes[-1]["blockers"] if passes else [],
    }
