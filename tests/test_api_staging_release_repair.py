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
