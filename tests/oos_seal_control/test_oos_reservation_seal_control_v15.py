"""Focused tests for V15-G OOS Reservation and Seal Control."""
from __future__ import annotations

import json
from pathlib import Path

from backend.nexus_oos_seal_control.bans import (
    assert_required_false_flags,
    hard_ban_probe_matrix,
    refuse_real_oos_reservation,
)
from backend.nexus_oos_seal_control.bindings import (
    build_bindings,
    compute_code_checksum,
    synthetic_candidate,
    synthetic_dataset,
    verify_bindings_intact,
)
from backend.nexus_oos_seal_control.constants import (
    ARTIFACT_REL,
    FORBIDDEN_STATUS_BASENAMES,
    FORBIDDEN_STATUS_JSON_SUFFIX,
    PLAN_STATUS_PLANNED_NOT_RESERVED,
    SEAL_STATUS_PLAN_SEALED_NOT_RESERVED,
)
from backend.nexus_oos_seal_control.controller import run_two_pass, write_immutable_artifacts
from backend.nexus_oos_seal_control.founder_auth import FounderAuthorizationGate
from backend.nexus_oos_seal_control.intervals import (
    build_interval_plan,
    prove_non_consumption,
    synthetic_planning_registries,
)
from backend.nexus_oos_seal_control.seals import SealLineageStore, build_lineage_seal, reset_seal_lineage


ROOT = Path(__file__).resolve().parents[2]


def test_interval_plan_not_reserved() -> None:
    regs = synthetic_planning_registries()
    plan = build_interval_plan(regs)
    assert plan["plan_status"] == PLAN_STATUS_PLANNED_NOT_RESERVED
    assert plan["oos_reserved"] is False
    assert plan["oos_downloaded"] is False
    assert plan["oos_executed"] is False
    assert plan["oos_consumed"] is False
    assert plan["real_oos_reservation_executed"] is False
    assert plan["checks"]["no_overlap_with_development"] is True


def test_bindings_and_non_consumption() -> None:
    candidate = synthetic_candidate()
    dataset = synthetic_dataset()
    plan = build_interval_plan(synthetic_planning_registries())
    code_checksum = compute_code_checksum(ROOT / "backend" / "nexus_oos_seal_control")
    bindings = build_bindings(
        candidate, dataset, code_checksum=code_checksum, plan_checksum=plan["plan_checksum"]
    )
    assert verify_bindings_intact(bindings)["intact"] is True
    proof = prove_non_consumption(plan)
    assert proof["proven"] is True
    assert proof["oos_consumed"] is False


def test_write_once_and_anti_regeneration() -> None:
    store = SealLineageStore()
    reset_seal_lineage(store)
    candidate = synthetic_candidate()
    dataset = synthetic_dataset()
    plan = build_interval_plan(synthetic_planning_registries())
    bindings = build_bindings(
        candidate,
        dataset,
        code_checksum=compute_code_checksum(ROOT / "backend" / "nexus_oos_seal_control"),
        plan_checksum=plan["plan_checksum"],
    )
    seal1 = build_lineage_seal(plan=plan, bindings=bindings, store=store)
    assert seal1["allowed"] is True
    assert seal1["status"] == SEAL_STATUS_PLAN_SEALED_NOT_RESERVED
    seal2 = build_lineage_seal(plan=plan, bindings=bindings, store=store)
    assert seal2["seal"] == seal1["seal"]

    mutated = dict(plan)
    mutated["plan_checksum"] = "a" * 64
    rejected = build_lineage_seal(plan=mutated, bindings=bindings, store=store)
    assert rejected["allowed"] is False
    assert rejected["anti_regeneration"] is True

    force = build_lineage_seal(plan=plan, bindings=bindings, store=store, force_overwrite=True)
    assert force["allowed"] is False


def test_founder_auth_spoof_rejected() -> None:
    gate = FounderAuthorizationGate()
    body = gate.evaluate()
    assert body["authorized"] is False
    assert gate.verify_bound_result(body)["valid"] is True
    spoof = gate.attempt_spoof_authorized()
    assert spoof["valid"] is False
    assert spoof["spoof_rejected"] is True


def test_hard_bans_refuse_real_reservation() -> None:
    refuse = refuse_real_oos_reservation("PLAN_X")
    assert refuse["allowed"] is False
    assert refuse["oos_reserved"] is False
    probe = hard_ban_probe_matrix()
    assert probe["all_refused"] is True
    flags = assert_required_false_flags()
    assert flags["ok"] is True


def test_two_pass_and_artifacts() -> None:
    two = run_two_pass(root=ROOT)
    assert two["both_passes_ok"] is True
    assert two["oos_reserved"] is False
    assert two["oos_downloaded"] is False
    assert two["oos_executed"] is False
    assert two["oos_consumed"] is False
    assert two["pass1"]["proofs"]["anti_regeneration_rejected"] is True
    assert two["pass2"]["adversarial"]["flag_injection_detected"] is True

    paths = write_immutable_artifacts(two, root=ROOT)
    assert paths["two_pass"].exists()
    assert paths["seal"].exists()
    report = json.loads(paths["two_pass"].read_text(encoding="utf-8"))
    assert report["both_passes_ok"] is True
    assert report["oos_reserved"] is False

    art = ROOT / ARTIFACT_REL
    for path in art.rglob("*.json"):
        name = path.name.lower()
        assert name not in FORBIDDEN_STATUS_BASENAMES
        assert not name.endswith(FORBIDDEN_STATUS_JSON_SUFFIX)


def test_flag_injection_detected() -> None:
    bad = {
        "oos_reserved": True,
        "oos_downloaded": False,
        "oos_executed": False,
        "oos_consumed": False,
    }
    check = assert_required_false_flags(bad)
    assert check["ok"] is False
    assert "oos_reserved" in check["violations"]
