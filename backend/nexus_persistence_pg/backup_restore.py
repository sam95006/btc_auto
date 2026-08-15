"""Backup manifest and restore verification for isolated PostgreSQL databases."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.nexus_persistence_pg.migrate import MigrationRunner, list_migrations
from backend.nexus_persistence_pg.pool import PostgresPool


@dataclass
class BackupRestoreVerifier:
    pool: PostgresPool

    def schema_version(self) -> str | None:
        return self.pool.fetchval(
            """
            SELECT version FROM nexus.schema_migrations
            ORDER BY version DESC LIMIT 1
            """
        )

    def row_counts(self) -> dict[str, int]:
        rows = self.pool.fetchall(
            """
            SELECT relname, n_live_tup::bigint
            FROM pg_stat_user_tables
            WHERE schemaname = 'nexus'
            ORDER BY relname
            """
        )
        return {name: int(count or 0) for name, count in rows}

    def exact_row_counts(self) -> dict[str, int]:
        tables = [
            row[0]
            for row in self.pool.fetchall(
                "SELECT tablename FROM pg_tables WHERE schemaname='nexus' ORDER BY tablename"
            )
        ]
        counts: dict[str, int] = {}
        for table in tables:
            counts[table] = int(
                self.pool.fetchval(f"SELECT COUNT(*) FROM nexus.{table}") or 0
            )
        return counts

    def evidence_hashes(self, campaign_id: str | None = None) -> list[str]:
        if campaign_id:
            rows = self.pool.fetchall(
                """
                SELECT content_sha256 FROM nexus.runtime_evidence_events
                WHERE campaign_id=%s ORDER BY id
                """,
                (campaign_id,),
            )
        else:
            rows = self.pool.fetchall(
                "SELECT content_sha256 FROM nexus.runtime_evidence_events ORDER BY id"
            )
        return [r[0] for r in rows]

    def build_manifest(self, *, campaign_id: str | None = None) -> dict[str, Any]:
        counts = self.row_counts()
        hashes = self.evidence_hashes(campaign_id)
        digest = hashlib.sha256("\n".join(hashes).encode("utf-8")).hexdigest() if hashes else None
        return {
            "schema": "nexus_backup_manifest_v1",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "schema_version": self.schema_version(),
            "migration_catalog": MigrationRunner().catalog(),
            "row_counts": counts,
            "evidence_hash_count": len(hashes),
            "evidence_aggregate_sha256": digest,
            "campaign_id": campaign_id,
        }

    def verify_against(self, expected: dict[str, Any]) -> dict[str, Any]:
        current = self.build_manifest(campaign_id=expected.get("campaign_id"))
        mismatches: list[str] = []
        if current.get("schema_version") != expected.get("schema_version"):
            mismatches.append("schema_version")
        for table, count in (expected.get("row_counts") or {}).items():
            if current["row_counts"].get(table) != count:
                mismatches.append(f"row_count:{table}")
        if expected.get("evidence_hash_count") is not None:
            if current["evidence_hash_count"] != expected["evidence_hash_count"]:
                mismatches.append("evidence_hash_count")
        if expected.get("evidence_aggregate_sha256"):
            if current["evidence_aggregate_sha256"] != expected["evidence_aggregate_sha256"]:
                mismatches.append("evidence_aggregate_sha256")
        return {
            "ok": not mismatches,
            "mismatches": mismatches,
            "current": current,
        }

    @staticmethod
    def save_manifest(path: str, manifest: dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
