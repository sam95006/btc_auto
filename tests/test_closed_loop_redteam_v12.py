"""V12-F Closed-Loop Red Team — fail-closed adversarial proofs."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_autonomy.closed_loop_redteam_v12.constants import (  # noqa: E402
    HARD_BANS,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    SCENARIO_IDS,
)
from backend.nexus_autonomy.closed_loop_redteam_v12.redteam import (  # noqa: E402
    evaluate_closed_loop_redteam,
    run_closed_loop_redteam,
    write_immutable_artifacts,
)
from backend.nexus_autonomy.closed_loop_redteam_v12.scenarios import (  # noqa: E402
    run_all_scenarios,
    scenario_checkpoint_rollback,
    scenario_duplicate_candidate_decision_intent,
    scenario_exchange_write_attempts,
    scenario_exit_before_position_snapshot,
    scenario_ledger_fork,
    scenario_lesson_before_verified_reflection,
    scenario_mainnet_profile_confusion,
    scenario_oos_authorization_spoof,
    scenario_partial_fill_crash,
    scenario_reflection_before_exit,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    return tmp_path / "clrt_work"


def test_all_required_scenarios_listed():
    required = {
        "duplicate_candidate_decision_intent",
        "partial_fill_crash",
        "exit_before_position_snapshot",
        "reflection_before_exit",
        "lesson_before_verified_reflection",
        "checkpoint_rollback",
        "ledger_fork",
        "oos_authorization_spoof",
        "exchange_write_attempts",
        "mainnet_profile_confusion",
    }
    assert set(SCENARIO_IDS) == required
    assert len(SCENARIO_IDS) == 10
    assert "no_auto_integration_into_PR27" in HARD_BANS
    assert any("closed_loop_redteam_v12" in p for p in OWNED_PATHS)


def test_duplicate_candidate_decision_intent(workdir: Path):
    r = scenario_duplicate_candidate_decision_intent(workdir)
    assert r.passed and r.fail_closed and r.attack_blocked


def test_partial_fill_crash(workdir: Path):
    r = scenario_partial_fill_crash(workdir)
    assert r.passed and r.attack_blocked


def test_exit_before_position_snapshot(workdir: Path):
    assert scenario_exit_before_position_snapshot(workdir).passed


def test_reflection_before_exit(workdir: Path):
    assert scenario_reflection_before_exit(workdir).passed


def test_lesson_before_verified_reflection(workdir: Path):
    assert scenario_lesson_before_verified_reflection(workdir).passed


def test_checkpoint_rollback(workdir: Path):
    assert scenario_checkpoint_rollback(workdir).passed


def test_ledger_fork(workdir: Path):
    assert scenario_ledger_fork(workdir).passed


def test_oos_authorization_spoof(workdir: Path):
    assert scenario_oos_authorization_spoof(workdir).passed


def test_exchange_write_attempts(workdir: Path):
    assert scenario_exchange_write_attempts(workdir).passed


def test_mainnet_profile_confusion(workdir: Path):
    assert scenario_mainnet_profile_confusion(workdir).passed


def test_run_all_scenarios(workdir: Path):
    results = run_all_scenarios(workdir)
    assert len(results) == len(SCENARIO_IDS)
    assert all(r.passed for r in results)


def test_evaluate_and_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Keep runtime writes under tmp for unit test.
    monkeypatch.setattr(
        "backend.nexus_autonomy.closed_loop_redteam_v12.redteam.write_runtime_status",
        lambda *a, **k: {},
    )
    status = evaluate_closed_loop_redteam(root=ROOT, workdir=tmp_path / "eval")
    assert status["scenario_pass_count"] == status["scenario_total_count"] == 10
    assert status["passed"] is True
    assert status["recommendation"] == PASS_RECOMMENDATION
    assert status["exchange_write_attempt_count"] == 0
    assert status["mainnet_client_created_count"] == 0
    assert status["demo_order_count"] == 0
    assert status["auto_integration"] is False

    art_root = tmp_path / "repo"
    (art_root / "artifacts" / "readiness" / "immutable").mkdir(parents=True)
    # Point immutable writer at tmp by monkeypatching repo root via root=arg
    paths = write_immutable_artifacts(root=art_root, status=status)
    assert paths["status"].exists()
    loaded = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert loaded["passed"] is True
    assert loaded["attack_blocked_count"] == 10


def test_run_closed_loop_redteam_no_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "backend.nexus_autonomy.closed_loop_redteam_v12.redteam.write_runtime_status",
        lambda *a, **k: {},
    )
    art_root = tmp_path / "repo2"
    status = run_closed_loop_redteam(
        root=art_root,
        write_artifact=True,
        write_runtime=False,
        commit="deadbeef",
    )
    assert status["passed"] is True
    assert status["commit"] == "deadbeef"
    assert (
        art_root
        / "artifacts"
        / "readiness"
        / "immutable"
        / "v12_closed_loop_redteam"
        / "closed_loop_redteam_status.json"
    ).exists()
