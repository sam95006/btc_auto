"""V15-I Reflection and Lesson Replay Lab — unit and adversarial tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_lesson_replay_v15.classification import (  # noqa: E402
    assert_loss_not_auto_bad,
    classify_from_evidence,
    migrate_classification,
)
from backend.nexus_lesson_replay_v15.checkpoint import load_checkpoint_readonly  # noqa: E402
from backend.nexus_lesson_replay_v15.constants import (  # noqa: E402
    CONTROL_FIXTURE_LABEL,
    HARD_BANS,
    OWNED_PATHS,
    PROCESS_CLASSES,
)
from backend.nexus_lesson_replay_v15.fixtures import labeled_fixture_controls  # noqa: E402
from backend.nexus_lesson_replay_v15.gate import (  # noqa: E402
    evaluate_real_lesson_gate,
    reject_forbidden_effect,
)
from backend.nexus_lesson_replay_v15.hard_bans import (  # noqa: E402
    HardBanViolation,
    assert_no_status_json_filenames,
    refuse_status_json_lane_artifact,
)
from backend.nexus_lesson_replay_v15.harness import (  # noqa: E402
    evaluate_lesson_replay_lab,
    write_immutable_artifacts,
)
from backend.nexus_lesson_replay_v15.replay_lab import classify_matrix, run_replay_lab  # noqa: E402
from backend.nexus_lesson_replay_v15.secret_scan import scan_payload  # noqa: E402
from backend.nexus_lesson_replay_v15.simulated_trades import (  # noqa: E402
    historical_simulated_completed_trades,
)
from backend.nexus_lesson_replay_v15.two_pass import run_two_pass  # noqa: E402

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
    assert "no_status_json_lane_artifact" in HARD_BANS
    assert "no_real_lesson_prevention_until_v23_verified" in HARD_BANS
    assert any("nexus_lesson_replay_v15" in p for p in OWNED_PATHS)


def test_migrate_classification():
    assert migrate_classification("PROCESS_UNDETERMINED") == "UNDETERMINED"
    assert migrate_classification("GOOD_PROCESS_LOSS") == "GOOD_PROCESS_LOSS"
    assert migrate_classification("junk") == "UNDETERMINED"


def test_loss_is_not_automatic_bad_process_fixture():
    packets = labeled_fixture_controls()
    good_loss = next(p for p in packets if p["trade_id"] == "V15I_FIX_good_loss")
    result = classify_from_evidence(good_loss)
    assert result["process_classification"] == "GOOD_PROCESS_LOSS"
    assert result["is_loss"] is True
    assert result["is_bad_process"] is False
    assert assert_loss_not_auto_bad(good_loss) is True


def test_loss_is_not_automatic_bad_process_sim():
    trades = historical_simulated_completed_trades()
    good_loss = next(p for p in trades if p["trade_id"] == "V15I_SIM_hist_good_loss_002")
    result = classify_from_evidence(good_loss)
    assert result["process_classification"] == "GOOD_PROCESS_LOSS"


def test_bad_process_win_not_auto_good():
    packets = labeled_fixture_controls()
    bad_win = next(p for p in packets if p["trade_id"] == "V15I_FIX_bad_cost_win")
    result = classify_from_evidence(bad_win)
    assert result["process_classification"] == "BAD_PROCESS_WIN"
    assert result["is_win"] is True
    assert result["is_good_process"] is False


def test_undetermined_insufficient_evidence():
    packets = labeled_fixture_controls()
    und = next(p for p in packets if p["trade_id"] == "V15I_FIX_undetermined")
    result = classify_from_evidence(und)
    assert result["process_classification"] == "UNDETERMINED"


def test_sim_and_fixture_matrices_cover_all_classes():
    sims = historical_simulated_completed_trades()
    fixtures = labeled_fixture_controls()
    for pkts in (sims, fixtures, sims + fixtures):
        matrix = classify_matrix(pkts)
        assert matrix["loss_is_not_automatic_bad_process"] is True
        assert all(matrix["required_classes_present"].values())


def test_fixtures_clearly_labelled():
    for p in labeled_fixture_controls():
        assert p["is_fixture"] is True
        assert p["fixture_label"] == CONTROL_FIXTURE_LABEL
        assert p["real_trading_learning"] is False or p.get("mechanics_only") is True


def test_sims_are_not_fixtures():
    for t in historical_simulated_completed_trades():
        assert t["is_fixture"] is False
        assert t["completed"] is True
        assert t["exchange_write"] is False
        assert t["historical_sim_label"]
        assert t["process_record_label"]


def test_replay_lab_pass_fixture_and_sim():
    lab = run_replay_lab()
    assert lab["replay_lab_status"] == "PASS"
    assert lab["misrepresented_as_real_learning"] is False
    assert lab["fixture_as_real_policy_effect_proof"] is False
    assert lab["new_policy_effect_lesson_count"] == 0
    assert lab["historical_simulated_trade_count"] >= 5
    assert lab["labeled_fixture_count"] >= 5
    assert lab["classification_matrix"]["labeled_fixtures"]["clearly_labelled"] is True


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


def test_real_gate_still_blocked_without_full_chain_even_if_verified_flags_spoofed():
    # Spoof VERIFIED without the remaining chain requirements → still BLOCKED.
    gate = evaluate_real_lesson_gate(
        v23_terminal_status="VERIFIED",
        v23_complete=True,
        quality_gates_passed=True,
        has_real_bad_process_source=True,
        lesson_retrieved=False,
        measurable_process_change=False,
        repeat_error_prevention=False,
    )
    assert gate["REAL_LESSON_PREVENTION_STATUS"] == "BLOCKED"
    assert "LESSON_NOT_RETRIEVED" in str(gate.get("blocked_reason"))


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


def test_secret_scan_clean_and_detects_assignment():
    clean = scan_payload({"lesson_id": "abc", "effect": "candidate_rejected"})
    assert clean["pass"] is True
    dirty = scan_payload({"api_key": "sk_live_12345678901234567890"})
    assert dirty["secret_leak_count"] >= 1


def test_status_json_hard_ban():
    with pytest.raises(HardBanViolation):
        refuse_status_json_lane_artifact()
    with pytest.raises(HardBanViolation):
        assert_no_status_json_filenames(["summary.json", "v15_i_status.json"])


def test_two_pass_ok_on_valid_bundle():
    result = evaluate_lesson_replay_lab(root=ROOT)
    assert result["REAL_LESSON_PREVENTION_STATUS"] == "BLOCKED"
    assert result["replay_lab_status"] == "PASS"
    assert result["two_pass"]["two_pass_ok"] is True
    assert result["pass"] is True
    assert result["new_policy_effect_lesson_count"] == 0
    assert result["auto_integrate"] is False
    assert result["wrote_status_json"] is False


def test_write_immutable_artifacts_no_status_json(tmp_path: Path):
    result = evaluate_lesson_replay_lab(root=ROOT)
    art_root = tmp_path
    (art_root / "artifacts" / "readiness" / "immutable").mkdir(parents=True)
    written = write_immutable_artifacts(result, root=art_root, commit="deadbeef")
    names = [p.name for p in written.iterdir()]
    assert "summary.json" in names
    assert "two_pass_report.json" in names
    assert "pass1_summary.json" in names
    assert "pass2_adversarial.json" in names
    assert "simulated_trades.json" in names
    assert "fixture_controls.json" in names
    assert "real_lesson_prevention_gate.json" in names
    assert not any(n.endswith("_status.json") for n in names)
    body = json.loads((written / "summary.json").read_text(encoding="utf-8"))
    assert body["REAL_LESSON_PREVENTION_STATUS"] == "BLOCKED"
    assert body["wrote_status_json"] is False
    assert body["auto_integrate"] is False


def test_two_pass_flags_bypass():
    bad_bundle = {
        "real_gate": {
            "REAL_LESSON_PREVENTION_STATUS": "READY",
            "new_policy_effect_lesson_count": 1,
        },
        "replay_lab": {
            "replay_lab_status": "PASS",
            "misrepresented_as_real_learning": False,
            "fixture_as_real_policy_effect_proof": False,
            "historical_simulated_trade_count": 8,
            "classification_matrix": {
                "combined": {
                    "loss_is_not_automatic_bad_process": True,
                    "required_classes_present": {
                        "GOOD_PROCESS_WIN": True,
                        "GOOD_PROCESS_LOSS": True,
                        "BAD_PROCESS_WIN": True,
                        "BAD_PROCESS_LOSS": True,
                        "UNDETERMINED": True,
                    },
                },
                "labeled_fixtures": {"clearly_labelled": True},
            },
        },
        "checkpoint": {"V2_3_complete": False, "mutated": False},
        "hard_bans": list(HARD_BANS),
        "secret_leak_count": 0,
        "auto_integrate": False,
        "pr27_merged": False,
        "wrote_status_json": False,
    }
    report = run_two_pass(bad_bundle)
    assert report["two_pass_ok"] is False
    assert report["pass1"]["critical_count"] >= 1
