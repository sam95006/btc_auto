"""Three-pass harness for V16-A Trade Error Ontology."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_trade_error_ontology_v1.ai_proposal import (
    apply_ai_proposal,
    attempt_ai_override,
)
from backend.nexus_trade_error_ontology_v1.classifier import (
    assert_loss_not_auto_bad,
    assert_win_not_auto_good,
    classify_trade_error,
)
from backend.nexus_trade_error_ontology_v1.constants import (
    ARTIFACT_REL,
    ERROR_DIMENSIONS,
    HARD_BANS,
    OWNED_PATHS,
    PROCESS_CLASSES,
    SCHEMA,
)
from backend.nexus_trade_error_ontology_v1.fixtures import (
    expected_class_by_trade_id,
    labeled_fixture_controls,
)
from backend.nexus_trade_error_ontology_v1.gene_bank import build_gene_bank, write_gene_bank_artifact
from backend.nexus_trade_error_ontology_v1.hard_bans import (
    HardBanViolation,
    assert_no_acceleration_report_edit,
    assert_no_status_json_filenames,
    hard_ban_inventory,
    refuse_exchange_write,
    refuse_fabricated_ai_learning,
    refuse_mainnet,
    refuse_oos,
    refuse_pr26_merge,
    refuse_pr27_merge,
    refuse_real_money,
    refuse_walkforward,
)
from backend.nexus_trade_error_ontology_v1.schema import (
    build_schema,
    validate_classification_record,
    write_schema_artifact,
)


def _pass1_implementation(root: Path) -> dict[str, Any]:
    schema_path = write_schema_artifact(root)
    gene_path = write_gene_bank_artifact(root)
    bank = build_gene_bank()
    schema = build_schema()
    fixtures = labeled_fixture_controls()
    expected = expected_class_by_trade_id()
    rows = [classify_trade_error(p) for p in fixtures]
    class_ok = all(r["process_classification"] == expected[r["trade_id"]] for r in rows)
    dims_covered = set(ERROR_DIMENSIONS) <= set(bank["error_dimensions"])
    genes_cover_dims = {g["dimension"] for g in bank["genes"]}
    return {
        "pass": 1,
        "name": "implementation",
        "status": "PASS" if class_ok and dims_covered else "FAIL",
        "schema_path": str(schema_path.relative_to(root)).replace("\\", "/"),
        "gene_bank_path": str(gene_path.relative_to(root)).replace("\\", "/"),
        "ontology_schema": SCHEMA,
        "process_class_count": len(PROCESS_CLASSES),
        "dimension_count": len(ERROR_DIMENSIONS),
        "gene_count": bank["gene_count"],
        "fixture_count": len(fixtures),
        "classification_match": class_ok,
        "all_dimensions_declared": dims_covered,
        "gene_dimensions_present": sorted(genes_cover_dims),
        "schema_required_fields": list(schema["required"]),
        "checks": {
            "classes_present": set(PROCESS_CLASSES) == {
                "GOOD_PROCESS_WIN",
                "GOOD_PROCESS_LOSS",
                "BAD_PROCESS_WIN",
                "BAD_PROCESS_LOSS",
                "UNAVOIDABLE_SHOCK",
                "INSUFFICIENT_EVIDENCE",
            },
            "profitable_bad_process_win": any(
                r["process_classification"] == "BAD_PROCESS_WIN" and r["is_win"] for r in rows
            ),
            "records_valid": all(not validate_classification_record(r) for r in rows),
        },
    }


def _pass2_adversarial(root: Path) -> dict[str, Any]:
    fixtures = {p["trade_id"]: p for p in labeled_fixture_controls()}
    findings: list[str] = []

    # 1) AI cannot override BAD_PROCESS_WIN → GOOD_PROCESS_WIN
    bad_win = fixtures["V16A_FIX_bad_cost_win"]
    try:
        attempt_ai_override(
            bad_win,
            {"process_classification": "GOOD_PROCESS_WIN", "narrative": "it made money"},
        )
        findings.append("ai_override_not_blocked")
    except HardBanViolation:
        pass

    merged = apply_ai_proposal(
        bad_win,
        {"process_classification": "GOOD_PROCESS_WIN", "dimensions": ["COST"]},
    )
    if merged["process_classification"] != "BAD_PROCESS_WIN":
        findings.append("ai_proposal_mutated_final_class")
    if merged["classifier_authority"]["ai_can_override"] is not False:
        findings.append("ai_can_override_true")
    if not merged["classifier_authority"]["ai_disagreement"]:
        findings.append("disagreement_not_flagged")

    # 2) Loss is not automatic BAD
    good_loss = fixtures["V16A_FIX_good_loss"]
    if not assert_loss_not_auto_bad(good_loss):
        findings.append("loss_auto_bad")

    # 3) Win is not automatic GOOD
    if not assert_win_not_auto_good(bad_win):
        findings.append("win_auto_good")

    # 4) Hard bans fire
    for fn in (
        refuse_real_money,
        refuse_mainnet,
        refuse_exchange_write,
        refuse_oos,
        refuse_walkforward,
        refuse_fabricated_ai_learning,
        refuse_pr26_merge,
        refuse_pr27_merge,
    ):
        try:
            fn()
            findings.append(f"ban_not_enforced:{fn.__name__}")
        except HardBanViolation:
            pass

    # 5) No status json / acceleration report in owned artifacts
    art = root / ARTIFACT_REL
    written = [str(p.relative_to(root)).replace("\\", "/") for p in art.rglob("*") if p.is_file()]
    try:
        assert_no_status_json_filenames(written)
        assert_no_acceleration_report_edit(written + list(OWNED_PATHS))
    except HardBanViolation as exc:
        findings.append(str(exc))

    # 6) Shock without process fault is UNAVOIDABLE; with fault is BAD
    shock = classify_trade_error(fixtures["V16A_FIX_unavoidable_shock"])
    mixed = classify_trade_error(fixtures["V16A_FIX_shock_with_cost_fault"])
    if shock["process_classification"] != "UNAVOIDABLE_SHOCK":
        findings.append("shock_misclassified")
    if mixed["process_classification"] != "BAD_PROCESS_LOSS":
        findings.append("shock_plus_fault_should_be_bad_process")

    return {
        "pass": 2,
        "name": "adversarial",
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "hard_ban_count": hard_ban_inventory()["count"],
        "ai_disagreement_preserved": merged["classifier_authority"]["ai_disagreement"],
        "final_class_locked": merged["process_classification"] == merged["deterministic_class"],
    }


def _pass3_independent_break(root: Path) -> dict[str, Any]:
    findings: list[str] = []
    # Mutation: force PnL-only classification must not be possible via API.
    pkt = {
        "trade_id": "V16A_BREAK_pnl_only",
        "net_pnl": -100.0,
        "entry_price": 1.0,
        "stop_price": 0.9,
        "target_price": 1.2,
        "cost_gate_status": "PASS",
        "risk_gate_status": "PASS",
        "data_quality_status": "OK",
        "position_size_valid": True,
        "liquidation_distance_valid": True,
        "rule_violation_count": 0,
        "prohibited_action_count": 0,
        "hard_block_reasons": [],
    }
    r = classify_trade_error(pkt)
    if r["process_classification"] != "GOOD_PROCESS_LOSS":
        findings.append("pnl_only_loss_not_good_process_loss")

    # Empty packet → insufficient
    empty = classify_trade_error({"trade_id": "V16A_BREAK_empty"})
    if empty["process_classification"] != "INSUFFICIENT_EVIDENCE":
        findings.append("empty_not_insufficient")

    # allow_override=True must raise
    try:
        apply_ai_proposal(pkt, {"process_classification": "BAD_PROCESS_LOSS"}, allow_override=True)
        findings.append("allow_override_not_refused")
    except HardBanViolation:
        pass

    # Gene bank checksum stability
    a = build_gene_bank()["checksum_sha256"]
    b = build_gene_bank()["checksum_sha256"]
    if a != b:
        findings.append("gene_bank_checksum_unstable")

    # Every dimension has ≥1 gene OR is declared (EXTERNAL_SHOCK + all listed)
    bank = build_gene_bank()
    covered = {g["dimension"] for g in bank["genes"]}
    missing_dims = [d for d in ERROR_DIMENSIONS if d not in covered]
    # DATA appears twice (stale + insufficient meta) — all dims should be covered.
    if missing_dims:
        findings.append(f"missing_gene_dimensions:{','.join(missing_dims)}")

    # Required hard bans present
    for ban in (
        "no_ai_override_of_deterministic_class",
        "no_real_money",
        "no_exchange_write",
        "no_oos",
        "no_walkforward",
        "no_fabricated_ai_learning",
        "no_pr26_merge",
        "no_pr27_merge",
        "no_status_json_lane_artifact",
    ):
        if ban not in HARD_BANS:
            findings.append(f"missing_hard_ban:{ban}")

    return {
        "pass": 3,
        "name": "independent_break",
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "gene_dimensions_covered": sorted(covered),
    }


def run_three_passes(root: Path | None = None) -> dict[str, Any]:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    p1 = _pass1_implementation(root)
    p2 = _pass2_adversarial(root)
    p3 = _pass3_independent_break(root)
    overall = "PASS" if all(p["status"] == "PASS" for p in (p1, p2, p3)) else "FAIL"

    # Write pass report (NOT *_status.json)
    art = root / ARTIFACT_REL
    art.mkdir(parents=True, exist_ok=True)
    report = {
        "lane": "V16-A",
        "schema": SCHEMA,
        "overall_status": overall,
        "passes": [p1, p2, p3],
        "owned_paths": list(OWNED_PATHS),
        "hard_bans": list(HARD_BANS),
    }
    report_path = art / "three_pass_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    hard_bans_path = art / "hard_bans.json"
    hard_bans_path.write_text(
        json.dumps(hard_ban_inventory(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
