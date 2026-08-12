"""Immutable experiment record construction and verification."""
from __future__ import annotations

from typing import Any

from backend.nexus_experiment_registry.constants import (
    HARD_BAN_FLAGS,
    IDENTITY_FIELDS,
    INTERVAL_CATEGORIES,
    RECORD_SCHEMA,
    REQUIRED_RECORD_KEYS,
    SCHEMA_VERSION,
)
from backend.nexus_experiment_registry.hashing import sha256_hex


class ExperimentRecordError(ValueError):
    """Fail-closed experiment record error."""


def _normalize_intervals(intervals: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not intervals:
        raise ExperimentRecordError("time_intervals_required")
    out: list[dict[str, Any]] = []
    for raw in intervals:
        if not isinstance(raw, dict):
            raise ExperimentRecordError("time_interval_not_dict")
        iid = str(raw.get("interval_id") or "").strip()
        category = str(raw.get("category") or "").strip()
        if not iid:
            raise ExperimentRecordError("interval_id_missing")
        if category not in INTERVAL_CATEGORIES:
            raise ExperimentRecordError(f"interval_category_invalid:{category}")
        try:
            start_ms = int(raw["start_ms"])
            end_ms = int(raw["end_ms"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ExperimentRecordError("interval_bounds_invalid") from exc
        if end_ms < start_ms:
            raise ExperimentRecordError(f"interval_inverted:{iid}")
        out.append(
            {
                "interval_id": iid,
                "label": str(raw.get("label") or iid),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "category": category,
            }
        )
    out.sort(key=lambda x: (x["start_ms"], x["interval_id"]))
    return out


def _normalize_lineage(lineage: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(lineage, dict) or not lineage:
        raise ExperimentRecordError("data_lineage_required")
    source_ids = list(lineage.get("source_ids") or [])
    if not source_ids:
        raise ExperimentRecordError("data_lineage_source_ids_required")
    as_of_ms = lineage.get("as_of_ms")
    if as_of_ms is None:
        raise ExperimentRecordError("data_lineage_as_of_ms_required")
    try:
        as_of_ms_i = int(as_of_ms)
    except (TypeError, ValueError) as exc:
        raise ExperimentRecordError("data_lineage_as_of_ms_invalid") from exc
    return {
        "source_ids": sorted(str(s) for s in source_ids),
        "as_of_ms": as_of_ms_i,
        "pit_bound": bool(lineage.get("pit_bound", True)),
        "capture_campaign_id": lineage.get("capture_campaign_id"),
        "notes": lineage.get("notes"),
    }


def _normalize_seeds(seeds: dict[str, Any] | list[Any] | int | str | None) -> dict[str, Any]:
    if seeds is None:
        raise ExperimentRecordError("seeds_required")
    if isinstance(seeds, dict):
        if not seeds:
            raise ExperimentRecordError("seeds_empty")
        return {str(k): seeds[k] for k in sorted(seeds, key=str)}
    if isinstance(seeds, list):
        if not seeds:
            raise ExperimentRecordError("seeds_empty")
        return {"seed_list": list(seeds)}
    return {"primary": seeds}


def _normalize_result_hashes(result_hashes: dict[str, str] | None) -> dict[str, str]:
    if not isinstance(result_hashes, dict) or not result_hashes:
        raise ExperimentRecordError("result_hashes_required")
    out: dict[str, str] = {}
    for k, v in result_hashes.items():
        hs = str(v)
        if len(hs) != 64 or any(c not in "0123456789abcdef" for c in hs.lower()):
            raise ExperimentRecordError(f"result_hash_invalid:{k}")
        out[str(k)] = hs.lower()
    return {k: out[k] for k in sorted(out)}


def identity_payload(fields: dict[str, Any]) -> dict[str, Any]:
    return {k: fields[k] for k in IDENTITY_FIELDS}


def compute_identity_fingerprint(fields: dict[str, Any]) -> str:
    return sha256_hex(identity_payload(fields))


def compute_record_hash(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "record_hash"}
    return sha256_hex(body)


def build_experiment_record(
    *,
    experiment_id: str,
    mechanism_semantic_id: str,
    data_lineage: dict[str, Any],
    universe_checksum: str,
    feature_version: str,
    code_checksum: str,
    parameter_checksum: str,
    cost_version: str,
    risk_version: str,
    execution_version: str,
    time_intervals: list[dict[str, Any]],
    development_only: bool,
    oos_consumed: bool,
    seeds: dict[str, Any] | list[Any] | int | str,
    result_hashes: dict[str, str],
    parent_experiment: str | None = None,
    registered_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a sealed, fail-closed experiment registry record."""
    eid = str(experiment_id or "").strip()
    mech = str(mechanism_semantic_id or "").strip()
    if not eid:
        raise ExperimentRecordError("experiment_id_required")
    if not mech:
        raise ExperimentRecordError("mechanism_semantic_id_required")
    if not universe_checksum or len(str(universe_checksum)) != 64:
        raise ExperimentRecordError("universe_checksum_invalid")
    if not code_checksum:
        raise ExperimentRecordError("code_checksum_required")
    if not parameter_checksum or len(str(parameter_checksum)) != 64:
        raise ExperimentRecordError("parameter_checksum_invalid")
    if not feature_version:
        raise ExperimentRecordError("feature_version_required")
    if not cost_version:
        raise ExperimentRecordError("cost_version_required")
    if not risk_version:
        raise ExperimentRecordError("risk_version_required")
    if not execution_version:
        raise ExperimentRecordError("execution_version_required")
    if not isinstance(development_only, bool):
        raise ExperimentRecordError("development_only_must_be_bool")
    if not isinstance(oos_consumed, bool):
        raise ExperimentRecordError("oos_consumed_must_be_bool")
    # Hard ban: real OOS consumption is forbidden in this research registry lane.
    if oos_consumed:
        raise ExperimentRecordError("oos_consumed_forbidden_by_hard_ban")

    lineage = _normalize_lineage(data_lineage)
    intervals = _normalize_intervals(time_intervals)
    # OOS intervals may be reserved but must not be marked consumed.
    oos_intervals = [i for i in intervals if i["category"] == "oos"]
    if oos_intervals and oos_consumed:
        raise ExperimentRecordError("oos_interval_consumed_forbidden")

    seed_map = _normalize_seeds(seeds)
    results = _normalize_result_hashes(result_hashes)

    core = {
        "mechanism_semantic_id": mech,
        "data_lineage": lineage,
        "universe_checksum": str(universe_checksum).lower(),
        "feature_version": str(feature_version),
        "code_checksum": str(code_checksum),
        "parameter_checksum": str(parameter_checksum).lower(),
        "cost_version": str(cost_version),
        "risk_version": str(risk_version),
        "execution_version": str(execution_version),
        "time_intervals": intervals,
        "development_only": development_only,
        "seeds": seed_map,
    }
    identity_fp = compute_identity_fingerprint(core)

    record: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "experiment_id": eid,
        **core,
        "oos_consumed": False,
        "result_hashes": results,
        "parent_experiment": parent_experiment,
        "identity_fingerprint": identity_fp,
        "registered_at": registered_at,
        **HARD_BAN_FLAGS,
    }
    if extra:
        # Extra metadata must not silently override sealed identity keys.
        for k, v in extra.items():
            if k in record:
                raise ExperimentRecordError(f"extra_overrides_sealed_key:{k}")
            record[k] = v
    record["record_hash"] = compute_record_hash(record)
    return record


def verify_experiment_record(record: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed verification of a sealed experiment record."""
    if not isinstance(record, dict):
        raise ExperimentRecordError("record_not_dict")
    missing = [k for k in REQUIRED_RECORD_KEYS if k not in record]
    if missing:
        raise ExperimentRecordError(f"record_missing_keys:{missing}")
    if record.get("schema") != RECORD_SCHEMA:
        raise ExperimentRecordError(f"schema_mismatch:{record.get('schema')}")
    if record.get("simulated_only") is not True:
        raise ExperimentRecordError("simulated_only_required")
    for ban_key in (
        "exchange_write",
        "demo_order",
        "shadow_order",
        "learning_claim",
        "profitability_claim",
        "formal_walk_forward_executed",
        "oos_executed",
        "mainnet",
        "real_money",
    ):
        if record.get(ban_key) is not False:
            raise ExperimentRecordError(f"hard_ban_violated:{ban_key}")
    if record.get("oos_consumed") is not False:
        raise ExperimentRecordError("oos_consumed_must_be_false")

    core = {k: record[k] for k in IDENTITY_FIELDS}
    expected_fp = compute_identity_fingerprint(core)
    if record.get("identity_fingerprint") != expected_fp:
        raise ExperimentRecordError("identity_fingerprint_mismatch")
    expected_hash = compute_record_hash(record)
    if record.get("record_hash") != expected_hash:
        raise ExperimentRecordError("record_hash_mismatch")

    # Re-validate nested shapes.
    _normalize_lineage(record["data_lineage"])
    _normalize_intervals(record["time_intervals"])
    _normalize_seeds(record["seeds"])
    _normalize_result_hashes(record["result_hashes"])

    return {
        "ok": True,
        "experiment_id": record["experiment_id"],
        "identity_fingerprint": record["identity_fingerprint"],
        "record_hash": record["record_hash"],
        "development_only": record["development_only"],
        "oos_consumed": record["oos_consumed"],
    }
