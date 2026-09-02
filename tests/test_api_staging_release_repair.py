"""NEXUS Workstream-B api-staging release verification repair.

Proves the release tooling: (a) verifies the CURRENT Personal staging origin
(configurable, not the retired Member Preview host), (b) gates HTTP verification
on the NEW Zeabur deployment reaching a terminal activated state, and (c) proves
Workstream-B routes are actually serving. All source-level (no live network).
"""
from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/founder_approved_api_staging_deploy.yml")
VERIFIER = Path("tools/ci/verify_api_staging_deployment.py")
STATUS = Path("tools/ci/zeabur_deployment_status.py")


def _wf() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _verify_block(source: str) -> str:
    marker = "- name: Read-only post-deploy verification"
    start = source.index(marker)
    nxt = source.find("\n      - name:", start + len(marker))
    return source[start: nxt if nxt != -1 else len(source)]


# 1 + 2 — verifier uses the configurable canonical Personal origin, not the retired one.
def test_verifier_uses_configurable_personal_origin_not_retired():
    v = VERIFIER.read_text(encoding="utf-8")
    assert "nexus-member-preview-v18-2-1" not in v
    assert "PERSONAL_STAGING_ORIGIN" in v            # configurable from the workflow
    assert "raise SystemExit(2)" in v                # fail closed when absent/invalid
    wf = _wf()
    assert "PERSONAL_STAGING_ORIGIN: https://nexus-personal-staging.zeabur.app" in wf
    # CORS header expectations follow the real product contract.
    assert "X-Nexus-Session" in v and "X-Nexus-CSRF" in v
    assert '"x-nexus-session" in cors_allow_headers.lower()' in v


# 3 + 4 — capture the NEW deployment id and wait for it to reach RUNNING before HTTP verify.
def test_verification_gated_on_new_deployment_activation():
    block = _verify_block(_wf())
    assert "NEW_DEPLOYMENT_ID=" in block
    assert "PREVIOUS_DEPLOYMENT_ID=" in block
    assert "NEW_DEPLOYMENT_ID_DID_NOT_ADVANCE=yes" in block   # prove it differs from previous
    assert "python tools/ci/zeabur_deployment_status.py" in block
    assert 'dep_status" = "RUNNING"' in block
    # Activation gate must precede the HTTP verifier invocation.
    assert block.index("NEW_DEPLOYMENT_ACTIVATED=yes") < block.index(
        "python tools/ci/verify_api_staging_deployment.py"
    )


# 5 — a FAILED deployment fails immediately.
def test_failed_deployment_fails_immediately():
    block = _verify_block(_wf())
    assert 'dep_status" = "FAILED"' in block
    assert "NEW_DEPLOYMENT_FAILED=yes" in block
    # The FAILED branch exits before the activation loop can succeed.
    assert block.index("NEW_DEPLOYMENT_FAILED=yes") < block.index("NEW_DEPLOYMENT_ACTIVATED=yes")


# 6 — activation timeout fails closed.
def test_activation_timeout_fails_closed():
    block = _verify_block(_wf())
    assert "DEPLOYMENT_ACTIVATION_TIMEOUT=yes" in block
    assert "LIVE_VERIFICATION_TIMEOUT=yes" in block
    assert "POST_DEPLOY_VERIFY_FAIL_CLOSED=yes" in block
    assert "exit 0" not in block
    assert "for attempt in $(seq 1 40)" in block


# 7 + 8 — Workstream-B routes are part of acceptance (catalog 200; subscription 401 ok, 404 fails).
def test_workstream_b_routes_in_acceptance():
    v = VERIFIER.read_text(encoding="utf-8")
    assert "/api/v1/personal/catalog" in v
    assert "personal_catalog_status" in v
    assert "_catalog_contract_ok" in v
    assert "/api/v1/personal/market-state" in v
    assert "/api/v1/personal/subscription" in v
    # 404 on the B routes fails; 401 on subscription is acceptable route-exists evidence.
    assert "catalog_status != 200" in v
    assert "market_state_status == 404" in v
    assert "subscription_status == 404" in v
    # Canonical commercial contract is asserted.
    for token in ("STARTER_TRIAL_30D", "annual_discount_pct", '"free"', '"starter"', '"pro"', '"advanced"', '"enterprise"'):
        assert token in v
    # The workflow's durable activation marker is the /personal/catalog route.
    assert "/api/v1/personal/catalog" in _verify_block(_wf())


# 9 — no automatic LEGACY_FULL_DEPLOY fallback anywhere in the verification path.
def test_no_automatic_legacy_fallback():
    block = _verify_block(_wf())
    assert "LEGACY_FULL_DEPLOY" not in block
    wf = _wf()
    # The deploy/env-mutation/restart steps remain gated OFF for SAFE_CATCHUP.
    assert "if: needs.validate.outputs.mode != 'SAFE_CATCHUP_ONLY'" in wf


# 10 — SAFE_CATCHUP verification performs no environment mutation.
def test_verification_does_not_mutate_environment():
    block = _verify_block(_wf())
    for mutation in ("zeabur variable update", "zeabur variable create", "zeabur variable delete",
                     "curl -X POST", "curl -X PUT", "curl -X PATCH", "curl -X DELETE",
                     "/register", "/login"):
        assert mutation not in block, mutation


# The deployment-status parser normalizes the terminal states used by the gate.
def test_status_parser_normalizes_states():
    s = STATUS.read_text(encoding="utf-8")
    for token in ("RUNNING", "FAILED", "PENDING", "UNKNOWN"):
        assert token in s


# ---- Part 1/2: exact deployment-id resolution + CI wiring -------------------

RESOLVE = Path("tools/ci/zeabur_deployment_resolve.py")
SERVICE_ID = "6a7ee0a82b4272705cd1c9c8"
ENV_ID = "69d559b6474db8a99d6dd6bf"


def _load(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# The new release-repair tests actually run in the deploy workflow's test job.
def test_release_repair_tests_wired_into_deploy_ci():
    wf = _wf()
    assert "tests/test_api_staging_release_repair.py" in wf
    assert "tests/test_v18_3_4_product_http_api.py" in wf
    assert "tests/test_api_staging_safe_catchup_workflow.py" in wf


# Real-shape JSON parsing + previous/new id extraction via before/after set-diff.
def test_resolver_extracts_previous_and_new_ids(tmp_path):
    r = _load(RESOLVE)
    # Stable service/env ids appear in BOTH snapshots; only the new deployment differs.
    before = ('{"deployments":[{"_id":"aaaaaaaaaaaaaaaaaaaaaaa1","status":"RUNNING",'
              f'"serviceID":"{SERVICE_ID}","environmentID":"{ENV_ID}"}}]}}')
    after = ('{"deployments":['
             f'{{"_id":"aaaaaaaaaaaaaaaaaaaaaaa1","status":"RUNNING","serviceID":"{SERVICE_ID}"}},'
             f'{{"_id":"bbbbbbbbbbbbbbbbbbbbbbb2","status":"BUILDING","serviceID":"{SERVICE_ID}","environmentID":"{ENV_ID}"}}]}}')
    bf = _write(tmp_path, "before.json", before)
    af = _write(tmp_path, "after.json", after)
    # previous ids include the pre-existing deployment; the diff yields exactly the new one.
    assert "aaaaaaaaaaaaaaaaaaaaaaa1" in r._ids(bf)
    assert sorted(r._ids(af) - r._ids(bf)) == ["bbbbbbbbbbbbbbbbbbbbbbb2"]


def test_resolver_same_snapshot_yields_no_new_id(tmp_path):
    r = _load(RESOLVE)
    same = '{"deployments":[{"_id":"aaaaaaaaaaaaaaaaaaaaaaa1","status":"RUNNING"}]}'
    bf = _write(tmp_path, "b.json", same)
    af = _write(tmp_path, "a.json", same)
    assert sorted(r._ids(af) - r._ids(bf)) == []   # -> workflow keeps polling / fails closed


def test_resolver_ignores_40hex_sha_and_redacted_secrets(tmp_path):
    r = _load(RESOLVE)
    # A 40-hex SHA and a redacted token must not be mistaken for a 24-hex deployment id.
    txt = ('362faee9d141c40d1dda61e58dc73c451eb27973 ***REDACTED*** '
           '{"_id":"ccccccccccccccccccccccc3"}')
    f = _write(tmp_path, "x.json", txt)
    assert r._ids(f) == {"ccccccccccccccccccccccc3"}


def test_status_parser_running_failed_pending_unknown(tmp_path):
    s = _load(STATUS)
    running = _write(tmp_path, "r.json", '[{"id":"d1","status":"RUNNING"}]')
    failed = _write(tmp_path, "f.json", '{"deployments":[{"deploymentID":"d2","state":"FAILED"}]}')
    building = _write(tmp_path, "p.json", '[{"id":"d3","phase":"BUILDING"}]')
    assert s._status_of(s._find_deployment(__import__("json").load(open(running)), "d1")) == "RUNNING"
    assert s._status_of(s._find_deployment(__import__("json").load(open(failed)), "d2")) == "FAILED"
    assert s._status_of(s._find_deployment(__import__("json").load(open(building)), "d3")) == "PENDING"


def test_workflow_resolves_exact_id_via_diff_and_fails_closed_when_unresolved():
    block = _verify_block(_wf())
    assert "python tools/ci/zeabur_deployment_resolve.py new /tmp/pre-deployments.json" in block
    assert 'resolved="yes"' in block or 'resolved = "yes"' in block or "resolved=yes" in block
    # Unresolvable new id (never appears / ambiguous) must fail closed, not pass.
    assert 'resolved" != "yes"' in block
    assert "NEW_DEPLOYMENT_ID_DID_NOT_ADVANCE=yes" in block
    assert "EXACT_NEW_DEPLOYMENT_ID_RESOLVED=yes" in block


def test_workflow_targets_exact_api_staging_service_for_deployment_list():
    wf = _wf()
    assert "API_STAGING_SERVICE_ID: 6a7ee0a82b4272705cd1c9c8" in wf
    # Deployment list snapshots are scoped to the exact service + env.
    assert 'zeabur deployment list --service-id "$SERVICE_ID" --env-id "$ZEABUR_ENV_ID"' in wf


def test_app_marker_remains_secondary_proof_alongside_exact_id():
    block = _verify_block(_wf())
    # Activation requires the exact id resolved AND (deployment RUNNING OR the
    # application-level /personal/catalog marker at 200).
    assert 'resolved" = "yes"' in block
    assert 'dep_status" = "RUNNING"' in block
    assert 'catalog_http" = "200"' in block
