"""V11 Security Mutation Red Team — adversarial mutation kill proofs."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_autonomy.security_mutation_v11.adversarial import (  # noqa: E402
    SCENARIO_IDS,
    run_adversarial_scenarios,
)
from backend.nexus_autonomy.security_mutation_v11.campaign import (  # noqa: E402
    evaluate_subject_real,
    kill_mutant,
    run_mutation_campaign,
)
from backend.nexus_autonomy.security_mutation_v11.constants import (  # noqa: E402
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    SUBJECT_IDS,
)
from backend.nexus_autonomy.security_mutation_v11.mutations import iter_mutants  # noqa: E402
from backend.nexus_autonomy.security_mutation_v11.redteam import (  # noqa: E402
    evaluate_security_mutation_redteam,
    run_security_mutation_redteam,
    write_immutable_artifacts,
)
from backend.nexus_autonomy.security_mutation_v11.subjects import SUBJECT_REGISTRY  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    return tmp_path / "mut_work"


def test_all_subjects_registered():
    assert set(SUBJECT_IDS) == set(SUBJECT_REGISTRY)
    assert len(SUBJECT_IDS) == 16


def test_each_subject_has_mutants():
    for sid in SUBJECT_IDS:
        mutants = iter_mutants(sid)
        assert len(mutants) >= 1, sid


def test_real_subjects_pass(workdir: Path):
    for sid in SUBJECT_IDS:
        result = evaluate_subject_real(sid, workdir / sid)
        assert result["passed"], result


def test_mutation_campaign_kills_or_blocks(workdir: Path):
    campaign = run_mutation_campaign(workdir)
    assert campaign["mutation_total"] > 0
    assert campaign["real_subject_pass_count"] == campaign["real_subject_total"]
    # Every outcome must be killed OR explicit unresolved blocker (no silent survivors)
    for o in campaign["mutation_outcomes"]:
        assert o["killed"] or o["unresolved_blocker"] or o["equivalent"], o


def test_weak_path_mutant_killed(workdir: Path):
    outcome = kill_mutant("path_traversal", "path_traversal::allow_all_paths", workdir)
    assert outcome.killed


def test_pickle_mutant_killed(workdir: Path):
    outcome = kill_mutant(
        "unsafe_deserialization",
        "unsafe_deserialization::allow_pickle",
        workdir,
    )
    assert outcome.killed


def test_risk_ceiling_mutant_killed(workdir: Path):
    outcome = kill_mutant("risk_limits", "risk_limits::raise_ceiling_1000x", workdir)
    assert outcome.killed


def test_idempotency_mutant_killed(workdir: Path):
    outcome = kill_mutant("idempotency", "idempotency::clear_intent_owners", workdir)
    assert outcome.killed


def test_ledger_tamper_mutant_killed(workdir: Path):
    outcome = kill_mutant("ledger_hashes", "ledger_hashes::skip_tamper_detect", workdir)
    assert outcome.killed


def test_adversarial_scenarios_pass(workdir: Path):
    results = run_adversarial_scenarios(workdir)
    assert len(results) == len(SCENARIO_IDS)
    failed = [r.scenario_id for r in results if not r.passed]
    assert failed == [], [(r.scenario_id, r.detail) for r in results if not r.passed]


def test_evaluate_counters_zero(workdir: Path):
    status = evaluate_security_mutation_redteam(root=ROOT, workdir=workdir)
    assert status["exchange_write_attempt_count"] == 0
    assert status["secret_leak_count"] == 0
    assert status["mainnet_client_created_count"] == 0
    assert status["demo_order_count"] == 0
    # Pass 1 may still have unresolved survivors recorded as blockers — counters must stay zero
    assert status["findings"]["items"] is not None


def test_no_unresolved_survivors_after_kill_suite(workdir: Path):
    status = evaluate_security_mutation_redteam(root=ROOT, workdir=workdir)
    assert status["mutation_unresolved_blocker_count"] == 0, status.get("unresolved_blockers")
    assert status["recommendation"] == PASS_RECOMMENDATION
    assert status["passed"] is True
    assert status["critical_findings"] == []


def test_immutable_artifacts_written(tmp_path: Path):
    status = evaluate_security_mutation_redteam(root=ROOT, workdir=tmp_path / "w")
    paths = write_immutable_artifacts(root=ROOT, status=status)
    assert paths["status"].is_file()
    loaded = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert loaded["exchange_write_attempt_count"] == 0
    assert loaded["secret_leak_count"] == 0
    assert loaded["mainnet_client_created_count"] == 0
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert "critical_findings" in summary


def test_run_end_to_end():
    status = run_security_mutation_redteam(write_artifact=True, root=ROOT)
    assert status["exchange_write_attempt_count"] == 0
    assert status["secret_leak_count"] == 0
    assert status["mainnet_client_created_count"] == 0
    art = (
        ROOT
        / "artifacts"
        / "readiness"
        / "immutable"
        / "v11_security_mutation_redteam"
        / "security_mutation_redteam_status.json"
    )
    assert art.is_file()


def test_owned_paths_declared():
    assert any("security_mutation_v11" in p for p in OWNED_PATHS)
    assert any("v11_security_mutation_redteam" in p for p in OWNED_PATHS)
