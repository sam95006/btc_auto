"""Filesystem migration runner with offline validation and explicit apply.

Apply to a real PostgreSQL instance only via explicit operator action.
Never touches the running Shadow campaign evidence directory.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from backend.nexus_persistence_pg.constants import PACKAGE, SCHEMA, SCHEMA_VERSION
from backend.nexus_persistence_pg.env import assert_pg_environment_allowed

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_VERSION_RE = re.compile(r"^(\d{4})_.+\.sql$")
_DESTRUCTIVE_RE = re.compile(
    r"\b(DROP\s+TABLE|DROP\s+SCHEMA|TRUNCATE\s+TABLE|DELETE\s+FROM)\b",
    re.IGNORECASE,
)


class MigrationExecutor(Protocol):
    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> None: ...

    def fetchall(self, statement: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]: ...


@dataclass(frozen=True)
class MigrationFile:
    version: str
    path: Path
    description: str
    checksum_sha256: str
    sql: str


def list_migrations(directory: Path | None = None) -> list[MigrationFile]:
    root = directory or MIGRATIONS_DIR
    files: list[MigrationFile] = []
    for path in sorted(root.glob("*.sql")):
        m = _VERSION_RE.match(path.name)
        if not m:
            raise ValueError(f"invalid migration filename: {path.name}")
        sql = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        desc = path.stem.split("_", 1)[1].replace("_", " ")
        files.append(
            MigrationFile(
                version=m.group(1),
                path=path,
                description=desc,
                checksum_sha256=digest,
                sql=sql,
            )
        )
    return files


@dataclass
class MigrationRunner:
    """Offline validator / dry-run catalog. Does not open DB sockets by default."""

    migrations_dir: Path = MIGRATIONS_DIR

    def catalog(self) -> dict[str, Any]:
        migrations = list_migrations(self.migrations_dir)
        return {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "package": PACKAGE,
            "migrations_dir": str(self.migrations_dir),
            "migration_count": len(migrations),
            "migrations": [
                {
                    "version": m.version,
                    "description": m.description,
                    "path": str(m.path),
                    "checksum_sha256": m.checksum_sha256,
                    "bytes": len(m.sql.encode("utf-8")),
                }
                for m in migrations
            ],
            "live_trading_wired": False,
            "lesson_auto_apply": False,
        }

    def validate(self) -> dict[str, Any]:
        migrations = list_migrations(self.migrations_dir)
        errors: list[str] = []
        if not migrations:
            errors.append("no_migrations_found")
        versions = [m.version for m in migrations]
        if versions != sorted(versions):
            errors.append("versions_not_sorted")
        if len(versions) != len(set(versions)):
            errors.append("duplicate_versions")
        required_tokens = (
            "nexus.schema_migrations",
            "nexus.campaigns",
            "nexus.runtime_evidence_events",
            "nexus.reflections",
            "nexus.counterfactuals",
            "nexus.lesson_candidates",
            "nexus.decision_memory",
            "nexus.audit_log",
            "nexus.auth_sessions",
            "nexus.product_audit_events",
        )
        joined = "\n".join(m.sql for m in migrations)
        for token in required_tokens:
            if token not in joined:
                errors.append(f"missing_table_token:{token}")
        banned = ("ALTER TABLE nexus.lesson_candidates ENABLE", "live_policy_write")
        for b in banned:
            if b.lower() in joined.lower():
                errors.append(f"banned_token:{b}")
        for migration in migrations:
            if _DESTRUCTIVE_RE.search(migration.sql):
                errors.append(f"destructive_sql_detected:{migration.version}")
        return {
            "ok": not errors,
            "errors": errors,
            "catalog": self.catalog(),
        }

    def applied_versions(self, executor: MigrationExecutor) -> set[str]:
        rows = executor.fetchall("SELECT version, checksum_sha256 FROM nexus.schema_migrations")
        return {row[0] for row in rows}

    def detect_drift(self, executor: MigrationExecutor) -> list[str]:
        drift: list[str] = []
        rows = {
            row[0]: row[1]
            for row in executor.fetchall(
                "SELECT version, checksum_sha256 FROM nexus.schema_migrations"
            )
        }
        for migration in list_migrations(self.migrations_dir):
            if migration.version in rows and rows[migration.version] != migration.checksum_sha256:
                drift.append(f"checksum_drift:{migration.version}")
        return drift

    def bootstrap(self, executor: MigrationExecutor) -> None:
        assert_pg_environment_allowed()
        executor.execute(
            """
            CREATE SCHEMA IF NOT EXISTS nexus;
            CREATE TABLE IF NOT EXISTS nexus.schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                checksum_sha256 TEXT NOT NULL,
                description TEXT NOT NULL
            );
            """
        )

    def apply_pending(
        self,
        executor: MigrationExecutor,
        *,
        allow_destructive: bool = False,
    ) -> dict[str, Any]:
        """Apply pending migrations transactionally per file."""
        assert_pg_environment_allowed()
        validation = self.validate()
        if not validation["ok"]:
            return {"ok": False, "applied": [], "errors": validation["errors"]}

        self.bootstrap(executor)
        drift = self.detect_drift(executor)
        if drift:
            return {"ok": False, "applied": [], "errors": drift}

        applied: list[str] = []
        known = self.applied_versions(executor)
        for migration in list_migrations(self.migrations_dir):
            if migration.version in known:
                continue
            if _DESTRUCTIVE_RE.search(migration.sql) and not allow_destructive:
                return {
                    "ok": False,
                    "applied": applied,
                    "errors": [f"destructive_sql_blocked:{migration.version}"],
                }
            if hasattr(executor, "apply_migration"):
                executor.apply_migration(
                    migration.sql,
                    version=migration.version,
                    checksum_sha256=migration.checksum_sha256,
                    description=migration.description,
                )
            else:
                executor.execute(migration.sql)
                executor.execute(
                    """
                    INSERT INTO nexus.schema_migrations (version, checksum_sha256, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (version) DO NOTHING
                    """,
                    (migration.version, migration.checksum_sha256, migration.description),
                )
            applied.append(migration.version)
        return {"ok": True, "applied": applied, "errors": []}
