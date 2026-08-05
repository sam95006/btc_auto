"""Three-pass adversarial orchestration for V16 moat redteam."""
from __future__ import annotations

from typing import Any

from backend.nexus_moat_adversarial_redteam_v16.attacks import AttackResult, run_all_attacks
from backend.nexus_moat_adversarial_redteam_v16.constants import (
    ATTACK_IDS,
    DISPOSITIONS,
    HARD_BANS,
    PASS_COUNT,
)


def _summarize(results: list[AttackResult]) -> dict[str, Any]:
    rows = [r.to_dict() for r in results]
    by_disp = {d: 0 for d in DISPOSITIONS}
    for row in rows:
        by_disp[row["disposition"]] = by_disp.get(row["disposition"], 0) + 1
    survivors = [row for row in rows if row["survivor"]]
    critical_survivors = [
        s for s in survivors if s["severity"] == "CRITICAL" and s["disposition"] != "EXPLICITLY_BLOCKED"
    ]
    # EXPLICITLY_BLOCKED Critical (exchange/mainnet) are closed-by-ban, not open defects.
    open_critical = [
        s
        for s in survivors
        if s["severity"] == "CRITICAL" and s["disposition"] == "PLATFORM_BLOCKED_NOT_PASS"
    ]
    open_high = [
        s
        for s in survivors
        if s["severity"] == "HIGH" and s["disposition"] == "PLATFORM_BLOCKED_NOT_PASS"
    ]
    unblocked = [row for row in rows if not row["attack_blocked"]]
    return {
        "attack_count": len(rows),
        "required_attack_count": len(ATTACK_IDS),
        "coverage_complete": len(rows) == len(ATTACK_IDS)
        and {r["attack_id"] for r in rows} == set(ATTACK_IDS),
        "disposition_counts": by_disp,
        "survivors": survivors,
        "survivor_count": len(survivors),
        "open_critical": open_critical,
        "open_high": open_high,
        "critical_open_count": len(open_critical),
        "high_open_count": len(open_high),
        "unblocked_attacks": unblocked,
        "explicitly_blocked": [
            r for r in rows if r["disposition"] == "EXPLICITLY_BLOCKED"
        ],
        "platform_blocked_not_pass": [
            r for r in rows if r["disposition"] == "PLATFORM_BLOCKED_NOT_PASS"
        ],
        "fixed": [r for r in rows if r["disposition"] == "FIXED"],
        "critical_survivors_legacy": critical_survivors,
    }


def run_pass(pass_id: int) -> dict[str, Any]:
    results = run_all_attacks()
    summary = _summarize(results)
    return {
        "pass_id": pass_id,
        "schema": f"v16_moat_adversarial_pass_{pass_id}",
        "hard_bans": list(HARD_BANS),
        "results": [r.to_dict() for r in results],
        "summary": summary,
    }


def run_three_passes() -> dict[str, Any]:
    passes = [run_pass(i) for i in range(1, PASS_COUNT + 1)]
    # Pass-over-pass stability: dispositions must not silently flip to FIXED without block.
    unstable: list[dict[str, Any]] = []
    first = {r["attack_id"]: r for r in passes[0]["results"]}
    for p in passes[1:]:
        for r in p["results"]:
            prev = first[r["attack_id"]]
            if prev["attack_blocked"] and not r["attack_blocked"]:
                unstable.append(
                    {
                        "attack_id": r["attack_id"],
                        "detail": "regression_unblocked_after_earlier_block",
                        "pass_id": p["pass_id"],
                    }
                )
            if (
                prev["disposition"] == "FIXED"
                and r["disposition"] == "PLATFORM_BLOCKED_NOT_PASS"
            ):
                unstable.append(
                    {
                        "attack_id": r["attack_id"],
                        "detail": "disposition_regressed_from_FIXED",
                        "pass_id": p["pass_id"],
                    }
                )

    final = passes[-1]["summary"]
    # Never auto-PASS: require full coverage, zero open CRITICAL/HIGH PLATFORM_BLOCKED,
    # zero unblocked attacks, zero unstable regressions, zero harness bugs.
    harness_bugs = [
        r
        for r in passes[-1]["results"]
        if str(r.get("detail", "")).startswith("harness_bug:")
        or str(r.get("detail", "")).startswith("probe_exception:")
    ]
    can_pass = (
        final["coverage_complete"]
        and final["critical_open_count"] == 0
        and final["high_open_count"] == 0
        and len(final["unblocked_attacks"]) == 0
        and len(unstable) == 0
        and len(harness_bugs) == 0
        and all(r["disposition"] in DISPOSITIONS for r in passes[-1]["results"])
        and all(
            r["disposition"] in {"FIXED", "EXPLICITLY_BLOCKED"}
            for r in passes[-1]["results"]
        )
    )
    return {
        "pass_count": PASS_COUNT,
        "passes": passes,
        "unstable": unstable,
        "final_summary": final,
        "can_pass": can_pass,
        "harness_bugs": harness_bugs,
        # All non-FIXED remain listed as survivors (Founder: list all survivors).
        "survivors": final["survivors"],
    }
