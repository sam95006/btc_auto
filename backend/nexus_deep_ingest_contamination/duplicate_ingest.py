"""Duplicate dataset ingestion detection — content-hash + dataset-id identity."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DatasetIngestResult:
    status: str  # INGESTED | DUPLICATE | REJECTED
    dataset_id: str
    content_hash: str
    action: str
    prior_ingest_id: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dataset_id": self.dataset_id,
            "content_hash": self.content_hash,
            "action": self.action,
            "prior_ingest_id": self.prior_ingest_id,
            "detail": self.detail,
        }


@dataclass
class DuplicateDatasetIngestor:
    """Tracks dataset identity by (dataset_id, content_hash) — duplicates are skipped."""

    max_batches: int = 32
    _by_hash: dict[str, str] = field(default_factory=dict)
    _by_id: dict[str, str] = field(default_factory=dict)
    _ingest_log: list[dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def hash_payload(payload: Any) -> str:
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
        return hashlib.sha256(blob).hexdigest()

    def ingest(
        self,
        *,
        dataset_id: str,
        payload: Any,
        ingest_id: str,
        allow_id_collision_different_hash: bool = False,
    ) -> DatasetIngestResult:
        if len(self._ingest_log) >= self.max_batches and ingest_id not in {
            e["ingest_id"] for e in self._ingest_log
        }:
            return DatasetIngestResult(
                status="REJECTED",
                dataset_id=dataset_id,
                content_hash="",
                action="budget_exceeded",
                detail=f"max_batches={self.max_batches}",
            )
        content_hash = self.hash_payload(payload)
        if content_hash in self._by_hash:
            return DatasetIngestResult(
                status="DUPLICATE",
                dataset_id=dataset_id,
                content_hash=content_hash,
                action="skipped",
                prior_ingest_id=self._by_hash[content_hash],
                detail="identical_content_hash",
            )
        if dataset_id in self._by_id:
            prior_hash = self._by_id[dataset_id]
            if prior_hash != content_hash and not allow_id_collision_different_hash:
                return DatasetIngestResult(
                    status="REJECTED",
                    dataset_id=dataset_id,
                    content_hash=content_hash,
                    action="id_conflict",
                    prior_ingest_id=self._by_hash.get(prior_hash),
                    detail="dataset_id_reused_with_different_hash",
                )
        self._by_hash[content_hash] = ingest_id
        self._by_id[dataset_id] = content_hash
        entry = {
            "ingest_id": ingest_id,
            "dataset_id": dataset_id,
            "content_hash": content_hash,
            "status": "INGESTED",
        }
        self._ingest_log.append(entry)
        return DatasetIngestResult(
            status="INGESTED",
            dataset_id=dataset_id,
            content_hash=content_hash,
            action="appended",
            detail="new_dataset",
        )

    def duplicate_attack_probe(self, *, dataset_id: str, payload: Any) -> dict[str, Any]:
        """Re-ingest identical payload — must return DUPLICATE, never double-count."""
        first = self.ingest(dataset_id=dataset_id, payload=payload, ingest_id=f"{dataset_id}:1")
        second = self.ingest(dataset_id=dataset_id, payload=payload, ingest_id=f"{dataset_id}:2")
        blocked = first.status == "INGESTED" and second.status == "DUPLICATE"
        return {
            "attack_id": "duplicate_dataset_reingest",
            "attack_blocked": blocked,
            "survivor": not blocked,
            "first": first.to_dict(),
            "second": second.to_dict(),
            "unique_hash_count": len(self._by_hash),
            "ingest_log_len": len(self._ingest_log),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "unique_hashes": len(self._by_hash),
            "unique_dataset_ids": len(self._by_id),
            "ingest_log_len": len(self._ingest_log),
            "max_batches": self.max_batches,
        }
