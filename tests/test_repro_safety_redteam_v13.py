"""V13-H Reproducibility and Safety Red Team — fail-closed adversarial proofs."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_autonomy.repro_safety_redteam_v13.constants import (  # noqa: E402
    ATTACK_SCENARIO_IDS,
    FIXTURE_IDS,
    HARD_BANS,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
)
from backend.nexus_autonomy.repro_safety_redteam_v13.fixtures import (  # noqa: E402
    checkpoint_mutation_fixture,
    property_fuzz_evidence_hashes,
    run_all_fixtures,
    schema_mutation_envelope,
)
from backend.nexus_autonomy.repro_safety_redteam_v13.redteam import (  # noqa: E402
    evaluate_repro_safety_redteam,
    run_repro_safety_redteam,
    write_immutable_artifacts,
)
from backend.nexus_autonomy.repro_safety_redteam_v13.scenarios import (  # noqa: E402
    ScenarioResult,
    run_all_scenarios,
    run_ledger_fork_fixture,
    scenario_checkpoint_version_tamper,
    scenario_cost_version_divergence,
    scenario_decision_evidence_hash_mismatch,
    scenario_dynamic_universe_reconstruction_drift,
    scenario_exchange_write_trap,
    scenario_founder_auth_spoof,
    scenario_future_data_exclusion_bypass,
    scenario_mainnet_profile_separation,
    scenario_oos_non_consumption_violation,
    scenario_pit_lineage_tamper,
    scenario_provider_model_provenance_spoof,
    scenario_risk_version_divergence,
    scenario_secret_redaction_leak,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    return tmp_path / "v13h_work"


def test_required_scenarios_and_hard_bans():
    required = {
        "pit_lineage_tamper",
        "decision_evidence_hash_mismatch",
        "cost_version_divergence",
        "risk_version_divergence",
        "checkpoint_version_tamper",
        "provider_model_provenance_spoof",
        "dynamic_universe_reconstruction_drift",
        "future_data_exclusion_bypass",
        "oos_non_consumption_violation",
        "founder_auth_spoof",
        "exchange_write_trap",
        "mainnet_profile_separation",
        "secret_redaction_leak",
    }
    assert set(ATTACK_SCENARIO_IDS) == required
    assert len(ATTACK_SCENARIO_IDS) == 13
    assert "no_platform_blocked_mutation_as_pass" in HARD_BANS
    assert "no_auto_integration_into_PR27" in HARD_BANS
    assert any("repro_safety_redteam_v13" in p for p in OWNED_PATHS)
    assert set(FIXTURE_IDS) == {
        "property_fuzz_evidence_hashes",
        "schema_mutation_envelope",
        "checkpoint_mutation",
        "ledger_fork",
    }


@pytest.mark.parametrize(
    "fn",
    [
        scenario_pit_lineage_tamper,
        scenario_decision_evidence_hash_mismatch,
        scenario_cost_version_divergence,
        scenario_risk_version_divergence,
        scenario_checkpoint_version_tamper,
        scenario_provider_model_provenance_spoof,
        scenario_dynamic_universe_reconstruction_drift,
        scenario_future_data_exclusion_bypass,
        scenario_oos_non_consumption_violation,
        scenario_founder_auth_spoof,
        scenario_exchange_write_trap,
        scenario_mainnet_profile_separation,
        scenario_secret_redaction_leak,
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
    assert property_fuzz_evidence_hashes(seed=7, rounds=32)["passed"] is True
    assert schema_mutation_envelope(root=ROOT)["passed"] is True
    assert checkpoint_mutation_fixture(root=ROOT)["passed"] is True
    assert run_ledger_fork_fixture(workdir)["passed"] is True
    fxs = run_all_fixtures(workdir, root=ROOT)
    assert len(fxs) == len(FIXTURE_IDS)
    assert all(f["passed"] for f in fxs)


def test_evaluate_and_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "backend.nexus_autonomy.repro_safety_redteam_v13.redteam.write_runtime_status",
        lambda *a, **k: {},
    )
    status = evaluate_repro_safety_redteam(root=ROOT, workdir=tmp_path / "eval", pass_number=1)
    assert status["scenario_pass_count"] == status["scenario_total_count"] == 13
    assert status["fixture_pass_count"] == status["fixture_total_count"] == 4
    assert status["platform_blocked_pass_count"] == 0
    assert status["exchange_write_attempt_count"] == 0
    assert status["mainnet_client_created_count"] == 0
    assert status["demo_order_count"] == 0
    assert status["auto_integration"] is False
    assert status["production_ast"]["platform_blocked_pass_count"] == 0
    assert status["production_ast"]["survivors"] == 0
    assert status["passed"] is True
    assert status["recommendation"] == PASS_RECOMMENDATION

    art_root = tmp_path / "repo"
    (art_root / "artifacts" / "readiness" / "immutable").mkdir(parents=True)
    paths = write_immutable_artifacts(root=art_root, status=status)
    assert paths["status"].exists()
    loaded = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert loaded["passed"] is True
    assert loaded["attack_blocked_count"] == 13


def test_run_repro_safety_redteam_no_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "backend.nexus_autonomy.repro_safety_redteam_v13.redteam.write_runtime_status",
        lambda *a, **k: {},
    )
    art_root = tmp_path / "repo2"
    status = run_repro_safety_redteam(
        root=art_root,
        write_artifact=True,
        write_runtime=False,
        commit="deadbeef",
        pass_number=2,
    )
    assert status["commit"] == "deadbeef"
    assert status["pass_number"] == 2
    assert (art_root / "artifacts" / "readiness" / "immutable" / "v13_repro_safety_redteam").exists()


# ---------------------------------------------------------------------------
# PASS 2 — adversarial / negative tests (false-PASS hunters)
# ---------------------------------------------------------------------------


def test_pass2_platform_blocked_never_counts_as_pass():
    """Hard ban: platform-blocked mutation must not be recommendation PASS."""
    from backend.nexus_autonomy.repro_safety_redteam_v13.redteam import _critical_findings

    fake = [
        ScenarioResult(
            scenario_id="exchange_write_trap",
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
        [{"fixture_id": "ledger_fork", "passed": True}],
        {"passed": True, "unresolved_blockers": []},
    )
    assert any("platform_blocked_not_pass" in f["code"] for f in findings)


def test_pass2_cost_version_silent_accept_is_hole(workdir: Path):
    """Negative: if cost pin were ignored, scenario must fail (detect hole)."""
    r = scenario_cost_version_divergence(workdir)
    assert r.passed
    assert "cost_version" in r.detail or r.attack_blocked


def test_pass2_future_data_nested_key_must_trip(workdir: Path):
    r = scenario_future_data_exclusion_bypass(workdir)
    assert r.evidence["dirty"]["violation_count"] >= 1
    assert r.evidence["clean"]["future_data_excluded"] is True


def test_pass2_oos_overlap_must_fail_proof(workdir: Path):
    r = scenario_oos_non_consumption_violation(workdir)
    assert r.evidence["dirty"]["proven"] is False
    assert r.evidence["clean"]["proven"] is True


def test_pass2_universe_excludes_future_launch(workdir: Path):
    r = scenario_dynamic_universe_reconstruction_drift(workdir)
    assert "FUTUREUSDT" not in r.evidence["members"]
    assert "DEADUSDT" not in r.evidence["members"]


def test_pass2_secret_value_never_in_public_blob(workdir: Path):
    r = scenario_secret_redaction_leak(workdir)
    assert r.evidence["not_echoed"] is True
    assert r.evidence["detected"] is True


def test_pass2_no_fixture_only_pass_without_scenarios(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fixtures alone must not yield PASS if scenarios are empty."""
    monkeypatch.setattr(
        "backend.nexus_autonomy.repro_safety_redteam_v13.redteam.run_all_scenarios",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "backend.nexus_autonomy.repro_safety_redteam_v13.redteam.write_runtime_status",
        lambda *a, **k: {},
    )
    status = evaluate_repro_safety_redteam(root=ROOT, workdir=tmp_path / "empty", pass_number=2)
    assert status["passed"] is False
    assert status["recommendation"] != PASS_RECOMMENDATION
