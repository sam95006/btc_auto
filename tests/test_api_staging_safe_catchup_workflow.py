from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/founder_approved_api_staging_deploy.yml")
VERIFY_SCRIPT = Path("tools/ci/verify_api_staging_deployment.py")


def _workflow_source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _step_block(source: str, step_name: str) -> str:
    marker = f"- name: {step_name}"
    start = source.index(marker)
    next_step = source.find("\n      - name:", start + len(marker))
    if next_step == -1:
        next_step = len(source)
    return source[start:next_step]


def test_safe_catchup_mode_requires_exact_founder_sha_and_current_main() -> None:
    source = _workflow_source()
    assert "SAFE_CATCHUP_ONLY" in source
    assert "LEGACY_FULL_DEPLOY" in source
    assert "target_sha:" in source
    assert "required: true" in source
    assert r"^[0-9a-fA-F]{40}$" in source
    assert "ref: ${{ github.event.inputs.target_sha }}" in source
    assert "ref: ${{ needs.validate.outputs.target_sha }}" in source
    assert 'git cat-file -e "$TARGET_SHA^{commit}"' in source
    assert 'git checkout --detach "$TARGET_SHA"' in source
    assert 'CHECKED_OUT_HEAD="$(git rev-parse HEAD)"' in source
    assert 'if [ "$TARGET_SHA" != "$ORIGIN_MAIN_SHA" ]; then' in source
    assert "TARGET_SHA_MATCHES_CHECKED_OUT_HEAD=yes" in source
    assert "TARGET_SHA_MUST_MATCH_CURRENT_MAIN=yes" in source


def test_safe_catchup_uses_exact_api_staging_service_without_creation_helper() -> None:
    source = _workflow_source()
    resolve_block = _step_block(source, "Resolve API staging service")
    safe_branch = resolve_block.split('if [ "$MODE" = "SAFE_CATCHUP_ONLY" ]; then', 1)[1].split("\n          else", 1)[0]
    assert "API_STAGING_SERVICE_ID: 6a7ee0a82b4272705cd1c9c8" in source
    assert 'SID="$API_STAGING_SERVICE_ID"' in safe_branch
    assert 'zeabur service get --id "$SID"' in safe_branch
    assert "ensure_api_staging_zeabur_service.py" not in safe_branch
    assert 'if [ "$SID" != "$API_STAGING_SERVICE_ID" ]; then' in resolve_block
    for forbidden in (
        "FORBIDDEN_MEMBER_PREVIEW",
        "FORBIDDEN_MEMBER_PREVIEW_STATIC",
        "FORBIDDEN_STAGE3",
        "FORBIDDEN_VALIDATION",
        "FORBIDDEN_OLD_VALIDATION",
        "nexus-member-preview-v18-2-1",
        "member-preview-static",
        "nexus-bybit-demo-learning-validation",
    ):
        assert forbidden in source


def test_safe_catchup_environment_check_is_read_only_and_fail_closed() -> None:
    source = _workflow_source()
    safe_env_block = _step_block(source, "Safe catch-up read-only environment guard")
    assert "if: needs.validate.outputs.mode == 'SAFE_CATCHUP_ONLY'" in safe_env_block
    assert "zeabur variable list" in safe_env_block
    assert "zeabur variable update" not in safe_env_block
    assert "zeabur variable create" not in safe_env_block
    assert "ENV_MUTATION_IN_SAFE_CATCHUP=no" in safe_env_block
    for required in (
        '"NEXUS_ENV": "STAGING"',
        '"NEXUS_STAGING_SESSION_BOOTSTRAP": "false"',
        '"NEXUS_STAGING_MEMBER_AUTH_ENABLED": "true"',
        '"NEXUS_STAGING_REGISTRATION_ENABLED": "true"',
        '"EXCHANGE_WRITE": "false"',
        '"MAINNET": "false"',
        '"REAL_MONEY": "false"',
        '"NEXUS_MEMBER_EXECUTION": "false"',
        '"NEXUS_RUNTIME_BINDING": "UNAVAILABLE"',
        '"NEXUS_PG_RUNTIME_ENABLED": "true"',
        "NEXUS_CORS_ALLOWED_ORIGINS",
        "DATABASE_URL",
        "NEXUS_POSTGRES_URL",
    ):
        assert required in safe_env_block


def test_safe_catchup_skips_legacy_env_mutation_restart_and_db_e2e() -> None:
    source = _workflow_source()
    legacy_env_block = _step_block(source, "Set and verify required staging API variables")
    legacy_restart_block = _step_block(source, "Legacy explicit service restart")
    legacy_e2e_block = _step_block(source, "Private Postgres staging E2E (in-pod, auto-cleanup)")
    assert "if: needs.validate.outputs.mode != 'SAFE_CATCHUP_ONLY'" in legacy_env_block
    assert "zeabur variable update" in legacy_env_block
    assert "zeabur variable create" in legacy_env_block
    assert "if: needs.validate.outputs.mode != 'SAFE_CATCHUP_ONLY'" in legacy_restart_block
    assert "zeabur service restart" in legacy_restart_block
    assert "if: needs.validate.outputs.mode != 'SAFE_CATCHUP_ONLY'" in legacy_e2e_block
    assert "backend.nexus_product_backend.staging_e2e" in legacy_e2e_block
    deploy_block = _step_block(source, "Deploy API staging only")
    assert "zeabur deploy --project-id" in deploy_block
    assert "zeabur service restart" not in deploy_block
    assert "EXPLICIT_SERVICE_RESTART_IN_SAFE_CATCHUP=no" in deploy_block


def test_safe_catchup_post_deploy_verification_is_read_only_and_checks_pr41_markers() -> None:
    source = _workflow_source()
    verify_block = _step_block(source, "Read-only post-deploy verification")
    assert "python tools/ci/verify_api_staging_deployment.py" in verify_block
    assert "READ_ONLY_POST_DEPLOY_VERIFY=yes" in verify_block
    assert "CORS_CSRF_MARKER_VERIFIED_BY_WORKFLOW=yes" in verify_block
    assert "AUTH_FOUNDATION_MARKER_VERIFIED_BY_WORKFLOW=yes" in verify_block
    forbidden_mutations = (
        "curl -X POST",
        "curl -X PUT",
        "curl -X PATCH",
        "curl -X DELETE",
        "method=\"POST\"",
        "method=\"PUT\"",
        "method=\"PATCH\"",
        "method=\"DELETE\"",
        "/register",
        "/login",
        "staging_e2e",
    )
    assert not any(token in verify_block for token in forbidden_mutations)

    verifier = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "method=\"OPTIONS\"" in verifier
    assert "X-Nexus-CSRF" in verifier
    assert "/api/v1/product/auth/foundation" in verifier
    assert "inline_verification_token_allowed_in_production" in verifier
    assert "is not False" in verifier


def test_safe_catchup_preserves_rollback_metadata_without_auto_rollback() -> None:
    source = _workflow_source()
    assert "Capture previous deployment metadata" in source
    assert "Capture new deployment metadata" in source
    assert "ROLLBACK_METADATA_CAPTURED=yes" in source
    assert "PREVIOUS_DEPLOYMENT_ID" in source
    assert "NEW_DEPLOYMENT_ID" in source
    assert "rollback" not in source.lower().replace("rollback_metadata", "").replace("rollback_previous", "")
