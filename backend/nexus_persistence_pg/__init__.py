"""PostgreSQL persistence foundation (Track B) — schema only, not live-trading wired.

Does not activate Lesson / policy changes into Shadow or Demo execution.
"""
from __future__ import annotations

from backend.nexus_persistence_pg.backup_restore import BackupRestoreVerifier
from backend.nexus_persistence_pg.constants import PACKAGE, SCHEMA, SCHEMA_VERSION
from backend.nexus_persistence_pg.evidence_db_mirror import EvidenceDbMirror, canonical_content_sha256
from backend.nexus_persistence_pg.evidence_mirror import EvidenceMirrorService
from backend.nexus_persistence_pg.migrate import MigrationRunner, list_migrations
from backend.nexus_persistence_pg.mirror_factory import build_evidence_mirror_from_env, mirror_config_health
from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_persistence_pg.runtime import EvidenceDbWriter, PostgresRuntimeConfig

__all__ = [
    "PACKAGE",
    "SCHEMA",
    "SCHEMA_VERSION",
    "BackupRestoreVerifier",
    "EvidenceDbMirror",
    "EvidenceMirrorService",
    "MigrationRunner",
    "PostgresPool",
    "build_evidence_mirror_from_env",
    "canonical_content_sha256",
    "list_migrations",
    "mirror_config_health",
    "EvidenceDbWriter",
    "PostgresRuntimeConfig",
]