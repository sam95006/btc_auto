"""NEXUS Workstream-B api-staging release verification repair.

Fixtures mirror the OBSERVED live `zeabur deployment list --json` shape
(2026-09-03): a top-level JSON array of deployment records with fields
ID / status / createdAt / serviceID / environmentID / commitSHA.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/founder_approved_api_staging_deploy.yml")
VERIFIER = Path("tools/ci/verify_api_staging_deployment.py")
STATUS = Path("tools/ci/zeabur_deployment_status.py")
RESOLVE = Path("tools/ci/zeabur_deployment_resolve.py")

SERVICE_ID = "6a7ee0a82b4272705cd1c9c8"
ENV_ID = "69d559b6474db8a99d6dd6bf"
OTHER_SERVICE = "ffffffffffffffffffffffff"
DEP1 = "a1a1a1a1a1a1a1a1a1a1a1a1"
DEP2 = "b2b2b2b2b2b2b2b2b2b2b2b2"
DEP3 = "c3c3c3c3c3c3c3c3c3c3c3c3"
# For the "not lexicographic id order" proof: lex-smallest id is the OLDER one.
DEP_OLD = "0a0a0a0a0a0a0a0a0a0a0a0a"
DEP_NEW = "f9f9f9f9f9f9f9f9f9f9f9f9"


def _wf() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _verify_block(source: str) -> str:
    marker = "- name: Read-only post-deploy verification"
    start = source.index(marker)
    nxt = source.find("\n      - name:", start + len(marker))
    return source[start: nxt if nxt != -1 else len(source)]


def _run(script: Path, *args: str) -> str:
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True).stdout.strip()


def _write(tmp_path, name, text) -> str:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _dep(_id, status, created="2026-09-02T00:00:00.000Z", service=SERVICE_ID, env=ENV_ID):
    return {"ID": _id, "status": status, "createdAt": created, "serviceID": service,
            "environmentID": env, "commitSHA": "0" * 40, "ref": "main"}


def _list(*records):   # top-level array — the observed live shape
    return json.dumps(list(records))


# ---- verifier origin ---------------------------------------------------------
def test_verifier_uses_configurable_personal_origin_not_retired():
    v = VERIFIER.read_text(encoding="utf-8")
    assert "nexus-member-preview-v18-2-1" not in v
    assert "PERSONAL_STAGING_ORIGIN" in v
    assert "raise SystemExit(2)" in v
    assert "PERSONAL_STAGING_ORIGIN: https://nexus-personal-staging.zeabur.app" in _wf()
    assert "X-Nexus-Session" in v and "X-Nexus-CSRF" in v
    assert '"x-nexus-session" in cors_allow_headers.lower()' in v


# ---- activation gate ---------------------------------------------------------
def test_verification_gated_on_new_deployment_activation():
    block = _verify_block(_wf())
    assert "NEW_DEPLOYMENT_ID=" in block and "PREVIOUS_DEPLOYMENT_ID=" in block
    assert "python tools/ci/zeabur_deployment_status.py" in block
    assert 'dep_status" = "RUNNING"' in block
    assert block.index("NEW_DEPLOYMENT_ACTIVATED=yes") < block.index(
        "python tools/ci/verify_api_staging_deployment.py")


def test_failed_deployment_fails_immediately():
    block = _verify_block(_wf())
    assert 'dep_status" = "FAILED"' in block and "NEW_DEPLOYMENT_FAILED=yes" in block
    assert block.index("NEW_DEPLOYMENT_FAILED=yes") < block.index("NEW_DEPLOYMENT_ACTIVATED=yes")


def test_activation_timeout_fails_closed():
    block = _verify_block(_wf())
    assert "DEPLOYMENT_ACTIVATION_TIMEOUT=yes" in block
    assert "LIVE_VERIFICATION_TIMEOUT=yes" in block
    assert "POST_DEPLOY_VERIFY_FAIL_CLOSED=yes" in block
    assert "exit 0" not in block
    assert "for attempt in $(seq 1 40)" in block


def test_workstream_b_routes_in_acceptance():
    v = VERIFIER.read_text(encoding="utf-8")
    for t in ("/api/v1/personal/catalog", "personal_catalog_status", "_catalog_contract_ok",
              "/api/v1/personal/market-state", "/api/v1/personal/subscription",
              "catalog_status != 200", "market_state_status == 404", "subscription_status == 404",
              "STARTER_TRIAL_30D", "annual_discount_pct", '"free"', '"starter"', '"pro"', '"advanced"', '"enterprise"'):
        assert t in v
    assert "/api/v1/personal/catalog" in _verify_block(_wf())


def test_no_automatic_legacy_fallback():
    assert "LEGACY_FULL_DEPLOY" not in _verify_block(_wf())
    assert "if: needs.validate.outputs.mode != 'SAFE_CATCHUP_ONLY'" in _wf()


def test_verification_does_not_mutate_environment():
    block = _verify_block(_wf())
    for m in ("zeabur variable update", "zeabur variable create", "zeabur variable delete",
              "curl -X POST", "curl -X PUT", "curl -X PATCH", "curl -X DELETE", "/register", "/login"):
        assert m not in block, m


def test_release_repair_tests_wired_into_deploy_ci():
    wf = _wf()
    for f in ("tests/test_api_staging_release_repair.py", "tests/test_v18_3_4_product_http_api.py",
              "tests/test_api_staging_safe_catchup_workflow.py"):
        assert f in wf


# ---- structural resolver (real live schema) ----------------------------------
def test_resolver_extracts_only_deployment_id_not_service_or_env(tmp_path):
    f = _write(tmp_path, "d.json", _list(_dep(DEP1, "RUNNING")))
    out = _run(RESOLVE, "records", f, "--service", SERVICE_ID, "--env", ENV_ID).split()
    assert out == [DEP1]
    assert SERVICE_ID not in out and ENV_ID not in out


def test_resolver_new_via_record_diff(tmp_path):
    before = _write(tmp_path, "b.json", _list(_dep(DEP1, "RUNNING")))
    after = _write(tmp_path, "a.json", _list(_dep(DEP1, "RUNNING"), _dep(DEP2, "BUILDING")))
    assert _run(RESOLVE, "new", before, after, "--service", SERVICE_ID, "--env", ENV_ID) == DEP2


def test_resolver_zero_new_is_none(tmp_path):
    same = _write(tmp_path, "s.json", _list(_dep(DEP1, "RUNNING")))
    assert _run(RESOLVE, "new", same, same) == "NONE"


def test_resolver_more_than_one_new_is_ambiguous(tmp_path):
    before = _write(tmp_path, "b.json", _list(_dep(DEP1, "RUNNING")))
    after = _write(tmp_path, "a.json", _list(_dep(DEP1, "RUNNING"), _dep(DEP2, "BUILDING"), _dep(DEP3, "BUILDING")))
    out = _run(RESOLVE, "new", before, after)
    assert out.startswith("AMBIGUOUS:") and DEP2 in out and DEP3 in out


def test_resolver_malformed_fails_closed(tmp_path):
    good = _write(tmp_path, "b.json", _list(_dep(DEP1, "RUNNING")))
    bad = _write(tmp_path, "a.json", "{ not json ")
    assert _run(RESOLVE, "new", good, bad) == "MALFORMED"
    assert _run(RESOLVE, "records", bad) == "MALFORMED"


def test_resolver_unrecognized_container_fails_closed(tmp_path):
    # A top-level array of NON-deployment dicts (no ID/status) is not a container.
    f = _write(tmp_path, "x.json", json.dumps([{"name": "svc", "serviceID": SERVICE_ID}]))
    assert _run(RESOLVE, "records", f) == "MALFORMED"


def test_resolver_rejects_wrong_service(tmp_path):
    before = _write(tmp_path, "b.json", _list(_dep(DEP1, "RUNNING")))
    after = _write(tmp_path, "a.json", _list(_dep(DEP1, "RUNNING"), _dep(DEP2, "RUNNING", service=OTHER_SERVICE)))
    assert _run(RESOLVE, "new", before, after, "--service", SERVICE_ID) == "NONE"


def test_resolver_supports_wrapped_deployments_container(tmp_path):
    f = _write(tmp_path, "w.json", json.dumps({"deployments": [_dep(DEP1, "RUNNING")]}))
    assert _run(RESOLVE, "records", f) == DEP1


# ---- previous deployment selection by timestamp (A3) -------------------------
def test_previous_deployment_selected_by_created_timestamp_not_id_order(tmp_path):
    # DEP_OLD is lexicographically SMALLEST but OLDER; DEP_NEW is lex-largest but NEWER.
    f = _write(tmp_path, "p.json", _list(
        _dep(DEP_OLD, "RUNNING", created="2026-09-01T00:00:00.000Z"),
        _dep(DEP_NEW, "RUNNING", created="2026-09-02T00:00:00.000Z"),
    ))
    latest = _run(RESOLVE, "latest", f, "--service", SERVICE_ID, "--env", ENV_ID)
    assert latest == DEP_NEW                       # newest by createdAt
    assert latest != DEP_OLD                       # NOT the lexicographically smallest id
    assert latest != sorted([DEP_OLD, DEP_NEW])[0]  # NOT sorted-id head


def test_previous_unavailable_when_no_timestamp(tmp_path):
    rec = {"ID": DEP1, "status": "RUNNING", "serviceID": SERVICE_ID}  # no createdAt
    f = _write(tmp_path, "n.json", _list(rec))
    assert _run(RESOLVE, "latest", f) == "PREVIOUS_DEPLOYMENT_ID_UNAVAILABLE"


# ---- status parser -----------------------------------------------------------
def test_status_running_failed_unknown(tmp_path):
    running = _write(tmp_path, "r.json", _list(_dep(DEP1, "RUNNING")))
    failed = _write(tmp_path, "f.json", _list(_dep(DEP1, "FAILED")))
    weird = _write(tmp_path, "w.json", _list(_dep(DEP1, "SOMETHING_ELSE")))
    assert _run(STATUS, running, DEP1) == "RUNNING"
    assert _run(STATUS, failed, DEP1) == "FAILED"
    assert _run(STATUS, weird, DEP1) == "UNKNOWN"
    assert _run(STATUS, running, DEP2) == "UNKNOWN"     # id not present


# ---- workflow wiring ---------------------------------------------------------
def test_workflow_resolves_exact_id_and_previous_by_timestamp():
    wf = _wf()
    block = _verify_block(wf)
    assert "python tools/ci/zeabur_deployment_resolve.py new /tmp/pre-deployments.json" in block
    assert '--service "$SERVICE_ID" --env "$ZEABUR_ENV_ID"' in block
    assert "DEPLOYMENT_LIST_MALFORMED=yes" in block
    assert 'resolved" != "yes"' in block
    assert "NEW_DEPLOYMENT_ID_DID_NOT_ADVANCE=yes" in block
    assert "EXACT_NEW_DEPLOYMENT_ID_RESOLVED=yes" in block
    # previous by real timestamp, not id order
    assert "zeabur_deployment_resolve.py latest /tmp/pre-deployments.json" in wf
    assert "PREVIOUS_DEPLOYMENT_ID_SELECTED_BY=createdAt_timestamp" in wf


def test_workflow_requires_running_and_catalog_marker():
    # Neither catalog 200 alone nor RUNNING alone may pass — BOTH are required.
    block = _verify_block(_wf())
    assert '[ "$dep_status" = "RUNNING" ] && [ "$catalog_http" = "200" ]' in block


def test_workflow_targets_exact_api_staging_service():
    wf = _wf()
    assert "API_STAGING_SERVICE_ID: 6a7ee0a82b4272705cd1c9c8" in wf
    assert 'zeabur deployment list --service-id "$SERVICE_ID" --env-id "$ZEABUR_ENV_ID"' in wf


def test_resolver_and_status_reuse_proven_field_helpers():
    r = RESOLVE.read_text(encoding="utf-8")
    s = STATUS.read_text(encoding="utf-8")
    assert "from zeabur_readonly_diagnostic import" in r and "_dep_id" in r and "_dep_created" in r
    assert "_records_container" in s and "_dep_status" in s
    # The strict release resolver does NOT use the loose "largest list of dicts".
    assert "_deployment_records" not in r
