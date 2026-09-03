#!/usr/bin/env python3
"""STAGING-ONLY operator-assisted password recovery for an EXISTING normal-member
account, until real transactional email delivery is configured.

This is a narrow operator recovery path — NOT a public reset bypass and NOT the
production password-reset architecture. It:

  * refuses to run unless NEXUS_ENV / NEXUS_DEPLOYMENT_ENV == "staging";
  * reads the target email and the new password ONLY from environment variables
    (supplied via GitHub Actions Secrets) — never from arguments, logs, or code;
  * resolves the EXISTING account by email and fails closed if it cannot be
    uniquely resolved;
  * sets the password using the SAME canonical Argon2 hasher the auth service uses
    (fails closed if that hasher is unavailable — never a weaker hash);
  * revokes all existing sessions and appends an audit event;
  * NEVER changes account_id, accounts.created_at / registered_at, plan, trial, or
    subscription history;
  * NEVER prints the email, the password, or the password hash.

It does NOT use any Founder session/claim, and enables no execution/runtime.
"""
from __future__ import annotations

import os
import sys


def _fail(marker: str) -> "int":
    print(marker)
    print("RECOVERY_OK=no")
    return 1


def main() -> int:
    env = (os.getenv("NEXUS_ENV") or os.getenv("NEXUS_DEPLOYMENT_ENV") or "").strip().lower()
    if env != "staging":
        return _fail("RECOVERY_REFUSED_NON_STAGING=yes")
    print("RECOVERY_STAGING_ENV=yes")

    email = (os.getenv("NEXUS_STAGING_RECOVERY_EMAIL") or "").strip().lower()
    new_password = os.getenv("NEXUS_STAGING_RECOVERY_PASSWORD") or ""
    if not email or not new_password:
        return _fail("RECOVERY_MISSING_INPUTS=yes")
    if len(new_password) < 8:
        return _fail("RECOVERY_WEAK_PASSWORD=yes")

    from backend.nexus_persistence_pg.pool import PostgresPool
    from backend.nexus_persistence_pg.runtime import PostgresRuntimeConfig
    from backend.nexus_product_backend.auth_alpha import AuthAlphaService
    from backend.nexus_product_backend.repository import ProductRepository

    try:
        cfg = PostgresRuntimeConfig.from_env()
    except ValueError:
        return _fail("RECOVERY_DB_CONFIG_INVALID=yes")
    if not cfg.enabled or not cfg.database_url:
        return _fail("RECOVERY_DB_UNAVAILABLE=yes")

    pool = PostgresPool(cfg.database_url)
    pool.open()
    repo = ProductRepository(pool)
    auth = AuthAlphaService(repo)
    hasher = getattr(auth, "_hasher", None)
    if hasher is None:
        return _fail("RECOVERY_HASHER_UNAVAILABLE=yes")

    account = repo.get_account_by_email(email)
    if not account or not account.get("account_id"):
        # Fail closed: never proceed when the account is not uniquely resolvable.
        return _fail("RECOVERY_ACCOUNT_NOT_RESOLVED=yes")
    account_id = account["account_id"]
    print("ACCOUNT_RESOLVED=yes")

    # Canonical Argon2 hash; only the password credential + sessions are touched.
    repo.update_password_hash(account_id, hasher.hash(new_password))
    print("PASSWORD_UPDATED=yes")
    revoked = int(repo.revoke_all_sessions(account_id))
    print(f"SESSIONS_REVOKED={revoked}")
    repo.append_product_audit(
        actor_account_id=None,
        action="staging_operator_password_recovery",
        resource_type="account",
        resource_id=account_id,
        detail={"channel": "staging_operator_recovery", "sessions_revoked": revoked},
    )
    print("AUDIT_APPENDED=yes")
    # account_id / created_at / plan / trial / subscription are never written here.
    print("ACCOUNT_IMMUTABLE_FIELDS_UNCHANGED=yes")
    print("RECOVERY_OK=yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
