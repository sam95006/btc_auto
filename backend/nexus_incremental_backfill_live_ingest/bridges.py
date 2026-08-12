"""Wire V18 ingest events into V17 Bronze / Silver / PIT."""
from __future__ import annotations

from typing import Any

from backend.nexus_bronze_immutable_raw_lake.lake import BronzeLake
from backend.nexus_incremental_backfill_live_ingest.constants import BRONZE_CLASS_MAP, INGESTIBLE_DATA_CLASSES
from backend.nexus_incremental_backfill_live_ingest.hashing import content_hash_of, parse_utc_z_ms, utc_now_ms
from backend.nexus_incremental_backfill_live_ingest.samples import instrument_observation
from backend.nexus_pit_revision_v17.store import PitRevisionStore
from backend.nexus_pit_revision_v17.types import DualTimeStamp, RevisionRecord
from backend.nexus_silver_symbol_identity.normalize import normalize_raw_instrument


class LayerBridge:
    """Fan-in bridge: Bronze append + Silver identity + PIT revision."""

    def __init__(
        self,
        *,
        bronze: BronzeLake,
        pit: PitRevisionStore | None = None,
    ) -> None:
        self.bronze = bronze
        self.pit = pit or PitRevisionStore()
        self._silver_cache: dict[str, dict[str, Any]] = {}

    def bronze_classification(self, data_class: str) -> str:
        if data_class not in INGESTIBLE_DATA_CLASSES:
            raise ValueError(f"non_ingestible_data_class:{data_class}")
        mapped = BRONZE_CLASS_MAP.get(data_class)
        if not mapped:
            raise ValueError(f"bronze_map_missing:{data_class}")
        return mapped

    def to_silver(self, symbol: str) -> dict[str, Any]:
        if symbol in self._silver_cache:
            return self._silver_cache[symbol]
        rec = normalize_raw_instrument(instrument_observation(symbol))
        self._silver_cache[symbol] = rec
        return rec

    def to_pit(
        self,
        *,
        symbol: str,
        exchange_timestamp: str,
        received_timestamp: str,
        payload: Any,
        data_class: str,
        kind: str = "OBSERVATION",
    ) -> RevisionRecord:
        event_ms = parse_utc_z_ms(exchange_timestamp)
        avail_ms = parse_utc_z_ms(received_timestamp)
        ingest_ms = max(avail_ms, utc_now_ms())
        # Ensure axis ordering for DualTimeStamp.validate
        if avail_ms < event_ms:
            avail_ms = event_ms
        if ingest_ms < avail_ms:
            ingest_ms = avail_ms
        c_hash = content_hash_of(payload)
        record = RevisionRecord(
            revision_id=f"v18b:{symbol}:{c_hash[:24]}",
            series_id=f"kline:{symbol}:1m",
            kind=kind,
            value={
                "payload": payload,
                "data_class": data_class,
                "symbol": symbol,
            },
            times=DualTimeStamp(
                event_time=event_ms,
                available_time=avail_ms,
                revision_time=avail_ms,
                ingest_time=ingest_ms,
            ),
            content_hash=c_hash,
            fixture_only=(data_class == "FIXTURE"),
            notes="v18b_bridge",
            tags=("v18b", data_class),
        )
        # Dedup by revision_id — if already present, return existing.
        existing = self.pit.get(record.revision_id)
        if existing is not None:
            return existing
        return self.pit.ingest(record)

    def ingest_event(
        self,
        *,
        exchange_timestamp: str,
        received_timestamp: str,
        source_id: str,
        symbol_original: str,
        payload: Any,
        data_class: str,
        license_reference: str,
        source_offset: int | None = None,
        pit_kind: str = "OBSERVATION",
    ) -> dict[str, Any]:
        bronze_class = self.bronze_classification(data_class)
        bronze_result = self.bronze.ingest(
            exchange_timestamp=exchange_timestamp,
            received_timestamp=received_timestamp,
            source_id=source_id,
            symbol_original=symbol_original,
            payload=payload,
            classification=bronze_class,
            license_reference=license_reference,
            source_offset=source_offset,
        )
        silver = self.to_silver(symbol_original)
        pit_rec = None
        if bronze_result.get("status") == "INGESTED":
            pit_rec = self.to_pit(
                symbol=symbol_original,
                exchange_timestamp=exchange_timestamp,
                received_timestamp=received_timestamp,
                payload=payload,
                data_class=data_class,
                kind=pit_kind,
            )
        return {
            "bronze": bronze_result,
            "silver": {
                "canonical_instrument_id": silver.get("canonical_instrument_id"),
                "exchange_symbol": silver.get("exchange_symbol"),
                "status": silver.get("status"),
            },
            "pit": None
            if pit_rec is None
            else {
                "revision_id": pit_rec.revision_id,
                "series_id": pit_rec.series_id,
                "kind": pit_rec.kind,
                "content_hash": pit_rec.content_hash,
            },
            "data_class": data_class,
            "bronze_classification": bronze_class,
        }
