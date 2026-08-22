"""P2 migration deployment-ID discovery from deployment list (not deploy --json)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.ci.p2_migration_bootstrap import (
    evaluate_create_command_pass,
    sanitize_create_helper_stderr,
)
from tools.ci.p2_migration_deployment_phase import (
    audit_deploy_output_deployment_id,
    evaluate_activation_baseline,
    evaluate_activation_deployment_discovery,
    evaluate_bootstrap_deployment_discovery,
)
from tools.ci.p2_migration_lifecycle_command import evaluate_activation_local_deploy

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "founder_approved_staging_postgres_p2_migration.yml"
STAGING_ENV = "69d559b6474db8a99d6dd6bf"
SERVICE_ID = "abcdef0123456789abcdef01"
PROJECT_ID = "bbbbbbbbbbbbbbbbbbbbbbbb"
BOOTSTRAP_ID = "6a89a69fa158dec40572a046"
ACTIVATION_ID = "6a89a6cd29f0931a12bfea72"
OTHER_ID = "cccccccccccccccccccccccc"

ZEABUR_DEPLOY_SUCCESS_JSON = json.dumps(
    {
        "status": "success",
        "service_id": SERVICE_ID,
        "project_id": PROJECT_ID,
        "environment_id": STAGING_ENV,
        "message": "Service deployed successfully",
    }
)


def _list_payload(*deployments: tuple[str, str]) -> str:
    items = [{"deployment_id": did, "status": status} for did, status in deployments]
    return json.dumps({"deployments": items})


def test_a_deploy_json_missing_deployment_id_does_not_fail_create():
    command = evaluate_create_command_pass(
        create_exit=0,
        service_id=SERVICE_ID,
        create_output=ZEABUR_DEPLOY_SUCCESS_JSON,
    )
    assert command["ok"] is True
    assert command["P2_MIGRATION_CREATE_COMMAND_PASS"] is True
    audit = audit_deploy_output_deployment_id(ZEABUR_DEPLOY_SUCCESS_JSON)
    assert audit["P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY"] is False
    assert audit["deploy_output_deployment_id_present"] is False


def test_b_fresh_service_deployment_list_zero_waits():
    result = evaluate_bootstrap_deployment_discovery(deployment_list_raw='{"deployments":[]}')
    assert result["ok"] is False
    assert result["wait"] is True
    assert result["P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_DISCOVERY_PASS"] is False


def test_c_fresh_service_deployment_list_exactly_one_bootstrap_pass():
    result = evaluate_bootstrap_deployment_discovery(
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "BUILDING")),
    )
    assert result["ok"] is True
    assert result["P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_DISCOVERY_PASS"] is True
    assert result["bootstrap_deployment_id"] == BOOTSTRAP_ID
    assert result["P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_COUNT"] == 1


def test_d_fresh_service_deployment_list_more_than_one_fail_closed():
    result = evaluate_bootstrap_deployment_discovery(
        deployment_list_raw=_list_payload(
            (BOOTSTRAP_ID, "BUILDING"),
            (OTHER_ID, "BUILDING"),
        ),
    )
    assert result["ok"] is False
    assert result["hard_fail"] is True
    assert result["P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_MULTIPLICITY_FAIL"] is True


def test_e_activation_baseline_contains_bootstrap_only():
    ok = evaluate_activation_baseline(
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "RUNNING")),
        expected_bootstrap_deployment_id=BOOTSTRAP_ID,
    )
    assert ok["ok"] is True
    assert ok["P2_MIGRATION_ACTIVATION_BASELINE_ID_SET_PASS"] is True
    bad = evaluate_activation_baseline(
        deployment_list_raw=_list_payload(
            (BOOTSTRAP_ID, "RUNNING"),
            (OTHER_ID, "CANCELED"),
        ),
        expected_bootstrap_deployment_id=BOOTSTRAP_ID,
    )
    assert bad["ok"] is False


def test_f_activation_after_list_adds_exactly_one_id_pass():
    baseline = frozenset({BOOTSTRAP_ID})
    after = _list_payload((BOOTSTRAP_ID, "RUNNING"), (ACTIVATION_ID, "BUILDING"))
    result = evaluate_activation_deployment_discovery(
        baseline_deployment_ids=baseline,
        deployment_list_raw=after,
    )
    assert result["ok"] is True
    assert result["P2_MIGRATION_ACTIVATION_DEPLOYMENT_DISCOVERY_PASS"] is True
    assert result["activation_deployment_id"] == ACTIVATION_ID
    assert result["P2_MIGRATION_ACTIVATION_NEW_DEPLOYMENT_COUNT"] == 1


def test_g_activation_after_list_adds_more_than_one_fail_closed():
    baseline = frozenset({BOOTSTRAP_ID})
    after = _list_payload(
        (BOOTSTRAP_ID, "CANCELED"),
        (ACTIVATION_ID, "BUILDING"),
        (OTHER_ID, "BUILDING"),
    )
    result = evaluate_activation_deployment_discovery(
        baseline_deployment_ids=baseline,
        deployment_list_raw=after,
    )
    assert result["ok"] is False
    assert result["hard_fail"] is True
    assert result["P2_MIGRATION_ACTIVATION_DEPLOYMENT_MULTIPLICITY_FAIL"] is True


def test_h_array_order_changes_same_correct_ids():
    forward = evaluate_bootstrap_deployment_discovery(
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "BUILDING")),
    )
    reversed_payload = json.dumps(
        {
            "deployments": [
                {"deployment_id": BOOTSTRAP_ID, "status": "BUILDING"},
            ]
        }
    )
    backward = evaluate_bootstrap_deployment_discovery(deployment_list_raw=reversed_payload)
    assert forward["bootstrap_deployment_id"] == backward["bootstrap_deployment_id"]

    baseline = frozenset({BOOTSTRAP_ID})
    order_a = evaluate_activation_deployment_discovery(
        baseline_deployment_ids=baseline,
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "CANCELED"), (ACTIVATION_ID, "BUILDING")),
    )
    order_b = evaluate_activation_deployment_discovery(
        baseline_deployment_ids=baseline,
        deployment_list_raw=_list_payload((ACTIVATION_ID, "BUILDING"), (BOOTSTRAP_ID, "CANCELED")),
    )
    assert order_a["activation_deployment_id"] == ACTIVATION_ID
    assert order_b["activation_deployment_id"] == ACTIVATION_ID


def test_i_old_canceled_bootstrap_cannot_become_activation_id():
    baseline = frozenset({BOOTSTRAP_ID})
    # No new ID — only bootstrap remains.
    result = evaluate_activation_deployment_discovery(
        baseline_deployment_ids=baseline,
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "CANCELED")),
    )
    assert result["ok"] is False
    assert result["wait"] is True
    assert result["activation_deployment_id"] == ""


def test_j_activation_deploy_json_without_deployment_id_passes():
    result = evaluate_activation_local_deploy(
        exit_code=0,
        output=ZEABUR_DEPLOY_SUCCESS_JSON,
        expected_service_id=SERVICE_ID,
        expected_environment_id=STAGING_ENV,
    )
    assert result["ok"] is True
    assert result["P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY"] is False
    assert not result["returned_deployment_id"]


def test_k_helper_stderr_diagnostics_visible_on_controlled_failure():
    stderr = (
        "P2_MIGRATION_CREATE_COMMAND_PASS=false\n"
        "BLOCKER_create_command_failed\n"
        "postgresql://user:secret@host/db\n"
        "ZEABUR_TOKEN=super-secret-token-value\n"
    )
    sanitized = sanitize_create_helper_stderr(stderr)
    assert "P2_MIGRATION_CREATE_COMMAND_PASS=false" in sanitized
    assert "BLOCKER_create_command_failed" in sanitized
    assert "secret" not in sanitized
    assert "ZEABUR_TOKEN" not in sanitized


def test_l_workflow_uses_list_discovery_not_deploy_output():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "P2_MIGRATION_CREATE_HELPER_EXIT=" in source
    assert "P2_MIGRATION_CREATE_DIAGNOSTIC_VISIBLE=true" in source
    assert "P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY=false" in source
    assert "--discover-bootstrap" in source
    assert "--discover-activation" in source
    assert "Discover activation deployment ID from deployment list" in source
    assert "P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_ID=missing" not in source
    assert "grep -E '^P2_MIGRATION_BOOTSTRAP_DEPLOYMENT_ID='" not in source


def test_m_zero_exchange_writes_on_discovery():
    result = evaluate_bootstrap_deployment_discovery(
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "RUNNING")),
    )
    assert result["exchange_write_call_count"] == 0
    assert result["create_order_calls"] == 0


def test_n_activation_zero_new_ids_waits():
    result = evaluate_activation_deployment_discovery(
        baseline_deployment_ids=frozenset({BOOTSTRAP_ID}),
        deployment_list_raw=_list_payload((BOOTSTRAP_ID, "RUNNING")),
    )
    assert result["wait"] is True
    assert result["P2_MIGRATION_ACTIVATION_NEW_DEPLOYMENT_COUNT"] == 0
