"""Pass-2 adversarial self-review for V14-I universe lineage red team."""
from __future__ import annotations

from typing import Any

from backend.nexus_universe_redteam.constants import (
    ATTACK_SCENARIO_IDS,
    EVIDENCE_CLASS,
    HARD_BANS,
    OWNED_PATHS,
)
from backend.nexus_universe_redteam.guards import (
    detect_listing_date_leakage,
    detect_rename_leakage,
    detect_survivorship_bias,
    require_attack_disposition,
)


def run_pass2_review(pass1_status: dict[str, Any]) -> dict[str, Any]:
    """Adversarial self-review: false-PASS, fixture-vs-real, PIT leakage, silent fallback."""
    findings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    # 1) False-PASS search: every scenario must attack_blocked and not platform_blocked
    scenarios = pass1_status.get("scenarios") or []
    for s in scenarios:
        if s.get("passed") and not s.get("attack_blocked"):
            findings.append(
                {
                    "severity": "critical",
                    "code": f"false_pass:{s.get('scenario_id')}",
                    "detail": "passed_without_attack_blocked",
                }
            )
        if s.get("platform_blocked") and s.get("passed"):
            findings.append(
                {
                    "severity": "critical",
                    "code": f"platform_blocked_as_pass:{s.get('scenario_id')}",
                    "detail": "platform_blocked_must_not_count_as_pass",
                }
            )
        disp = require_attack_disposition(
            attack_blocked_by_code=bool(s.get("attack_blocked")),
            critical_blocker_code=s.get("critical_blocker_code"),
        )
        if not disp["ok"] and s.get("passed"):
            findings.append(
                {
                    "severity": "critical",
                    "code": f"missing_disposition:{s.get('scenario_id')}",
                    "detail": "attack_neither_blocked_nor_critical_blocker",
                }
            )
    checks.append({"check": "false_pass_search", "ok": not any(f["code"].startswith("false_pass") or f["code"].startswith("platform_blocked") for f in findings)})

    # 2) Fixture-versus-real classification
    label = pass1_status.get("evidence_class") or pass1_status.get("label")
    fixture_ok = EVIDENCE_CLASS in str(label) or "CONTROL" in str(label).upper() or "NOT_REAL" in str(label).upper()
    if not fixture_ok:
        findings.append(
            {
                "severity": "critical",
                "code": "fixture_vs_real_mislabel",
                "detail": f"label={label}",
            }
        )
    for fx in pass1_status.get("fixtures") or []:
        if fx.get("evidence_class") != EVIDENCE_CLASS:
            findings.append(
                {
                    "severity": "high",
                    "code": f"fixture_label_missing:{fx.get('fixture_id')}",
                    "detail": "fixture_must_declare_control_evidence_class",
                }
            )
    checks.append({"check": "fixture_versus_real", "ok": fixture_ok})

    # 3) PIT leakage negative expansion
    listing_attack = detect_listing_date_leakage(
        symbol="X",
        listing_ms=9_999_999_999_999,
        as_of_ms=1,
        claimed_eligible=True,
    )
    rename_attack = detect_rename_leakage(
        old_symbol="A",
        new_symbol="B",
        rename_effective_ms=100,
        as_of_ms=50,
        rename_lineage_id=None,
        claimed_identity="B",
    )
    surv = detect_survivorship_bias(
        claimed_symbols=["BTCUSDT"],
        pit_eligible_symbols=["BTCUSDT", "GHOSTUSDT"],
        today_survivor_symbols=["BTCUSDT"],
    )
    pit_ok = (not listing_attack["ok"]) and (not rename_attack["ok"]) and (not surv["ok"])
    if not pit_ok:
        findings.append(
            {
                "severity": "critical",
                "code": "pass2_pit_leakage_oracle_failed",
                "detail": "negative_expansion_oracles_did_not_block",
            }
        )
    checks.append({"check": "pit_leakage_search", "ok": pit_ok})

    # 4) Silent fallback / schema drift
    missing_scenarios = sorted(set(ATTACK_SCENARIO_IDS) - {s.get("scenario_id") for s in scenarios})
    if missing_scenarios:
        findings.append(
            {
                "severity": "critical",
                "code": "silent_scenario_drop",
                "detail": ",".join(missing_scenarios),
            }
        )
    checks.append({"check": "silent_fallback_search", "ok": len(missing_scenarios) == 0})

    # 5) Hard bans still declared
    bans = set(pass1_status.get("hard_bans") or [])
    required_bans = set(HARD_BANS)
    missing_bans = sorted(required_bans - bans)
    if missing_bans:
        findings.append(
            {
                "severity": "critical",
                "code": "hard_ban_regression",
                "detail": ",".join(missing_bans),
            }
        )
    checks.append({"check": "hard_ban_presence", "ok": len(missing_bans) == 0})

    # 6) Owned-path discipline reminder (no auto-integrate)
    if pass1_status.get("auto_integration") is True:
        findings.append(
            {
                "severity": "critical",
                "code": "auto_integration_enabled",
                "detail": "V14 must not auto-integrate",
            }
        )
    owned = pass1_status.get("owned_paths") or []
    checks.append(
        {
            "check": "owned_paths",
            "ok": list(owned) == list(OWNED_PATHS) or set(owned) == set(OWNED_PATHS),
        }
    )

    # 7) Secret / cost omission / race — universe lane has no cost path; assert zero writes
    if int(pass1_status.get("exchange_write_attempt_count") or 0) != 0:
        findings.append(
            {
                "severity": "critical",
                "code": "exchange_write_nonzero",
                "detail": "hard_ban_violation",
            }
        )
    if int(pass1_status.get("secret_leak_count") or 0) != 0:
        findings.append(
            {
                "severity": "critical",
                "code": "secret_leak_nonzero",
                "detail": "secret_leakage_search_failed",
            }
        )
    checks.append(
        {
            "check": "secret_and_write_bans",
            "ok": int(pass1_status.get("exchange_write_attempt_count") or 0) == 0
            and int(pass1_status.get("secret_leak_count") or 0) == 0,
        }
    )

    critical = [f for f in findings if f.get("severity") == "critical"]
    high = [f for f in findings if f.get("severity") == "high"]
    passed = len(critical) == 0 and all(c.get("ok") for c in checks)
    return {
        "pass_number": 2,
        "passed": passed,
        "checks": checks,
        "findings": findings,
        "critical_finding_count": len(critical),
        "high_finding_count": len(high),
        "critical_findings": critical,
        "high_findings": high,
    }
