"""V14-G Lesson Prevention Proof V2 — unit and mechanics tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_lesson_prevention_v2.classification import (  # noqa: E402
    assert_loss_not_auto_bad,
    classify_from_evidence,
    migrate_classification,
)
from backend.nexus_lesson_prevention_v2.checkpoint import load_checkpoint_readonly  # noqa: E402
from backend.nexus_lesson_prevention_v2.constants import (  # noqa: E402
    HARD_BANS,
    OWNED_PATHS,
    PROCESS_CLASSES,
)
from backend.nexus_lesson_prevention_v2.fixtures import mechanics_fixture_packets  # noqa: E402
from backend.nexus_lesson_prevention_v2.gate import (  # noqa: E402
    evaluate_real_lesson_gate,
    reject_forbidden_effect,
)
from backend.nexus_lesson_prevention_v2.harness import (  # noqa: E402
    evaluate_lesson_prevention_v2,
    write_immutable_artifacts,
)
from backend.nexus_lesson_prevention_v2.mechanics import (  # noqa: E402
    classify_fixture_matrix,
    run_mechanics_chain_proof,
)
from backend.nexus_lesson_prevention_v2.real_proof import run_real_policy_effect_proof  # noqa: E402
from backend.nexus_lesson_prevention_v2.secret_scan import scan_payload  # noqa: E402
from backend.nexus_lesson_prevention_v2.two_pass import run_two_pass  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def test_process_classes_inventory():
    assert set(PROCESS_CLASSES) == {
        "GOOD_PROCESS_WIN",
        "GOOD_PROCESS_LOSS",
        "BAD_PROCESS_WIN",
        "BAD_PROCESS_LOSS",
        "UNDETERMINED",
    }
    assert "no_loss_as_automatic_bad_process" in HARD_BANS
    assert "no_auto_integrate" in HARD_BANS
    assert any("nexus_lesson_prevention_v2" in p for p in OWNED_PATHS)


def test_migrate_classification():
    assert migrate_classification("PROCESS_UNDETERMINED") == "UNDETERMINED"
    assert migrate_classification("GOOD_PROCESS_LOSS") == "GOOD_PROCESS_LOSS"
    assert migrate_classification("junk") == "UNDETERMINED"


def test_loss_is_not_automatic_bad_process():
    packets = mechanics_fixture_packets()
    good_loss = next(p for p in packets if p["trade_id"] == "V14G_FIX_good_loss")
    result = classify_from_evidence(good_loss)
    assert result["process_classification"] == "GOOD_PROCESS_LOSS"
    assert result["is_loss"] is True
    assert result["is_bad_process"] is False
    assert assert_loss_not_auto_bad(good_loss) is True


def test_bad_process_win_not_auto_good():
    packets = mechanics_fixture_packets()
    bad_win = next(p for p in packets if p["trade_id"] == "V14G_FIX_bad_cost_win")
    result = classify_from_evidence(bad_win)
    assert result["process_classification"] == "BAD_PROCESS_WIN"
    assert result["is_win"] is True
    assert result["is_good_process"] is False


def test_undetermined_insufficient_evidence():
    packets = mechanics_fixture_packets()
    und = next(p for p in packets if p["trade_id"] == "V14G_FIX_undetermined")
    result = classify_from_evidence(und)
    assert result["process_classification"] == "UNDETERMINED"


def test_fixture_matrix_covers_all_classes():
    matrix = classify_fixture_matrix()
    assert matrix["loss_is_not_automatic_bad_process"] is True
    assert all(matrix["required_classes_present"].values())


def test_mechanics_chain_pass_fixture_only():
    proof = run_mechanics_chain_proof()
    assert proof["mechanics_proof_status"] == "PASS"
    assert proof["misrepresented_as_real_learning"] is False
    assert proof["fixture_as_real_policy_effect_proof"] is False
    assert proof["new_policy_effect_lesson_count"] == 0
    assert proof["measurable_change"] is True
    assert proof["hard_risk_override_path_test_status"] == "PASS"


def test_real_gate_blocked_while_incomplete():
    gate = evaluate_real_lesson_gate(
        v23_terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        v23_complete=False,
        quality_gates_passed=False,
        has_real_bad_process_source=False,
    )
    assert gate["REAL_LESSON_PREVENTION_STATUS"] == "BLOCKED"
    assert gate["policy_effect_lesson_allowed"] is False
    assert gate["new_policy_effect_lesson_count"] == 0


def test_forbidden_effect_rejected():
    r = reject_forbidden_effect("increase_leverage")
    assert r["forbidden"] is True
    assert r["deterministic_rejected"] is True
    assert r["mutation_applied"] is False


def test_checkpoint_readonly_incomplete():
    ckpt = load_checkpoint_readonly()
    assert ckpt["read_only"] is True
    assert ckpt["mutated"] is False
    if ckpt["checkpoint_found"]:
        assert ckpt["V2_3_complete"] is False
        assert ckpt["V2_3_terminal_status"] != "VERIFIED"
        assert int(ckpt.get("groq_success_count") or 0) == 53


def test_real_proof_blocked_uses_no_fixtures_as_real():
    ckpt = load_checkpoint_readonly()
    # Even if we pass fixture packets, they must not count as real sources.
    real = run_real_policy_effect_proof(
        checkpoint=ckpt,
        real_bad_process_packets=mechanics_fixture_packets(),
        quality_gates_passed=False,
    )
    assert real["REAL_LESSON_PREVENTION_STATUS"] == "BLOCKED"
    assert real["fixture_used_as_real_proof"] is False
    assert real["new_policy_effect_lesson_count"] == 0
    assert real["genuine_bad_process_source_trade_count"] == 0


def test_secret_scan_clean_and_detects_assignment():
    clean = scan_payload({"lesson_id": "abc", "effect": "candidate_rejected"})
    assert clean["pass"] is True
    dirty = scan_payload({"api_key": "sk_live_12345678901234567890"})
    assert dirty["secret_leak_count"] >= 1


def test_two_pass_ok_on_valid_bundle():
    status = evaluate_lesson_prevention_v2(root=ROOT)
    assert status["REAL_LESSON_PREVENTION_STATUS"] == "BLOCKED"
    assert status["mechanics_proof_status"] == "PASS"
    assert status["two_pass"]["two_pass_ok"] is True
    assert status["pass"] is True
    assert status["new_policy_effect_lesson_count"] == 0
    assert status["auto_integrate"] is False


def test_write_immutable_artifacts(tmp_path: Path):
    # Evaluate against real checkpoint, write into temp tree mirroring owned path.
    status = evaluate_lesson_prevention_v2(root=ROOT)
    # Monkeypatch ARTIFACT write via root=tmp with same relative layout
    art_root = tmp_path
    (art_root / "artifacts" / "readiness" / "immutable").mkdir(parents=True)
    # Copy minimal package import path by writing into tmp using harness helper
    # Point write to temp by temporarily using status + custom root that has ARTIFACT_REL
    written = write_immutable_artifacts(status, root=art_root, commit="deadbeef")
    assert (written / "lesson_prevention_v2_status.json").is_file()
    assert (written / "mechanics_proof.json").is_file()
    assert (written / "real_policy_effect_proof.json").is_file()
    assert (written / "two_pass_report.json").is_file()
    body = json.loads((written / "summary.json").read_text(encoding="utf-8"))
    assert body["REAL_LESSON_PREVENTION_STATUS"] == "BLOCKED"
    assert body["auto_integrate"] is False


def test_two_pass_flags_bypass():
    bad_bundle = {
        "real_gate": {
            "REAL_LESSON_PREVENTION_STATUS": "READY",
            "new_policy_effect_lesson_count": 1,
        },
        "mechanics": {
            "mechanics_proof_status": "PASS",
            "misrepresented_as_real_learning": False,
            "classification_matrix": {
                "loss_is_not_automatic_bad_process": True,
                "required_classes_present": {
                    "GOOD_PROCESS_WIN": True,
                    "GOOD_PROCESS_LOSS": True,
                    "BAD_PROCESS_WIN": True,
                    "BAD_PROCESS_LOSS": True,
                    "UNDETERMINED": True,
                },
            },
        },
        "checkpoint": {"V2_3_complete": False, "mutated": False},
        "hard_bans": list(HARD_BANS),
        "secret_leak_count": 0,
        "auto_integrate": False,
        "pr27_merged": False,
    }
    report = run_two_pass(bad_bundle)
    assert report["two_pass_ok"] is False
    assert report["pass1"]["critical_count"] >= 1
