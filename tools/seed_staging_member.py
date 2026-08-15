"""Explicit, staging-only seed member provisioner.

Run as a controlled one-shot deployment job. It never runs during API startup
and refuses any environment other than staging.
"""
from __future__ import annotations

import os

from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_persistence_pg.runtime import PostgresRuntimeConfig
from backend.nexus_product_backend.auth_alpha import AuthAlphaService
from backend.nexus_product_backend.repository import ProductRepository


def main() -> None:
    if (os.getenv("NEXUS_ENV") or os.getenv("NEXUS_DEPLOYMENT_ENV") or "").strip().lower() != "staging":
        raise RuntimeError("staging_seed_refused_outside_staging")
    email = os.getenv("NEXUS_STAGING_SEED_EMAIL", "").strip().lower()
    password = os.getenv("NEXUS_STAGING_SEED_PASSWORD", "")
    if not email or len(password) < 12:
        raise RuntimeError("staging_seed_requires_email_and_12_character_password")
    cfg = PostgresRuntimeConfig.from_env()
    if not cfg.enabled or not cfg.database_url:
        raise RuntimeError("staging_seed_requires_postgres")
    pool = PostgresPool(cfg.database_url)
    pool.open()
    repo = ProductRepository(pool)
    auth = AuthAlphaService(repo)
    account = repo.get_account_by_email(email)
    account_id = account["account_id"] if account else auth.register(email, password)["account_id"]
    repo.grant_entitlement(account_id, "ADVANCED")
    repo.bind_role(account_id, "role_member")
    repo.profile(account_id)
    repo.member_preferences(account_id)
    repo.notification_preferences(account_id)
    print("staging_seed_member_ready")


if __name__ == "__main__":
    main()
