"""Inventory legally accessible in-repo sources and document RO public endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_dev_data_foundation.constants import (
    IN_REPO_SOURCE_SPECS,
    INVENTORY_SCHEMA,
    PUBLIC_RO_ENDPOINTS,
)
from backend.nexus_dev_data_foundation.hashing import ms_to_iso, sha_file, sha_obj, utc_now_iso
from backend.nexus_dev_data_foundation.partitions import build_time_partitions, classify_timestamp
from backend.nexus_dev_data_foundation.records import build_record


def _infer_availability_ms(path: Path, payload: Any) -> int | None:
    if isinstance(payload, dict):
        for key in ("availability_ms", "observation_ms", "time", "start_ms", "historical_start"):
            if key in payload and payload[key] is not None:
                try:
                    return int(payload[key])
                except (TypeError, ValueError):
                    pass
        # Fixture index: use earliest snapshot availability
        snaps = payload.get("snapshots")
        if isinstance(snaps, list) and snaps:
            vals = [int(s["availability_ms"]) for s in snaps if "availability_ms" in s]
            if vals:
                return min(vals)
        result = payload.get("result")
        if isinstance(result, dict):
            rows = result.get("list")
            if isinstance(rows, list) and rows and isinstance(rows[0], list) and rows[0]:
                try:
                    return int(rows[0][0])
                except (TypeError, ValueError, IndexError):
                    pass
    # Fall back to none — do not invent
    return None


def _source_timestamp_from_payload(payload: Any, availability_ms: int | None) -> str | None:
    if isinstance(payload, dict) and "time" in payload:
        try:
            return ms_to_iso(int(payload["time"]))
        except (TypeError, ValueError):
            pass
    return ms_to_iso(availability_ms)


def inventory_in_repo_sources(root: Path) -> dict[str, Any]:
    retrieval = utc_now_iso()
    partitions = build_time_partitions()
    records: list[dict[str, Any]] = []
    missing_paths: list[str] = []

    for spec in IN_REPO_SOURCE_SPECS:
        rel = spec["path"]
        path = root / rel
        source_id = spec["source_id"]
        kind = spec["kind"]

        if not path.is_file():
            missing_paths.append(rel)
            # Honest MISSING record — do not invent content
            rec = build_record(
                source_id=source_id,
                source_kind=kind,
                source_path=rel,
                source_timestamp=None,
                availability_ms=None,
                content_checksum=sha_obj({"missing": rel}),
                availability_state="MISSING",
                partition_id=None,
                partition_category="DEVELOPMENT",
                missing_state="FILE_ABSENT",
                retrieval_timestamp=retrieval,
                notes="Source path not present; history not invented",
                allow_oos_catalog_only=False,
            )
            # Consumed marker may be missing in some checkouts — still catalog
            if "consumed" in source_id:
                rec = build_record(
                    source_id=source_id,
                    source_kind=kind,
                    source_path=rel,
                    source_timestamp=None,
                    availability_ms=None,
                    content_checksum=sha_obj({"missing": rel}),
                    availability_state="MISSING",
                    partition_id="H3_CONSUMED_FAILED_HOLDOUT",
                    partition_category="CONSUMED_FORBIDDEN",
                    missing_state="FILE_ABSENT",
                    retrieval_timestamp=retrieval,
                    notes="Consumed holdout marker absent in this checkout",
                    allow_oos_catalog_only=True,
                )
            records.append(rec)
            continue

        raw = path.read_bytes()
        checksum = sha_file(path)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None

        availability_ms = _infer_availability_ms(path, payload) if payload is not None else None
        category = classify_timestamp(availability_ms, partitions) if availability_ms is not None else "DEVELOPMENT"
        partition_id = None
        for p in partitions["partitions"]:
            if availability_ms is not None and int(p["start_ms"]) <= availability_ms <= int(p["end_ms"]):
                partition_id = p["partition_id"]
                category = p["category"]
                break
        if category == "CONSUMED_FORBIDDEN":
            partition_id = "H3_CONSUMED_FAILED_HOLDOUT"

        # Classify availability honestly
        if kind == "historical_manifest_metadata":
            availability_state = "METADATA_ONLY"
            missing_state = "RAW_BARS_NOT_IN_GIT"
            notes = "Manifest present; raw historical bars gitignored - not fabricated"
            # Manifest spans DEV window — bind to DEVELOPMENT for catalog purposes
            partition_id = "DEV_EXPLORATION_PRIMARY"
            category = "DEVELOPMENT"
        elif kind == "consumed_holdout_registry":
            availability_state = "CONSUMED_FORBIDDEN"
            missing_state = "NOT_MISSING"
            notes = "Consumed failed OOS/holdout — catalog only, never reload for development"
            partition_id = "H3_CONSUMED_FAILED_HOLDOUT"
            category = "CONSUMED_FORBIDDEN"
        elif kind == "public_ro_fixture_sample":
            availability_state = "AVAILABLE"
            missing_state = "SAMPLE_ONLY_NOT_FULL_HISTORY"
            notes = "Small public-API-shape fixture sample - not full market history"
            if category in {
                "OOS_RESERVED",
                "OOS_UNTOUCHED",
                "OUTSIDE_SEALED_PARTITIONS",
                "CONSUMED_FORBIDDEN",
            }:
                # Sample timestamps may sit outside DEV; catalog under DEVELOPMENT as fixture evidence class
                partition_id = "DEV_EXPLORATION_PRIMARY"
                category = "DEVELOPMENT"
        else:
            availability_state = "AVAILABLE"
            missing_state = "NOT_MISSING"
            notes = (
                "Sanitized PIT fixture - never substitute later era for earlier as_of"
            )
            if category in {
                "OOS_RESERVED",
                "OOS_UNTOUCHED",
                "OUTSIDE_SEALED_PARTITIONS",
                "CONSUMED_FORBIDDEN",
            }:
                # Universe eras are PIT control fixtures, not the consumed holdout
                # evaluation interval. Calendar overlap with consumed holdout must
                # not ban sanitized fixtures from development catalog use.
                partition_id = "DEV_EXPLORATION_PRIMARY"
                category = "DEVELOPMENT"

        summary: dict[str, Any] = {
            "bytes": len(raw),
            "legal_basis": spec["legal_basis"],
            "loaded_for_development": category == "DEVELOPMENT" and kind != "consumed_holdout_registry",
        }
        if isinstance(payload, dict):
            if "instruments" in payload:
                summary["instrument_count"] = len(payload.get("instruments") or [])
            if "historical_record_count" in payload:
                summary["historical_record_count"] = payload.get("historical_record_count")
            if "historical_dataset_checksum" in payload:
                summary["historical_dataset_checksum"] = payload.get("historical_dataset_checksum")
            if "eligible_historical_symbol_count" in payload:
                summary["eligible_historical_symbol_count"] = payload.get(
                    "eligible_historical_symbol_count"
                )

        allow_oos = category in {"OOS_RESERVED", "OOS_UNTOUCHED", "CONSUMED_FORBIDDEN"}
        rec = build_record(
            source_id=source_id,
            source_kind=kind,
            source_path=rel.replace("\\", "/"),
            source_timestamp=_source_timestamp_from_payload(payload, availability_ms),
            availability_ms=availability_ms,
            content_checksum=checksum,
            availability_state=availability_state,
            partition_id=partition_id,
            partition_category=category,
            missing_state=missing_state,
            retrieval_timestamp=retrieval,
            notes=notes,
            payload_summary=summary,
            allow_oos_catalog_only=allow_oos,
        )
        records.append(rec)

    # Document RO public endpoints without inventing historical payloads
    endpoint_docs: list[dict[str, Any]] = []
    for ep in PUBLIC_RO_ENDPOINTS:
        endpoint_docs.append(
            {
                "source_id": ep["source_id"],
                "kind": ep["kind"],
                "url": ep["url"],
                "legal_basis": ep["legal_basis"],
                "retrieval_timestamp": retrieval,
                "availability_state": "UNSUPPORTED",
                "missing_state": "NO_LIVE_FETCH_IN_LANE_BY_DEFAULT",
                "notes": "Documented read-only public endpoint; lane defaults to in-repo fixtures "
                "for reproducible PIT. Optional probe may confirm reachability without persisting "
                "invented history.",
                "invented_history": False,
                "oos_consumed": False,
                "exchange_write": False,
            }
        )
        records.append(
            build_record(
                source_id=ep["source_id"],
                source_kind=ep["kind"],
                source_path=ep["url"],
                source_timestamp=None,
                availability_ms=None,
                content_checksum=sha_obj({"endpoint": ep["url"], "documented": True}),
                availability_state="UNSUPPORTED",
                partition_id=None,
                partition_category="DEVELOPMENT",
                missing_state="NO_LIVE_FETCH_IN_LANE_BY_DEFAULT",
                retrieval_timestamp=retrieval,
                notes="Endpoint documented only; no fabricated klines",
                payload_summary={"legal_basis": ep["legal_basis"], "loaded_for_development": False},
            )
        )

    # Seal every partition category as a catalog entry (OOS never loaded).
    for p in partitions["partitions"]:
        cat = p["category"]
        if cat in {"OOS_RESERVED", "OOS_UNTOUCHED"}:
            availability_state = "RESERVED_UNTOUCHED"
            missing_state = "NOT_LOADED_BY_DESIGN"
            allow_oos = True
            loaded = False
        elif cat == "VALIDATION_PLANNING":
            availability_state = "AVAILABLE"
            missing_state = "PARTITION_SEAL_ONLY"
            allow_oos = False
            loaded = False
        else:
            availability_state = "AVAILABLE"
            missing_state = "PARTITION_SEAL_ONLY"
            allow_oos = False
            loaded = False
        records.append(
            build_record(
                source_id=f"partition_seal_{p['partition_id'].lower()}",
                source_kind="partition_seal",
                source_path=None,
                source_timestamp=p["start_utc"],
                availability_ms=p["start_ms"],
                content_checksum=sha_obj(
                    {
                        "partition_id": p["partition_id"],
                        "start_ms": p["start_ms"],
                        "end_ms": p["end_ms"],
                    }
                ),
                availability_state=availability_state,
                partition_id=p["partition_id"],
                partition_category=cat,
                missing_state=missing_state,
                retrieval_timestamp=retrieval,
                notes=str(p["notes"]).replace("\u2014", "-"),
                payload_summary={"loaded_for_development": loaded, "seal": True},
                allow_oos_catalog_only=allow_oos,
            )
        )

    inventory = {
        "schema": INVENTORY_SCHEMA,
        "retrieval_timestamp": retrieval,
        "in_repo_source_count": len(IN_REPO_SOURCE_SPECS),
        "public_endpoint_doc_count": len(PUBLIC_RO_ENDPOINTS),
        "record_count": len(records),
        "missing_path_count": len(missing_paths),
        "missing_paths": missing_paths,
        "records": records,
        "endpoint_docs": endpoint_docs,
        "partition_checksum": partitions["partition_checksum"],
        "oos_consumed": False,
        "invented_history_count": 0,
        "inventory_checksum": "",
    }
    inventory["inventory_checksum"] = sha_obj(
        {
            "record_ids": [r["record_id"] for r in records],
            "checksums": [r["content_checksum"] for r in records],
            "missing_paths": missing_paths,
        }
    )
    return inventory
