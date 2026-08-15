"""Isolated JSONL → PostgreSQL evidence mirror (never wired to live conductor)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_persistence_pg.evidence_db_mirror import canonical_content_sha256
from backend.nexus_persistence_pg.runtime import EvidenceDbWriter


@dataclass
class EvidenceMirrorService:
    pool: PostgresPool

    def ensure_campaign(self, campaign_id: str, *, status: str = "mirror") -> None:
        self.pool.execute(
            """
            INSERT INTO nexus.campaigns (campaign_id, created_at, status, real_money)
            VALUES (%s, NOW(), %s, FALSE)
            ON CONFLICT (campaign_id) DO NOTHING
            """,
            (campaign_id, status),
        )

    def import_jsonl(
        self,
        campaign_id: str,
        stream_name: str,
        jsonl_path: Path,
    ) -> dict[str, Any]:
        self.ensure_campaign(campaign_id)
        writer = EvidenceDbWriter(self.pool)
        imported = 0
        skipped = 0
        path = Path(jsonl_path)
        if not path.exists():
            return {"imported": 0, "skipped": 0, "missing": True}
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                payload = json.loads(line)
                # Hash the parsed persisted record canonically, not the
                # incidental whitespace/key ordering of a JSONL source line.
                digest = canonical_content_sha256(payload)
                before = self.pool.fetchval(
                    """
                    SELECT COUNT(*) FROM nexus.runtime_evidence_events
                    WHERE campaign_id=%s AND stream_name=%s AND content_sha256=%s
                    """,
                    (campaign_id, stream_name, digest),
                )
                writer.append_event(
                    {
                        "campaign_id": campaign_id,
                        "stream_name": stream_name,
                        "event_time_ms": payload.get("event_time_ms"),
                        "symbol": payload.get("symbol"),
                        "decision_id": payload.get("decision_id"),
                        "candidate_id": payload.get("candidate_id"),
                        "position_id": payload.get("position_id"),
                        "lifecycle_id": payload.get("lifecycle_id"),
                        "cycle_index": payload.get("cycle_index"),
                        "payload_json": payload,
                        "content_sha256": digest,
                    }
                )
                after = self.pool.fetchval(
                    """
                    SELECT COUNT(*) FROM nexus.runtime_evidence_events
                    WHERE campaign_id=%s AND stream_name=%s AND content_sha256=%s
                    """,
                    (campaign_id, stream_name, digest),
                )
                if after and (not before):
                    imported += 1
                else:
                    skipped += 1
        return {"imported": imported, "skipped": skipped, "missing": False}

    def import_evidence_dir(self, campaign_id: str, evidence_dir: Path) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for path in sorted(Path(evidence_dir).glob("*.jsonl")):
            results[path.name] = self.import_jsonl(campaign_id, path.name, path)
        return results
