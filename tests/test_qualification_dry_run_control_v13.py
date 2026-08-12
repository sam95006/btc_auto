"""Tests for Founder V13-F Qualification Dry-Run Control (blocked-only)."""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_qualification.dryrun_v13.checksums import (
    compute_code_checksum,
    compute_dataset_checksum,
    compute_parameter_checksum,
    compute_semantic_checksum,
    stamp_all_checksums,
    validate_checksums,
)
from backend.nexus_qualification.dryrun_v13.constants import (
    ALLOWED_DISCOVERY_LABELS,
    FORMAL_STAGES,
    FORMAL_STATUS_BLOCKED,
    HARD_BANS,
    INFRA_STATUS_BLOCKED_READY,
    OWNED_PATHS,
    SCHEMA_ID,
    STAGE_STATUS_BLOCKED,
)
from backend.nexus_qualification.dryrun_v13.controller import (
    QualificationDryRunControlV13F,
    run_qualification_dry_run_control,
    run_two_pass_dry_run,
    write_immutable_artifacts,
)
from backend.nexus_qualification.dryrun_v13.discovery_ingest import (
    build_synthetic_discovery_bundle,
    ingest_discovery_bundle,
    validate_discovery_bundle,
)
from backend.nexus_qualification.dryrun_v13.future_data import assert_future_data_excluded
from backend.nexus_qualification.dryrun_v13.replay import (
    run_development_replay,
    verify_development_replay_deterministic,
)

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = (
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)(?<!g)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)gsk_[A-Za-z0-9]{20,}"),
)


def test_schema_and_blocked_states():
    summary = run_qualification_dry_run_control()
    assert summary["schema"] == SCHEMA_ID
    assert summary["qualification_status"] == FORMAL_STATUS_BLOCKED
    assert summary["infrastructure_status"] == INFRA_STATUS_BLOCKED_READY
    assert summary["all_stages_blocked"] is True
    assert summary["qualification_ready_count"] == 0
    for stage in FORMAL_STAGES:
        assert summary["stages"][stage] == STAGE_STATUS_BLOCKED


def test_discovery_ingest_connects_outputs():
    ingested = ingest_discovery_bundle()
    assert ingested["ingested_candidate_count"] >= 2
    assert ingested["qualification_ready_count"] == 0
    assert ingested["selected_strategy"] is None
    for cand in ingested["strategy_discovery"]["candidates"]:
        assert cand["discovery_label"] in ALLOWED_DISCOVERY_LABELS
        assert cand["qualified"] is False
        assert cand["selected"] is False
        assert cand["promoted"] is False
        assert cand["fixture_only"] is True
        assert cand["semantic_checksum"]
        assert cand["parameter_checksum"]
        assert cand["code_checksum"]
        assert cand["dataset_checksum"]
        assert validate_checksums(cand, market=ingested["market_discovery"]) == []


def test_checksum_tamper_fail_closed():
    bundle = build_synthetic_discovery_bundle()
    market = bundle["market_discovery"]
    cand = stamp_all_checksums(bundle["strategy_discovery"]["candidates"][0], market=market)
    cand["semantic_checksum"] = "0" * 64
    assert "semantic_checksum_mismatch" in validate_checksums(cand, market=market)
    # Parameter / code / dataset integrity
    assert len(compute_semantic_checksum(cand)) == 64
    assert len(compute_parameter_checksum(cand)) == 64
    assert len(compute_code_checksum(cand)) == 64
    assert len(compute_dataset_checksum(cand, market)) == 64


def test_candidate_freeze_plan_not_executed():
    summary = run_qualification_dry_run_control()
    freeze = summary["proofs"]["candidate_freeze"]
    assert freeze["formal_candidate_freeze_executed"] is False
    assert freeze["all_blocked"] is True
    assert freeze["freeze_plan_count"] == summary["discovery_ingest"]["ingested_candidate_count"]
    for plan in freeze["plans"]:
        assert plan["formal_stage_status"] == STAGE_STATUS_BLOCKED
        assert plan["qualified"] is False
        assert plan["selected"] is False


def test_development_replay_deterministic_not_formal_wf():
    summary = run_qualification_dry_run_control()
    replay = summary["proofs"]["development_replay"]
    assert replay["formal_walk_forward_executed"] is False
    assert replay["all_deterministic"] is True
    assert replay["oos_touched"] is False
    assert replay["demo_order_count"] == 0
    assert summary["formal_walk_forward_executed"] is False

    cand = {
        **summary["discovery_ingest"]["checksums"][0],
        "development_interval": {
            "start_ms": 1_700_000_000_000 - 60 * 86_400_000,
            "end_ms": 1_700_000_000_000 - 30 * 86_400_000,
        },
        "eligible_symbol_profile": ["SYNTHUSDT"],
        "candidate_id": summary["discovery_ingest"]["candidate_ids"][0],
    }
    # Rebuild from ingest for full candidate
    ingested = ingest_discovery_bundle()
    full = ingested["strategy_discovery"]["candidates"][0]
    v = verify_development_replay_deterministic(full)
    assert v["match"] is True
    a = run_development_replay(full)
    assert a["formal_walk_forward"] is False
    assert a["profitability_claimed"] is False


def test_future_data_exclusion():
    summary = run_qualification_dry_run_control()
    assert summary["proofs"]["future_data_excluded"] is True
    assert summary["proofs"]["future_data_exclusion_violation_case"]["allowed"] is False
    assert summary["proofs"]["future_data_exclusion_valid_case"]["allowed"] is True
    assert summary["proofs"]["market_universe_pit"]["ok"] is True


def test_eligibility_plans_only_never_execute():
    summary = run_qualification_dry_run_control()
    plans = summary["proofs"]["eligibility_plans"]
    assert plans["formal_walk_forward_executed"] is False
    assert plans["oos_reservation_created"] is False
    assert plans["oos_executed"] is False
    assert plans["oos_consumed"] is False
    assert plans["demo_eligibility_granted"] is False
    assert plans["demo_order_count"] == 0
    assert plans["all_plans_not_executed"] is True
    assert len(plans["walk_forward_plans"]) >= 1
    assert len(plans["risk_review_plans"]) >= 1
    assert len(plans["oos_reservation_plans"]) >= 1
    assert len(plans["demo_eligibility_plans"]) >= 1


def test_hard_ban_flags_and_stage_refusals():
    ctrl = QualificationDryRunControlV13F()
    summary = ctrl.bootstrap()
    assert summary["Founder_authorization_present"] is False
    assert summary["formal_walk_forward_executed"] is False
    assert summary["oos_reservation_created"] is False
    assert summary["oos_executed"] is False
    assert summary["oos_consumed"] is False
    assert summary["strategy_selected"] is False
    assert summary["strategy_promoted"] is False
    assert summary["demo_order_count"] == 0
    assert summary["exchange_write_attempt_count"] == 0
    assert summary["pr27_merged"] is False
    assert summary["proofs"]["all_attempts_refused"] is True
    assert summary["proofs"]["all_selects_refused"] is True
    assert summary["proofs"]["all_promotes_refused"] is True
    for ban in (
        "no_formal_walk_forward",
        "no_real_oos_reservation",
        "no_real_oos_consumption",
        "no_strategy_selection",
        "no_strategy_promotion",
        "no_demo_orders",
        "no_pr27_merge",
    ):
        assert ban in HARD_BANS


def test_reject_qualified_discovery_label_bundle():
    bundle = build_synthetic_discovery_bundle()
    bundle["strategy_discovery"]["candidates"][0]["qualified"] = True
    errors = validate_discovery_bundle(bundle)
    assert any(e.startswith("candidate_marked_qualified") for e in errors)


def test_reject_non_fixture_and_oos_touched():
    bundle = build_synthetic_discovery_bundle()
    bundle["fixture_only"] = False
    assert "discovery_bundle_must_be_fixture_only" in validate_discovery_bundle(bundle)
    bundle = build_synthetic_discovery_bundle()
    bundle["real_oos_touched"] = True
    assert "real_oos_touched_forbidden" in validate_discovery_bundle(bundle)


def test_future_listed_symbol_rejected_from_eligible():
    bundle = build_synthetic_discovery_bundle()
    as_of = bundle["market_discovery"]["as_of_ms"]
    bundle["market_discovery"]["eligible_universe"].append(
        {
            "symbol": "LEAKEDFUTURE",
            "listing_timestamp_ms": as_of + 10,
            "fixture_only": True,
        }
    )
    errors = validate_discovery_bundle(bundle)
    assert any(e.startswith("future_listed_in_eligible") for e in errors)


def test_two_pass_adversarial_ok():
    report = run_two_pass_dry_run()
    assert report["both_passes_ok"] is True
    assert report["pass2"]["adversarial_ok"] is True
    assert report["qualification_ready_count"] == 0
    adv = report["pass2"]["adversarial"]
    assert adv["force_execute_walk_forward"]["allowed"] is False
    assert adv["force_select"]["allowed"] is False
    assert adv["force_promote"]["allowed"] is False
    assert adv["future_data_injection"]["allowed"] is False


def test_write_artifacts(tmp_path: Path):
    report = run_two_pass_dry_run()
    paths = write_immutable_artifacts(report, root=tmp_path)
    assert paths["status"].is_file()
    status = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert status["qualification_status"] == FORMAL_STATUS_BLOCKED
    assert status["infrastructure_status"] == INFRA_STATUS_BLOCKED_READY
    assert status["qualification_ready_count"] == 0
    assert status["formal_walk_forward_executed"] is False
    assert status["demo_order_count"] == 0
    two = json.loads(paths["two_pass"].read_text(encoding="utf-8"))
    assert two["both_passes_ok"] is True


def test_owned_paths_exist_and_secret_scan():
    for rel in OWNED_PATHS:
        # artifact dir may be created by harness; source paths must exist
        if rel.startswith("artifacts/"):
            continue
        assert (ROOT / rel).exists(), rel
    for rel in (
        "backend/nexus_qualification/dryrun_v13",
        "tools/research/run_qualification_dry_run_control_v13.py",
        "tests/test_qualification_dry_run_control_v13.py",
    ):
        target = ROOT / rel
        files = [target] if target.is_file() else list(target.rglob("*.py"))
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                assert pat.search(text) is None, f"{path}:{pat.pattern}"


def test_select_promote_remain_blocked_after_copy_mutation():
    """Negative: mutating a candidate copy cannot force selection through control plane."""
    summary = run_qualification_dry_run_control()
    mutated = copy.deepcopy(summary["discovery_ingest"]["checksums"][0])
    mutated["selected"] = True
    mutated["promoted"] = True
    mutated["qualified"] = True
    ctrl = QualificationDryRunControlV13F()
    ctrl.bootstrap()
    sel = ctrl.attempt_select_strategy(mutated["candidate_id"])
    promo = ctrl.attempt_promote_strategy(mutated["candidate_id"])
    assert sel["allowed"] is False
    assert promo["allowed"] is False
    # Control flags remain zero/false regardless of mutated copy.
    out = ctrl.summary()
    assert out["strategy_selected"] is False
    assert out["strategy_promoted"] is False
    assert out["qualification_ready_count"] == 0


def test_assert_future_data_excluded_unit():
    as_of = 1_700_000_000_000
    ok = assert_future_data_excluded(
        proposed_start_ms=as_of - 10, proposed_end_ms=as_of - 1, as_of_ms=as_of
    )
    bad = assert_future_data_excluded(
        proposed_start_ms=as_of - 10, proposed_end_ms=as_of + 1, as_of_ms=as_of
    )
    assert ok["allowed"] is True
    assert bad["allowed"] is False


def test_summary_ignores_mutated_control_flags():
    """Pass-2: mutating controller flags must not create a false PASS surface."""
    ctrl = QualificationDryRunControlV13F()
    ctrl.bootstrap()
    ctrl.flags["formal_walk_forward_executed"] = True
    ctrl.flags["oos_reservation_created"] = True
    ctrl.flags["oos_executed"] = True
    ctrl.flags["oos_consumed"] = True
    ctrl.flags["strategy_selected"] = True
    ctrl.flags["strategy_promoted"] = True
    ctrl.flags["demo_order_count"] = 7
    ctrl.flags["qualification_ready_count"] = 99
    ctrl.flags["pr27_merged"] = True
    ctrl.qualification_status = "READY"  # type: ignore[assignment]
    out = ctrl.summary()
    assert out["qualification_status"] == FORMAL_STATUS_BLOCKED
    assert out["infrastructure_status"] == INFRA_STATUS_BLOCKED_READY
    assert out["formal_walk_forward_executed"] is False
    assert out["oos_reservation_created"] is False
    assert out["oos_executed"] is False
    assert out["oos_consumed"] is False
    assert out["strategy_selected"] is False
    assert out["strategy_promoted"] is False
    assert out["demo_order_count"] == 0
    assert out["qualification_ready_count"] == 0
    assert out["pr27_merged"] is False


def test_reject_qualified_discovery_label_string():
    bundle = build_synthetic_discovery_bundle()
    bundle["strategy_discovery"]["candidates"][0]["discovery_label"] = "QUALIFIED"
    errors = validate_discovery_bundle(bundle)
    assert any(e.startswith("invalid_discovery_label") for e in errors)
