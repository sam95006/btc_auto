"""V15-L Private Core Final False-Pass Red Team — fail-closed adversarial proofs."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_private_core_redteam.constants import (  # noqa: E402
    ATTACK_SCENARIO_IDS,
    FIXTURE_IDS,
    HARD_BANS,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
)
from backend.nexus_private_core_redteam.fixtures import (  # noqa: E402
    checkpoint_mutation_fixture,
    concurrency_fuzz_fixture,
    property_fuzz_research_seals,
    result_mutation_fixture,
    run_all_fixtures,
    schema_mutation_result,
)
from backend.nexus_private_core_redteam.redteam import (  # noqa: E402
    evaluate_private_core_redteam,
    run_private_core_redteam,
    write_immutable_artifacts,
)
from backend.nexus_private_core_redteam.scenarios import (  # noqa: E402
    ScenarioResult,
    run_all_scenarios,
    run_ledger_mutation_fixture,
    scenario_capacity_as_quality,
    scenario_candidate_relabeling,
    scenario_checkpoint_rollback,
    scenario_cost_omission,
    scenario_counter_inflation,
    scenario_development_oos_confusion,
    scenario_duplicate_lifecycle,
    scenario_exchange_write_bypass,
    scenario_fabricated_universe,
    scenario_founder_auth_spoof,
    scenario_future_data_leakage,
    scenario_ledger_fork,
    scenario_lesson_before_reflection,
    scenario_mainnet_profile_confusion,
    scenario_result_cherry_picking,
    scenario_risk_bypass,
    scenario_secret_leakage,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    return tmp_path / "v15l_work"


def test_required_scenarios_and_hard_bans():
    required = {
        "future_data_leakage",
        "development_oos_confusion",
        "fabricated_universe",
        "cost_omission",
        "result_cherry_picking",
        "candidate_relabeling",
        "counter_inflation",
        "checkpoint_rollback",
        "ledger_fork",
        "duplicate_lifecycle",
        "risk_bypass",
        "lesson_before_reflection",
        "capacity_as_quality",
        "founder_auth_spoof",
        "exchange_write_bypass",
        "mainnet_profile_confusion",
        "secret_leakage",
    }
    assert set(ATTACK_SCENARIO_IDS) == required
    assert len(ATTACK_SCENARIO_IDS) == 17
    assert "no_platform_blocked_mutation_as_pass" in HARD_BANS
    assert "no_provider_capacity_as_quality" in HARD_BANS
    assert "no_lesson_before_reflection" in HARD_BANS
    assert "no_risk_bypass" in HARD_BANS
    assert "no_duplicate_lifecycle_objects" in HARD_BANS
    assert "no_surviving_critical_mutation_as_pass" in HARD_BANS
    assert any("nexus_private_core_redteam" in p for p in OWNED_PATHS)
    assert set(FIXTURE_IDS) == {
        "property_fuzz_research_seals",
        "schema_mutation_result",
        "result_mutation",
        "checkpoint_mutation",
        "ledger_mutation",
        "concurrency_fuzz",
    }


@pytest.mark.parametrize(
    "fn",
    [
        scenario_future_data_leakage,
        scenario_development_oos_confusion,
        scenario_fabricated_universe,
        scenario_cost_omission,
        scenario_result_cherry_picking,
        scenario_candidate_relabeling,
        scenario_counter_inflation,
        scenario_checkpoint_rollback,
        scenario_ledger_fork,
        scenario_duplicate_lifecycle,
        scenario_risk_bypass,
        scenario_lesson_before_reflection,
        scenario_capacity_as_quality,
        scenario_founder_auth_spoof,
        scenario_exchange_write_bypass,
        scenario_mainnet_profile_confusion,
        scenario_secret_leakage,
    ],
)
def test_each_attack_scenario(fn, workdir: Path):
    r = fn(workdir)
    assert isinstance(r, ScenarioResult)
    assert r.passed and r.fail_closed and r.attack_blocked
    assert r.platform_blocked is False


def test_run_all_scenarios(workdir: Path):
    results = run_all_scenarios(workdir)
    assert len(results) == len(ATTACK_SCENARIO_IDS)
    assert all(r.passed and not r.platform_blocked for r in results)


def test_fixtures(workdir: Path):
    assert property_fuzz_research_seals(seed=15, rounds=32)["passed"] is True
    assert schema_mutation_result()["passed"] is True
    assert result_mutation_fixture()["passed"] is True
    assert checkpoint_mutation_fixture(workdir)["passed"] is True
    assert run_ledger_mutation_fixture(workdir)["passed"] is True
    assert concurrency_fuzz_fixture(workdir, workers=6, rounds=8)["passed"] is True
    fxs = run_all_fixtures(workdir, root=ROOT)
    assert len(fxs) == len(FIXTURE_IDS)
    assert all(f["passed"] for f in fxs)


def test_evaluate_and_artifacts(tmp_path: Path):
    status = evaluate_private_core_redteam(root=ROOT, workdir=tmp_path / "eval", pass_number=1)
    assert status["scenario_pass_count"] == status["scenario_total_count"] == 17
    assert status["fixture_pass_count"] == status["fixture_total_count"] == 6
    assert status["platform_blocked_pass_count"] == 0
    assert status["exchange_write_attempt_count"] == 0
    assert status["mainnet_client_created_count"] == 0
    assert status["demo_order_count"] == 0
    assert status["auto_integration"] is False
    assert status["production_ast"]["platform_blocked_pass_count"] == 0
    assert status["production_ast"]["survivors"] == 0
    assert status["passed"] is True
    assert status["recommendation"] == PASS_RECOMMENDATION
    assert status["v15_readiness_blocked_by_survivors"] is False

    art_root = tmp_path / "repo"
    (art_root / "artifacts" / "readiness" / "immutable").mkdir(parents=True)
    paths = write_immutable_artifacts(root=art_root, status=status)
    assert paths["report"].exists()
    assert paths["summary"].exists()
    assert "status.json" not in paths["report"].name
    loaded = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert loaded["passed"] is True
    assert loaded["attack_blocked_count"] == 17


def test_run_private_core_redteam_no_runtime_status(tmp_path: Path):
    art_root = tmp_path / "repo2"
    status = run_private_core_redteam(
        root=art_root,
        write_artifact=True,
        commit="deadbeef",
        pass_number=2,
    )
    assert status["commit"] == "deadbeef"
    assert status["pass_number"] == 2
    out = art_root / "artifacts" / "readiness" / "immutable" / "v15_private_core_redteam"
    assert out.exists()
    names = {p.name for p in out.iterdir()}
    assert "private_core_redteam_summary.json" in names
    assert "private_core_redteam_report.json" in names
    assert not any(n.endswith("_status.json") for n in names)


# ---------------------------------------------------------------------------
# PASS 2 — adversarial / negative tests (false-PASS hunters)
# ---------------------------------------------------------------------------


def test_pass2_platform_blocked_never_counts_as_pass():
    from backend.nexus_private_core_redteam.redteam import _critical_findings

    fake = [
        ScenarioResult(
            scenario_id="exchange_write_bypass",
            passed=False,
            fail_closed=True,
            detail="platform_blocked_not_pass",
            critical=True,
            attack_blocked=False,
            platform_blocked=True,
        )
    ]
    findings = _critical_findings(
        fake,
        [{"fixture_id": "ledger_mutation", "passed": True}],
        {"passed": True, "unresolved_blockers": []},
    )
    assert any("platform_blocked_not_pass" in f["code"] for f in findings)


def test_pass2_future_data_nested_key_must_trip(workdir: Path):
    r = scenario_future_data_leakage(workdir)
    assert r.evidence["dirty"]["violation_count"] >= 1
    assert r.evidence["clean"]["future_data_excluded"] is True


def test_pass2_oos_confusion_and_consumption(workdir: Path):
    r = scenario_development_oos_confusion(workdir)
    assert r.evidence["dirty_oos"]["proven"] is False
    assert r.evidence["clean_oos"]["proven"] is True
    assert r.evidence["relabel"]["ok"] is False


def test_pass2_fabricated_universe_excludes_future(workdir: Path):
    r = scenario_fabricated_universe(workdir)
    assert "FUTUREUSDT" in r.evidence["attack"]["fabricated"]
    assert "FUTUREUSDT" not in r.evidence["pit"]


def test_pass2_duplicate_lifecycle_collapses(workdir: Path):
    r = scenario_duplicate_lifecycle(workdir)
    assert r.evidence["honest"]["ok"] is True
    assert r.evidence["attack"]["ok"] is False
    assert r.evidence["second"]["duplicate"] is True


def test_pass2_risk_bypass_forbidden_rejected(workdir: Path):
    r = scenario_risk_bypass(workdir)
    assert r.evidence["forbidden"]["allowed"] is False
    assert r.evidence["ceiling"]["allowed"] is False
    assert r.evidence["attack"]["status"] == "RISK_BYPASS"


def test_pass2_lesson_before_reflection_blocked(workdir: Path):
    r = scenario_lesson_before_reflection(workdir)
    assert r.evidence["blocked_gate"]["lesson_prevention_executed"] is False
    assert r.evidence["premature"]["status"] == "LESSON_BEFORE_REFLECTION"


def test_pass2_capacity_not_quality(workdir: Path):
    r = scenario_capacity_as_quality(workdir)
    assert r.evidence["attack_claim"]["ok"] is False
    assert r.evidence["honest"]["ok"] is True


def test_pass2_counter_inflation_detects_invented(workdir: Path):
    r = scenario_counter_inflation(workdir)
    assert "invented" in r.evidence["inflated"]["inflated"]


def test_pass2_secret_value_never_in_public_blob(workdir: Path):
    r = scenario_secret_leakage(workdir)
    assert r.evidence["not_echoed"] is True
    assert r.evidence["detected"] is True


def test_pass2_checkpoint_rollback_sequence_must_drop(workdir: Path):
    r = scenario_checkpoint_rollback(workdir)
    assert r.evidence["rollback_detected"] is True
    assert r.evidence["rolled_sequence"] < r.evidence["sealed_sequence"]


def test_pass2_no_fixture_only_pass_without_scenarios(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "backend.nexus_private_core_redteam.redteam.run_all_scenarios",
        lambda *_a, **_k: [],
    )
    status = evaluate_private_core_redteam(root=ROOT, workdir=tmp_path / "empty", pass_number=2)
    assert status["passed"] is False
    assert status["recommendation"] != PASS_RECOMMENDATION


def test_pass2_survivors_block_v15_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Surviving Critical mutations must block V15 readiness."""
    monkeypatch.setattr(
        "backend.nexus_private_core_redteam.redteam.run_v15_production_ast_campaign",
        lambda **_k: {
            "passed": False,
            "killed": 0,
            "survivors": 1,
            "equivalent": 0,
            "errors": 0,
            "platform_blocked_count": 0,
            "platform_blocked_pass_count": 0,
            "required_kill_status": {},
            "unresolved_blockers": ["production_ast_survivors:1"],
        },
    )
    status = evaluate_private_core_redteam(root=ROOT, workdir=tmp_path / "surv", pass_number=2)
    assert status["passed"] is False
    assert status["recommendation"] != PASS_RECOMMENDATION
    assert int(status["production_ast"]["survivors"]) == 1
    assert status["v15_readiness_blocked_by_survivors"] is True
