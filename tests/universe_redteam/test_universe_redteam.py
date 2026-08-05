"""V14-I Universe Lineage Red Team — fail-closed adversarial proofs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_universe_redteam.constants import (  # noqa: E402
    ATTACK_SCENARIO_IDS,
    EVIDENCE_CLASS,
    FIXTURE_IDS,
    HARD_BANS,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
)
from backend.nexus_universe_redteam.fixtures import run_all_fixtures  # noqa: E402
from backend.nexus_universe_redteam.guards import (  # noqa: E402
    detect_rename_leakage,
    detect_survivorship_bias,
    require_attack_disposition,
)
from backend.nexus_universe_redteam.pass2 import run_pass2_review  # noqa: E402
from backend.nexus_universe_redteam.redteam import (  # noqa: E402
    evaluate_universe_redteam,
    run_universe_redteam,
    write_immutable_artifacts,
)
from backend.nexus_universe_redteam.scenarios import (  # noqa: E402
    SCENARIO_FNS,
    ScenarioResult,
    run_all_scenarios,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    return tmp_path / "v14i_work"


def test_required_scenarios_and_hard_bans():
    required = {
        "survivorship_bias",
        "listing_date_leakage",
        "delisting_leakage",
        "rename_leakage",
        "contract_spec_changes",
        "today_universe_substitution",
        "future_liquidity_leakage",
        "future_funding_availability",
        "mapping_drift",
        "min_notional_drift",
    }
    assert set(ATTACK_SCENARIO_IDS) == required
    assert len(ATTACK_SCENARIO_IDS) == 10
    assert "no_auto_integration_into_PR27" in HARD_BANS
    assert "no_today_universe_for_past" in HARD_BANS
    assert "no_silent_rename_without_lineage" in HARD_BANS
    assert any("nexus_universe_redteam" in p for p in OWNED_PATHS)
    assert set(FIXTURE_IDS) == {
        "property_fuzz_universe_checksums",
        "schema_mutation_lineage",
        "era_comparison_stability",
        "adversarial_suite_reuse",
    }
    assert EVIDENCE_CLASS == "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"


@pytest.mark.parametrize("scenario_id", list(ATTACK_SCENARIO_IDS))
def test_each_attack_scenario(scenario_id: str, workdir: Path):
    r = SCENARIO_FNS[scenario_id](workdir / scenario_id)
    assert isinstance(r, ScenarioResult)
    assert r.passed and r.fail_closed and r.attack_blocked
    assert r.platform_blocked is False
    disp = require_attack_disposition(
        attack_blocked_by_code=r.attack_blocked,
        critical_blocker_code=r.critical_blocker_code,
    )
    assert disp["ok"]


def test_run_all_scenarios(workdir: Path):
    results = run_all_scenarios(workdir)
    assert len(results) == len(ATTACK_SCENARIO_IDS)
    assert all(r.passed and not r.platform_blocked and r.attack_blocked for r in results)


def test_fixtures(workdir: Path):
    fixtures = run_all_fixtures(workdir)
    assert len(fixtures) == len(FIXTURE_IDS)
    assert all(f.get("passed") for f in fixtures)
    assert all(f.get("evidence_class") == EVIDENCE_CLASS for f in fixtures)


def test_guards_negative():
    surv = detect_survivorship_bias(
        claimed_symbols=["BTCUSDT"],
        pit_eligible_symbols=["BTCUSDT", "GHOSTUSDT"],
        today_survivor_symbols=["BTCUSDT"],
    )
    assert not surv["ok"]
    rename = detect_rename_leakage(
        old_symbol="A",
        new_symbol="B",
        rename_effective_ms=100,
        as_of_ms=50,
        rename_lineage_id=None,
        claimed_identity="B",
    )
    assert not rename["ok"]


def test_pass1_evaluate(workdir: Path):
    status = evaluate_universe_redteam(root=ROOT, workdir=workdir, pass_number=1)
    assert status["scenario_pass_count"] == len(ATTACK_SCENARIO_IDS)
    assert status["attack_blocked_count"] == len(ATTACK_SCENARIO_IDS)
    assert status["fixture_pass_count"] == len(FIXTURE_IDS)
    assert status["exchange_write_attempt_count"] == 0
    assert status["auto_integration"] is False
    assert status["recommendation"] == PASS_RECOMMENDATION
    assert status["passed"] is True


def test_pass2_review_and_full_run(tmp_path: Path):
    work = tmp_path / "full"
    status = evaluate_universe_redteam(root=ROOT, workdir=work, pass_number=2)
    assert status["pass_number"] == 2
    assert status["passed"] is True
    assert status["recommendation"] == PASS_RECOMMENDATION
    assert status["pass2"]["passed"] is True
    assert int(status["findings"]["unresolved_critical_count"]) == 0

    # Pass2 alone on a healthy body
    p2 = run_pass2_review(status)
    assert p2["passed"] is True


def test_write_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Write into repo immutable dir (owned path) via evaluate then write
    status = evaluate_universe_redteam(root=ROOT, workdir=tmp_path / "art", pass_number=2)
    paths = write_immutable_artifacts(root=ROOT, status=status)
    assert paths["status"].exists()
    assert paths["summary"].exists()
    body = paths["status"].read_text(encoding="utf-8")
    assert "survivorship_bias" in body
    assert "NEXUS_V14_UNIVERSE_LINEAGE_REDTEAM" in body


def test_run_universe_redteam_no_runtime(tmp_path: Path):
    status = run_universe_redteam(
        write_artifact=True,
        write_runtime=True,
        root=ROOT,
        pass_number=2,
        runtime_path=tmp_path / "v14_i_status.json",
    )
    assert status["passed"] is True
    assert (tmp_path / "v14_i_status.json").exists()
