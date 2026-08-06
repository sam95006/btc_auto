"""Incremental backfill + live append ingest pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_bronze_immutable_raw_lake.lake import BronzeLake, DiskBudgetExceeded
from backend.nexus_incremental_backfill_live_ingest.bridges import LayerBridge
from backend.nexus_incremental_backfill_live_ingest.checkpoint import ResumeCheckpoint
from backend.nexus_incremental_backfill_live_ingest.constants import (
    ALLOWED_BACKFILL_WINDOWS_DAYS,
    DATA_CLASS_DEGRADED,
    DATA_CLASS_STALE,
    DATA_CLASS_UNAVAILABLE,
    DEFAULT_LICENSE_REFERENCE,
    DEFAULT_MAX_DISK_BYTES,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_SOURCE_ID,
    INGESTIBLE_DATA_CLASSES,
    NON_INGEST_DATA_CLASSES,
    PRIORITY_SYMBOLS,
)
from backend.nexus_incremental_backfill_live_ingest.counters import AcceptanceCounters
from backend.nexus_incremental_backfill_live_ingest.date_manifest import DatePartitionManifest
from backend.nexus_incremental_backfill_live_ingest.disk_quota import DiskQuota, DiskQuotaExceeded
from backend.nexus_incremental_backfill_live_ingest.hard_bans import (
    HardBanViolation,
    refuse_historical_rewrite,
    refuse_silent_gap_fill,
)
from backend.nexus_incremental_backfill_live_ingest.hashing import (
    content_hash_of,
    reject_future_timestamp,
    utc_now_iso,
)
from backend.nexus_incremental_backfill_live_ingest.license_gate import LicenseBindingError, LicenseGate
from backend.nexus_incremental_backfill_live_ingest.rate_limit import RateLimitController
from backend.nexus_incremental_backfill_live_ingest.retention import RetentionPolicy
from backend.nexus_incremental_backfill_live_ingest.samples import (
    fixture_batches,
    live_append_batches,
    official_historical_sample_batches,
)
from backend.nexus_pit_revision_v17.store import PitRevisionStore


class IngestPipeline:
    """Founder V18-B ingest: backfill + live append with full safety contract."""

    def __init__(
        self,
        root: Path,
        *,
        max_disk_bytes: int = DEFAULT_MAX_DISK_BYTES,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        license_gate: LicenseGate | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.bronze = BronzeLake(self.root / "bronze", max_disk_bytes=max_disk_bytes)
        self.pit = PitRevisionStore()
        self.bridge = LayerBridge(bronze=self.bronze, pit=self.pit)
        self.manifest = DatePartitionManifest(self.root / "manifest")
        self.checkpoint = ResumeCheckpoint(self.root / "resume_checkpoint.json")
        self.quota = DiskQuota(self.root, max_bytes=max_disk_bytes)
        self.retention = RetentionPolicy(retention_days=retention_days)
        self.rate_limit = RateLimitController()
        self.license = license_gate or LicenseGate()
        self.counters = AcceptanceCounters()
        self._seen_hashes: set[str] = set()
        self.quarantine_dir = self.root / "quarantine"
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    # --- safety helpers -------------------------------------------------

    def attempt_raw_rewrite(self, content_hash: str, new_payload: Any) -> None:
        """Any raw rewrite attempt increments counter and hard-refuses."""
        self.counters.raw_rewrite_count += 1
        _ = (content_hash, new_payload)
        refuse_historical_rewrite()

    def attempt_silent_gap_fill(self, *, gap_start: str, gap_end: str) -> None:
        self.counters.silent_gap_fill_count += 1
        _ = (gap_start, gap_end)
        refuse_silent_gap_fill()

    def classify_non_ingest(self, data_class: str) -> dict[str, Any]:
        if data_class not in NON_INGEST_DATA_CLASSES:
            raise ValueError(f"not_a_non_ingest_class:{data_class}")
        self.counters.bump_class(data_class)
        return {
            "status": "CLASSIFIED_ONLY",
            "data_class": data_class,
            "ingested": False,
            "at": utc_now_iso(),
        }

    def quarantine_corrupt(self, *, content_hash: str, reason: str, blob: bytes) -> dict[str, Any]:
        q_path = self.quarantine_dir / f"{content_hash}.bin"
        meta_path = self.quarantine_dir / f"{content_hash}.meta.json"
        q_path.write_bytes(blob)
        meta = {
            "content_hash": content_hash,
            "reason": reason,
            "quarantined_at": utc_now_iso(),
            "bytes": len(blob),
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # Also ask bronze to quarantine if present
        bronze_ptr = None
        rec = self.bronze.records_dir / f"{content_hash}.json"
        if rec.exists():
            try:
                bronze_ptr = self.bronze.quarantine_corrupt(content_hash, reason=reason)
            except Exception as exc:  # noqa: BLE001 — partial failure path
                bronze_ptr = {"error": str(exc)}
        self.counters.quarantined_count += 1
        return {"status": "QUARANTINED", "meta": meta, "bronze": bronze_ptr}

    # --- core ingest ----------------------------------------------------

    def ingest_one(
        self,
        batch: dict[str, Any],
        *,
        source_offset: int,
        mode: str,
        pit_kind: str = "OBSERVATION",
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        self.rate_limit.assert_not_paused()

        data_class = str(batch.get("data_class") or "")
        if data_class in NON_INGEST_DATA_CLASSES:
            return self.classify_non_ingest(data_class)
        if data_class not in INGESTIBLE_DATA_CLASSES:
            raise ValueError(f"unknown_data_class:{data_class}")

        symbol = str(batch["symbol_original"])
        source_id = str(batch.get("source_id") or DEFAULT_SOURCE_ID)
        license_reference = str(batch.get("license_reference") or DEFAULT_LICENSE_REFERENCE)
        exchange_timestamp = str(batch["exchange_timestamp"])
        received_timestamp = str(batch["received_timestamp"])
        payload = batch["payload"]

        # Future timestamp hard refuse
        try:
            reject_future_timestamp(exchange_timestamp, now_ms=now_ms)
        except HardBanViolation:
            self.counters.future_timestamp_accept_count += 1
            raise

        # License binding
        try:
            license_bind = self.license.assert_licensed(
                source_id=source_id, license_reference=license_reference
            )
        except (HardBanViolation, LicenseBindingError):
            self.counters.unlicensed_ingest_count += 1
            self.counters.license_reject_count += 1
            raise

        c_hash = content_hash_of(payload)
        # Local dedupe before bronze
        if c_hash in self._seen_hashes or self.bronze.has_content_hash(c_hash):
            self.counters.duplicate_resolved_count += 1
            self.counters.bump_class(data_class)
            self.manifest.append(
                exchange_timestamp=exchange_timestamp,
                content_hash=c_hash,
                symbol=symbol,
                source_id=source_id,
                data_class=data_class,
                status="DUPLICATE",
            )
            # Checkpoint still advances so resume contract stays monotonic
            self.checkpoint.write(
                symbol=symbol,
                exchange_timestamp=exchange_timestamp,
                content_hash=c_hash,
                source_offset=source_offset,
                data_class=data_class,
                mode=mode,
            )
            return {
                "status": "DUPLICATE",
                "content_hash": c_hash,
                "action": "skipped",
                "duplicate_resolved": True,
                "data_class": data_class,
            }

        # Disk quota (pipeline root + bronze)
        blob_size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        try:
            self.quota.assert_can_write(blob_size + 512)
        except DiskQuotaExceeded:
            self.counters.disk_quota_block_count += 1
            raise

        try:
            wired = self.bridge.ingest_event(
                exchange_timestamp=exchange_timestamp,
                received_timestamp=received_timestamp,
                source_id=source_id,
                symbol_original=symbol,
                payload=payload,
                data_class=data_class,
                license_reference=license_reference,
                source_offset=source_offset,
                pit_kind=pit_kind,
            )
        except DiskBudgetExceeded:
            self.counters.disk_quota_block_count += 1
            raise
        except Exception as exc:  # noqa: BLE001 — partial failure recovery
            # Quarantine opaque payload bytes; do not silent-gap-fill.
            self.quarantine_corrupt(
                content_hash=c_hash,
                reason=f"partial_failure:{type(exc).__name__}:{exc}",
                blob=json.dumps({"payload": payload}, sort_keys=True).encode("utf-8"),
            )
            self.counters.partial_failure_recovered_count += 1
            self.checkpoint.write(
                symbol=symbol,
                exchange_timestamp=exchange_timestamp,
                content_hash=c_hash,
                source_offset=source_offset,
                data_class=data_class,
                mode=mode,
            )
            return {
                "status": "PARTIAL_FAILURE_RECOVERED",
                "content_hash": c_hash,
                "error": str(exc),
                "data_class": data_class,
            }

        bronze_status = wired["bronze"]["status"]
        if bronze_status == "DUPLICATE":
            self.counters.duplicate_resolved_count += 1
            status = "DUPLICATE"
        elif bronze_status == "INGESTED":
            self._seen_hashes.add(c_hash)
            self.counters.ingested_count += 1
            if mode == "live_append":
                self.counters.live_append_count += 1
            if mode == "backfill":
                self.counters.backfill_batch_count += 1
            status = "INGESTED"
        else:
            # Unexpected bronze status — count as unresolved duplicate risk if unknown
            self.counters.duplicate_unresolved_count += 1
            status = str(bronze_status)

        self.counters.bump_class(data_class)
        self.manifest.append(
            exchange_timestamp=exchange_timestamp,
            content_hash=c_hash,
            symbol=symbol,
            source_id=source_id,
            data_class=data_class,
            status=status,
            extra={"license_bound": license_bind.get("bound"), "mode": mode},
        )
        self.checkpoint.write(
            symbol=symbol,
            exchange_timestamp=exchange_timestamp,
            content_hash=c_hash,
            source_offset=source_offset,
            data_class=data_class,
            mode=mode,
        )
        self.rate_limit.record_weight(1)
        return {
            "status": status,
            "content_hash": c_hash,
            "wired": wired,
            "data_class": data_class,
            "mode": mode,
            "license_bound": True,
        }

    def run_batches(
        self,
        batches: list[dict[str, Any]],
        *,
        mode: str,
        resume: bool = True,
        pit_kind: str = "OBSERVATION",
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        start = self.checkpoint.resume_offset() if resume else 0
        results: list[dict[str, Any]] = []
        for i, batch in enumerate(batches):
            if i < start:
                continue
            results.append(
                self.ingest_one(
                    batch,
                    source_offset=i,
                    mode=mode,
                    pit_kind=pit_kind,
                    now_ms=now_ms,
                )
            )
        return {
            "mode": mode,
            "started_at_offset": start,
            "processed": len(results),
            "results": results,
            "checkpoint": self.checkpoint.read(),
            "counters": self.counters.to_dict(),
        }

    def incremental_backfill(self, *, window_days: int = 7, resume: bool = True) -> dict[str, Any]:
        if int(window_days) not in ALLOWED_BACKFILL_WINDOWS_DAYS:
            raise ValueError(f"backfill_window_refused:{window_days}")
        batches = fixture_batches() + official_historical_sample_batches(window_days=window_days)
        report = self.run_batches(batches, mode="backfill", resume=resume, pit_kind="BACKFILL")
        report["window_days"] = int(window_days)
        report["priority_symbols"] = list(PRIORITY_SYMBOLS)
        return report

    def live_append(self, *, resume: bool = True, now_ms: int | None = None) -> dict[str, Any]:
        batches = live_append_batches()
        # Continue offsets after prior backfill by using absolute offsets from checkpoint.
        # Live batches are appended as a fresh sequence starting at current resume offset index
        # mapped onto these batches (0..n) when resume=False for the live segment.
        start_base = self.checkpoint.resume_offset() if resume else 0
        results: list[dict[str, Any]] = []
        for i, batch in enumerate(batches):
            offset = start_base + i
            results.append(
                self.ingest_one(
                    batch,
                    source_offset=offset,
                    mode="live_append",
                    pit_kind="OBSERVATION",
                    now_ms=now_ms,
                )
            )
        return {
            "mode": "live_append",
            "started_at_offset": start_base,
            "processed": len(results),
            "results": results,
            "checkpoint": self.checkpoint.read(),
            "counters": self.counters.to_dict(),
        }

    def apply_retention(self) -> dict[str, Any]:
        pruned = self.retention.prune_partition_index(self.manifest.partitions())
        self.manifest.replace_index(pruned["kept"])
        self.counters.retention_prune_count += int(pruned["pruned_partition_count"])
        return pruned

    def pause_on_rate_limit(self, *, http_status: int = 429) -> dict[str, Any]:
        self.rate_limit.observe_http_status(http_status)
        if self.rate_limit.paused:
            self.counters.rate_limit_pause_count += 1
        return self.rate_limit.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "priority_symbols": list(PRIORITY_SYMBOLS),
            "partitions": self.manifest.partitions(),
            "manifest_digest": self.manifest.digest(),
            "checkpoint": self.checkpoint.read(),
            "counters": self.counters.to_dict(),
            "rate_limit": self.rate_limit.snapshot(),
            "disk_usage_bytes": self.quota.usage_bytes(),
            "acceptance_zeros": self.counters.zero_snapshot(),
            "acceptance_zeros_ok": self.counters.acceptance_zeros_ok(),
            "non_ingest_classes": sorted(NON_INGEST_DATA_CLASSES),
            "stale_probe": DATA_CLASS_STALE,
            "degraded_probe": DATA_CLASS_DEGRADED,
            "unavailable_probe": DATA_CLASS_UNAVAILABLE,
        }
