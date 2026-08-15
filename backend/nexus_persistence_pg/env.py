"""Environment guard for optional PostgreSQL runtime."""
from __future__ import annotations

import os

ALLOWED_ENVIRONMENTS = frozenset({"LOCAL", "TEST", "STAGING"})


def current_environment() -> str:
    return (os.getenv("NEXUS_ENV") or os.getenv("NEXUS_ENVIRONMENT") or "LOCAL").strip().upper()


def assert_pg_environment_allowed() -> None:
    env = current_environment()
    if env not in ALLOWED_ENVIRONMENTS:
        raise RuntimeError(
            f"postgresql_runtime_blocked_in_environment:{env}; "
            f"allowed={sorted(ALLOWED_ENVIRONMENTS)}"
        )


def is_test_database_url(url: str | None) -> bool:
    if not url:
        return False
    marker = (os.getenv("NEXUS_TEST_DATABASE_URL") or "").strip()
    return bool(marker) and url == marker
