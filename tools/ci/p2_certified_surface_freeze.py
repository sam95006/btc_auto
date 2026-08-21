"""Helpers for certified-surface freeze checks (diagnostics-only commits)."""
from __future__ import annotations

FORBIDDEN_CERTIFIED_SURFACE_PREFIXES: tuple[str, ...] = (
    "backend/nexus_demo_execution/",
    "backend/nexus_persistence_pg/migrations/0001_",
    "backend/nexus_persistence_pg/migrations/0002_",
    "backend/nexus_persistence_pg/migrations/0003_",
    "backend/nexus_persistence_pg/migrations/0004_",
    "backend/nexus_persistence_pg/migrations/0005_",
    "backend/nexus_persistence_pg/migrations/0006_",
    ".github/workflows/founder_approved_bybit_demo_p1_",
    ".github/workflows/founder_approved_staging_postgres_p1_migration.yml",
    "backend/bybit/",
    "tools/ci/p2_1_postgres_qualification.py",
)
