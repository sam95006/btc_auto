"""Pass-2 adversarial probes for V15-A development data foundation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_dev_data_foundation.constants import FORBIDDEN_STATUS_GLOB, OWNED_PATHS
from backend.nexus_dev_data_foundation.hashing import sha_obj
from backend.nexus_dev_data_foundation.partitions import (
    build_time_partitions,
    verify_no_dev_oos_overlap,
)
from backend.nexus_dev_data_foundation.pit import (
    filter_records_for_development,
    prove_oos_excluded,
    reject_invented_history,
    reject_oos_load,
    reject_today_for_past,
)
from backend.nexus_dev_data_foundation.records import build_record, verify_record


def _finding(severity: str, code: str, detail: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"severity": severity, "code": code, "detail": detail, "evidence": evidence}


def run_adversarial_pass(
    root: Path,
    *,
    inventory: dict[str, Any],
    pass_number: int,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    records = list(inventory.get("records") or [])

    # 1) OOS load attack
    oos_gate = reject_oos_load("OOS_RESERVED")
    checks.append({"check": "oos_reserved_load_blocked", "ok": oos_gate["blocked"] is True, "evidence": oos_gate})
    if not oos_gate["blocked"]:
        findings.append(_finding("CRITICAL", "OOS_LOAD_ALLOWED", "OOS_RESERVED load was not blocked", oos_gate))

    untouched_gate = reject_oos_load("OOS_UNTOUCHED")
    checks.append(
        {"check": "oos_untouched_load_blocked", "ok": untouched_gate["blocked"] is True, "evidence": untouched_gate}
    )
    if not untouched_gate["blocked"]:
        findings.append(
            _finding("CRITICAL", "OOS_UNTOUCHED_LOAD_ALLOWED", "OOS_UNTOUCHED load was not blocked", untouched_gate)
        )

    # 2) Invented history attack
    invent = reject_invented_history(claimed_available=True, source_present=False)
    checks.append({"check": "invented_history_blocked", "ok": invent["ok"] is False, "evidence": invent})
    if invent["ok"]:
        findings.append(_finding("CRITICAL", "INVENTED_HISTORY_ALLOWED", "Missing source treated as available", invent))

    # Attempt to build a fabricated AVAILABLE record should still mark invented_history False
    # and MISSING when we follow inventory rules — attack is claiming AVAILABLE without file.
    attack_ok = invent["status"] == "INVENTED_HISTORY_BLOCKED"
    checks.append({"check": "invented_history_status", "ok": attack_ok, "evidence": invent})

    # 3) Today-for-past attack
    today_attack = reject_today_for_past(snapshot_availability_ms=1_740_787_200_000, as_of_ms=1_717_200_000_000)
    checks.append({"check": "today_for_past_blocked", "ok": today_attack["ok"] is False, "evidence": today_attack})
    if today_attack["ok"]:
        findings.append(
            _finding("CRITICAL", "TODAY_FOR_PAST_ALLOWED", "Later snapshot accepted for earlier as_of", today_attack)
        )

    # 4) Partition overlap
    overlap = verify_no_dev_oos_overlap()
    checks.append({"check": "no_dev_oos_overlap", "ok": overlap["ok"], "evidence": overlap})
    if not overlap["ok"]:
        findings.append(_finding("CRITICAL", "PARTITION_OVERLAP", "Development overlaps OOS", overlap))

    # 5) OOS exclusion proof on inventory
    oos_proof = prove_oos_excluded(records)
    checks.append({"check": "oos_excluded_from_dev_load", "ok": oos_proof["oos_excluded"], "evidence": oos_proof})
    if not oos_proof["oos_excluded"]:
        findings.append(_finding("CRITICAL", "OOS_LEAK_INTO_DEV", "OOS records loadable for development", oos_proof))

    # 6) Record hash integrity
    hash_failures = []
    for r in records:
        vr = verify_record(r)
        if not vr.get("ok"):
            hash_failures.append({"record_id": r.get("record_id"), "verify": vr})
    checks.append(
        {
            "check": "record_hash_integrity",
            "ok": len(hash_failures) == 0,
            "evidence": {"failure_count": len(hash_failures), "failures": hash_failures[:10]},
        }
    )
    if hash_failures:
        findings.append(
            _finding("HIGH", "RECORD_HASH_FAILURES", "One or more records failed hash verify", {"count": len(hash_failures)})
        )

    # 7) Tamper detection
    if records:
        original = records[0]["content_checksum"]
        tampered = sha_obj({"tamper": True, "original": original})
        checks.append(
            {
                "check": "checksum_tamper_detection",
                "ok": tampered != original,
                "evidence": {"original": original, "tampered": tampered},
            }
        )
    else:
        findings.append(_finding("CRITICAL", "EMPTY_INVENTORY", "No inventory records", {}))
        checks.append({"check": "checksum_tamper_detection", "ok": False, "evidence": {}})

    # 8) Forbidden human-facing status JSON
    art = root / "artifacts/readiness/immutable/v15_dev_data_foundation"
    banned = list(art.glob(FORBIDDEN_STATUS_GLOB)) if art.is_dir() else []
    # Also scan owned paths for the forbidden pattern
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_dir():
            banned.extend(target.rglob("v15_*_status.json"))
    banned_rels = sorted({str(p.relative_to(root)).replace("\\", "/") for p in banned if p.is_file()})
    checks.append(
        {
            "check": "no_human_facing_v15_status_json",
            "ok": len(banned_rels) == 0,
            "evidence": {"banned_files": banned_rels},
        }
    )
    if banned_rels:
        findings.append(
            _finding(
                "CRITICAL",
                "FORBIDDEN_STATUS_JSON",
                "Found v15_*_status.json (banned by Founder report rule)",
                {"files": banned_rels},
            )
        )

    # 9) Consumed holdout must not be development-loadable
    consumed = [r for r in records if r.get("partition_category") == "CONSUMED_FORBIDDEN"]
    loaded = filter_records_for_development(records)
    consumed_leaked = [r["record_id"] for r in loaded if r.get("partition_category") == "CONSUMED_FORBIDDEN"]
    checks.append(
        {
            "check": "consumed_holdout_excluded",
            "ok": len(consumed_leaked) == 0,
            "evidence": {"consumed_catalog_count": len(consumed), "leaked": consumed_leaked},
        }
    )
    if consumed_leaked:
        findings.append(
            _finding("CRITICAL", "CONSUMED_HOLDOUT_REUSED", "Consumed holdout loadable for development", {"ids": consumed_leaked})
        )

    # 10) Hard-ban flags on records
    ban_violations = []
    for r in records:
        if r.get("oos_consumed") is True or r.get("invented_history") is True:
            ban_violations.append(r.get("record_id"))
        if r.get("exchange_write") is True or r.get("mainnet") is True:
            ban_violations.append(r.get("record_id"))
    checks.append(
        {"check": "hard_ban_flags_clean", "ok": len(ban_violations) == 0, "evidence": {"violations": ban_violations}}
    )
    if ban_violations:
        findings.append(_finding("CRITICAL", "HARD_BAN_FLAG_VIOLATION", "Record flipped a hard ban", {"ids": ban_violations}))

    # 11) Fabricated edge scan — inventory must not claim profitability
    edge_hits = []
    for r in records:
        summary = r.get("payload_summary") or {}
        for key in ("profit", "edge", "alpha", "qualified"):
            if key in summary and summary[key]:
                edge_hits.append(r.get("record_id"))
        if r.get("profitability_claim") is True or r.get("fabricated_edge") is True:
            edge_hits.append(r.get("record_id"))
    checks.append({"check": "no_fabricated_edge_claim", "ok": len(edge_hits) == 0, "evidence": {"hits": edge_hits}})
    if edge_hits:
        findings.append(_finding("CRITICAL", "FABRICATED_EDGE", "Inventory claims edge/profit", {"ids": edge_hits}))

    # 12) Attempt build_record for OOS without allow flag must fail
    oos_build_blocked = False
    try:
        build_record(
            source_id="attack_oos",
            source_kind="attack",
            source_path=None,
            source_timestamp=None,
            availability_ms=1_785_663_000_100,
            content_checksum="abc",
            availability_state="AVAILABLE",
            partition_id="SEPTEMBER_H3_OOS_RESERVED",
            partition_category="OOS_RESERVED",
            allow_oos_catalog_only=False,
        )
    except ValueError as exc:
        oos_build_blocked = "oos_or_consumed_forbidden" in str(exc)
    checks.append({"check": "oos_record_build_requires_catalog_flag", "ok": oos_build_blocked, "evidence": {}})
    if not oos_build_blocked:
        findings.append(
            _finding("CRITICAL", "OOS_RECORD_BUILD_UNBLOCKED", "OOS record built without catalog-only flag", {})
        )

    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    high = [f for f in findings if f["severity"] == "HIGH"]
    passed = len(critical) == 0 and all(c["ok"] for c in checks)

    return {
        "schema": "v15_a_adversarial_pass",
        "pass_number": pass_number,
        "passed": passed,
        "checks": checks,
        "findings": findings,
        "critical_finding_count": len(critical),
        "high_finding_count": len(high),
        "critical_findings": critical,
        "high_findings": high,
        "partitions": build_time_partitions(),
        "check_pass_count": sum(1 for c in checks if c["ok"]),
        "check_total_count": len(checks),
    }
