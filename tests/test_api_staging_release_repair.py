"""NEXUS Workstream-B api-staging release verification repair.

Proves the release tooling: (a) verifies the CURRENT Personal staging origin
(configurable, not the retired Member Preview host), (b) resolves the EXACT new
Zeabur deployment id from deployment RECORDS (never a global 24-hex scrape) and
gates on that exact deployment reaching RUNNING, and (c) proves Workstream-B
routes are actually serving.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/founder_approved_api_staging_deploy.yml")
VERIFIER = Path("tools/ci/verify_api_staging_deployment.py")
STATUS = Path("tools/ci/zeabur_deployment_status.py")
RESOLVE = Path("tools/ci/zeabur_deployment_resolve.py")

SERVICE_ID = "6a7ee0a82b4272705cd1c9c8"
ENV_ID = "69d559b6474db8a99d6dd6bf"
DEP1 = "a1a1a1a1a1a1a1a1a1a1a1a1"
DEP2 = "b2b2b2b2b2b2b2b2b2b2b2b2"
DEP3 = "c3c3c3c3c3c3c3c3c3c3c3c3"
OTHER_SERVICE = "ffffffffffffffffffffffff"


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


def _dep(_id, status, service=SERVICE_ID, env=ENV_ID):
    return {"_id": _id, "status": status, "serviceID": service, "environmentID": env}


def _list_json(*records):
    import json
    return json.dumps({"deployments": list(records)})


# ---- 1 + 2: verifier uses the configurable canonical Personal origin ----------
def test_verifier_uses_configurable_personal_origin_not_retired():
    v = VERIFIER.read_text(encoding="utf-8")
    assert "nexus-member-preview-v18-2-1" not in v
    assert "PERSONAL_STAGING_ORIGIN" in v
    assert "raise SystemExit(2)" in v            # fail closed when absent/invalid
    assert "PERSONAL_STAGING_ORIGIN: https://nexus-personal-staging.zeabur.app" in _wf()
    assert "X-Nexus-Session" in v and "X-Nexus-CSRF" in v
    assert '"x-nexus-session" in cors_allow_headers.lower()' in v


# ---- 3 + 4: gate on exact deployment activation before HTTP verify ------------
def test_verification_gated_on_new_deployment_activation():
    block = _verify_block(_wf())
    assert "NEW_DEPLOYMENT_ID=" in block
    assert "PREVIOUS_DEPLOYMENT_ID=" in block
    assert "NEW_DEPLOYMENT_ID_DID_NOT_ADVANCE=yes" in block
    assert "python tools/ci/zeabur_deployment_status.py" in block
    assert 'dep_status" = "RUNNING"' in block
    assert block.index("NEW_DEPLOYMENT_ACTIVATED=yes") < block.index(
        "python tools/ci/verify_api_staging_deployment.py"
    )


def test_failed_deployment_fails_immediately():
    block = _verify_block(_wf())
    assert 'dep_status" = "FAILED"' in block
    assert "NEW_DEPLOYMENT_FAILED=yes" in block
    assert block.index("NEW_DEPLOYMENT_FAILED=yes") < block.index("NEW_DEPLOYMENT_ACTIVATED=yes")


def test_activation_timeout_fails_closed():
    block = _verify_block(_wf())
    assert "DEPLOYMENT_ACTIVATION_TIMEOUT=yes" in block
    assert "LIVE_VERIFICATION_TIMEOUT=yes" in block
    assert "POST_DEPLOY_VERIFY_FAIL_CLOSED=yes" in block
    assert "exit 0" not in block
    assert "for attempt in $(seq 1 40)" in block


# ---- 7 + 8: Workstream-B routes in acceptance --------------------------------
def test_workstream_b_routes_in_acceptance():
    v = VERIFIER.read_text(encoding="utf-8")
    assert "/api/v1/personal/catalog" in v
    assert "personal_catalog_status" in v
    assert "_catalog_contract_ok" in v
    assert "/api/v1/personal/market-state" in v
    assert "/api/v1/personal/subscription" in v
    assert "catalog_status != 200" in v
    assert "market_state_status == 404" in v
    assert "subscription_status == 404" in v
    for token in ("STARTER_TRIAL_30D", "annual_discount_pct", '"free"', '"starter"', '"pro"', '"advanced"', '"enterprise"'):
        assert token in v
    assert "/api/v1/personal/catalog" in _verify_block(_wf())


# ---- 9: no automatic LEGACY fallback -----------------------------------------
def test_no_automatic_legacy_fallback():
    block = _verify_block(_wf())
    assert "LEGACY_FULL_DEPLOY" not in block
    assert "if: needs.validate.outputs.mode != 'SAFE_CATCHUP_ONLY'" in _wf()


# ---- 10: SAFE_CATCHUP verification performs no env mutation -------------------
def test_verification_does_not_mutate_environment():
    block = _verify_block(_wf())
    for mutation in ("zeabur variable update", "zeabur variable create", "zeabur variable delete",
                     "curl -X POST", "curl -X PUT", "curl -X PATCH", "curl -X DELETE",
                     "/register", "/login"):
        assert mutation not in block, mutation


# ---- CI wiring ---------------------------------------------------------------
def test_release_repair_tests_wired_into_deploy_ci():
    wf = _wf()
    assert "tests/test_api_staging_release_repair.py" in wf
    assert "tests/test_v18_3_4_product_http_api.py" in wf
    assert "tests/test_api_staging_safe_catchup_workflow.py" in wf


# ---- Structural resolver (record-based, NOT global hex scrape) ----------------
def test_resolver_extracts_only_deployment_ids_not_service_or_env(tmp_path):
    # Records carry serviceID/environmentID fields, but only the deployment id
    # (_id) may be extracted — never the service/env ids.
    f = _write(tmp_path, "d.json", _list_json(_dep(DEP1, "RUNNING")))
    out = _run(RESOLVE, "records", f, "--service", SERVICE_ID, "--env", ENV_ID).split()
    assert out == [DEP1]
    assert SERVICE_ID not in out and ENV_ID not in out


def test_resolver_new_via_record_diff(tmp_path):
    before = _write(tmp_path, "b.json", _list_json(_dep(DEP1, "RUNNING")))
    after = _write(tmp_path, "a.json", _list_json(_dep(DEP1, "RUNNING"), _dep(DEP2, "BUILDING")))
    assert _run(RESOLVE, "new", before, after, "--service", SERVICE_ID, "--env", ENV_ID) == DEP2


def test_resolver_same_snapshot_yields_none(tmp_path):
    same = _write(tmp_path, "s.json", _list_json(_dep(DEP1, "RUNNING")))
    assert _run(RESOLVE, "new", same, same) == "NONE"


def test_resolver_ambiguous_multiple_new_rejected(tmp_path):
    before = _write(tmp_path, "b.json", _list_json(_dep(DEP1, "RUNNING")))
    after = _write(tmp_path, "a.json", _list_json(_dep(DEP1, "RUNNING"), _dep(DEP2, "BUILDING"), _dep(DEP3, "BUILDING")))
    out = _run(RESOLVE, "new", before, after)
    assert out.startswith("AMBIGUOUS:") and DEP2 in out and DEP3 in out


def test_resolver_malformed_json_fails_closed(tmp_path):
    good = _write(tmp_path, "b.json", _list_json(_dep(DEP1, "RUNNING")))
    bad = _write(tmp_path, "a.json", "{ this is : not json ")
    assert _run(RESOLVE, "new", good, bad) == "MALFORMED"
    assert _run(RESOLVE, "records", bad) == "MALFORMED"


def test_resolver_rejects_wrong_service(tmp_path):
    # A new record belonging to another service must not be accepted as our new id.
    before = _write(tmp_path, "b.json", _list_json(_dep(DEP1, "RUNNING")))
    after = _write(tmp_path, "a.json", _list_json(_dep(DEP1, "RUNNING"), _dep(DEP2, "RUNNING", service=OTHER_SERVICE)))
    assert _run(RESOLVE, "new", before, after, "--service", SERVICE_ID) == "NONE"


# ---- Status parser (same exact record) ---------------------------------------
def test_status_running_failed_unknown(tmp_path):
    running = _write(tmp_path, "r.json", _list_json(_dep(DEP1, "RUNNING")))
    failed = _write(tmp_path, "f.json", _list_json(_dep(DEP1, "FAILED")))
    weird = _write(tmp_path, "w.json", _list_json(_dep(DEP1, "SOMETHING_WEIRD")))
    assert _run(STATUS, running, DEP1) == "RUNNING"
    assert _run(STATUS, failed, DEP1) == "FAILED"
    assert _run(STATUS, weird, DEP1) == "UNKNOWN"          # unrecognised terminal -> UNKNOWN
    assert _run(STATUS, running, DEP2) == "UNKNOWN"        # id not present -> UNKNOWN


# ---- Workflow wiring of the structural resolver ------------------------------
def test_workflow_resolves_exact_id_via_records_and_fails_closed():
    block = _verify_block(_wf())
    assert "python tools/ci/zeabur_deployment_resolve.py new /tmp/pre-deployments.json" in block
    assert '--service "$SERVICE_ID" --env "$ZEABUR_ENV_ID"' in block
    assert "DEPLOYMENT_LIST_MALFORMED=yes" in block        # malformed -> fail closed
    assert 'resolved" != "yes"' in block                   # unresolved -> fail closed
    assert "NEW_DEPLOYMENT_ID_DID_NOT_ADVANCE=yes" in block
    assert "EXACT_NEW_DEPLOYMENT_ID_RESOLVED=yes" in block


def test_workflow_requires_running_and_catalog_marker():
    # catalog 200 alone must NOT count as activation — deployment RUNNING is required.
    block = _verify_block(_wf())
    assert '[ "$dep_status" = "RUNNING" ] && [ "$catalog_http" = "200" ]' in block


def test_workflow_targets_exact_api_staging_service():
    wf = _wf()
    assert "API_STAGING_SERVICE_ID: 6a7ee0a82b4272705cd1c9c8" in wf
    assert 'zeabur deployment list --service-id "$SERVICE_ID" --env-id "$ZEABUR_ENV_ID"' in wf


def test_resolver_and_status_reuse_proven_parser():
    # Both reuse the repo's established structural parser (single source of truth),
    # not an ad-hoc global hex scan.
    r = RESOLVE.read_text(encoding="utf-8")
    s = STATUS.read_text(encoding="utf-8")
    for src in (r, s):
        assert "from zeabur_readonly_diagnostic import" in src
        assert "_deployment_records" in src
    assert "_dep_id" in r
    assert "_dep_status" in s
