"""One-shot, disposable qualification of the deployed API staging backend.

Run only inside ``nexus-api-staging`` through Zeabur service exec.  It never
prints a DSN, session token, account ID, or other credential and removes every
qualification row in ``finally``.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_persistence_pg.runtime import PostgresRuntimeConfig
from backend.nexus_product_backend.audit_alpha import ProductAuditAlphaService
from backend.nexus_product_backend.auth_alpha import AuthAlphaService
from backend.nexus_product_backend.entitlement_alpha import EntitlementAlphaService
from backend.nexus_product_backend.rbac_alpha import RbacAlphaService
from backend.nexus_product_backend.repository import ProductRepository


def _cleanup(pool: PostgresPool, account_id: str | None) -> None:
    if not account_id:
        return
    # Delete dependent qualification records explicitly; never alter migration
    # history, seeded roles/permissions, or unrelated staging entities.
    for statement in (
        "DELETE FROM nexus.product_audit_events WHERE actor_account_id = %s",
        "DELETE FROM nexus.rbac_bindings WHERE account_id = %s",
        "DELETE FROM nexus.entitlements WHERE account_id = %s",
        "DELETE FROM nexus.auth_sessions WHERE account_id = %s",
        "DELETE FROM nexus.one_time_tokens WHERE account_id = %s",
        "DELETE FROM nexus.mfa_factors WHERE account_id = %s",
        "DELETE FROM nexus.password_credentials WHERE account_id = %s",
        "DELETE FROM nexus.email_identities WHERE account_id = %s",
        "DELETE FROM nexus.accounts WHERE account_id = %s",
    ):
        pool.execute(statement, (account_id,))


def run() -> dict[str, Any]:
    cfg = PostgresRuntimeConfig.from_env()
    if not cfg.enabled or not cfg.database_url:
        raise RuntimeError("database_not_configured")

    pool = PostgresPool(cfg.database_url)
    pool.open()
    account_id: str | None = None
    try:
        repo = ProductRepository(pool)
        auth = AuthAlphaService(repo)
        entitlement = EntitlementAlphaService(repo, auth)
        rbac = RbacAlphaService(repo, auth)
        audit = ProductAuditAlphaService(repo)
        nonce = uuid.uuid4().hex

        registration = auth.register(f"api-staging-e2e-{nonce}@invalid.example", "e2e-only-password")
        account_id = registration["account_id"]
        session_id = registration["session_id"]
        created = repo.get_active_session(session_id) is not None
        repo.pool.execute(
            "UPDATE nexus.accounts SET status = 'suspended' WHERE account_id = %s",
            (account_id,),
        )
        updated = bool(
            repo.pool.fetchval(
                "SELECT status = 'suspended' FROM nexus.accounts WHERE account_id = %s",
                (account_id,),
            )
        )
        repo.pool.execute(
            "UPDATE nexus.accounts SET status = 'active' WHERE account_id = %s",
            (account_id,),
        )
        repo.grant_entitlement(account_id, "PRO")
        repo.bind_role(account_id, "role_admin")

        entitlement_result = entitlement.decision_from_session(session_id, "MARKET_OVERVIEW")
        rbac_result = rbac.permissions_for_session(session_id)
        audit_result = audit.record(
            actor_account_id=account_id,
            action="staging.e2e.qualification",
            resource_type="qualification",
        )

        # Exercise the same route registration served by the API, without
        # exposing the temporary session ID over HTTP or output.
        from api_staging_app import app

        client = app.test_client()
        protected_read = client.get(
            "/api/v1/product/shadow-watch-snapshot",
            headers={"X-Nexus-Session": session_id},
        )
        auth.logout(session_id)
        revoked_read = client.get(
            "/api/v1/product/shadow-watch-snapshot",
            headers={"X-Nexus-Session": session_id},
        )
        migrations = int(pool.fetchval("SELECT COUNT(*) FROM nexus.schema_migrations") or 0)

        checks = {
            "private_database_ready": pool.fetchval("SELECT 1") == 1,
            "migration_history_intact": migrations >= 2,
            "create_read": created,
            "update": updated,
            "entitlement_allowed": bool(entitlement_result.get("allowed")),
            "rbac_allowed": "org.view_audit" in (rbac_result.get("permissions") or []),
            "audit_persisted": bool(audit_result.get("event_id")),
            "authenticated_protected_read": protected_read.status_code == 200,
            "revoked_session_denied": revoked_read.status_code == 401,
        }
        if not all(checks.values()):
            raise RuntimeError(f"qualification_checks_failed:{checks}")
        return {"ok": True, "checks": checks, "cleanup": "pending"}
    finally:
        _cleanup(pool, account_id)
        pool.close()


def main() -> int:
    result = run()
    result["cleanup"] = "completed"
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
