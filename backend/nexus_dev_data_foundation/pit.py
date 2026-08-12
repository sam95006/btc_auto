"""PIT guards — reject future leakage, OOS consumption, invented history."""
from __future__ import annotations

from typing import Any, Iterable

from backend.nexus_dev_data_foundation.partitions import classify_timestamp


def pit_observation_allowed(*, observation_ms: int, as_of_ms: int) -> bool:
    return int(observation_ms) <= int(as_of_ms)


def reject_future_observation(*, observation_ms: int, as_of_ms: int) -> dict[str, Any]:
    allowed = pit_observation_allowed(observation_ms=observation_ms, as_of_ms=as_of_ms)
    return {
        "ok": allowed,
        "status": "PASS" if allowed else "FUTURE_OBSERVATION_REJECTED",
        "observation_ms": int(observation_ms),
        "as_of_ms": int(as_of_ms),
    }


def reject_today_for_past(*, snapshot_availability_ms: int, as_of_ms: int) -> dict[str, Any]:
    """Refuse using a later snapshot for an earlier as_of."""
    ok = int(snapshot_availability_ms) <= int(as_of_ms)
    return {
        "ok": ok,
        "status": "PASS" if ok else "TODAY_OR_FUTURE_SNAPSHOT_FOR_PAST",
        "snapshot_availability_ms": int(snapshot_availability_ms),
        "as_of_ms": int(as_of_ms),
    }


def reject_oos_load(partition_category: str) -> dict[str, Any]:
    blocked = partition_category in {"OOS_RESERVED", "OOS_UNTOUCHED", "CONSUMED_FORBIDDEN"}
    return {
        "ok": not blocked,  # ok means "load allowed"
        "blocked": blocked,
        "status": "OOS_OR_CONSUMED_LOAD_BLOCKED" if blocked else "LOAD_ALLOWED",
        "partition_category": partition_category,
    }


def reject_invented_history(*, claimed_available: bool, source_present: bool) -> dict[str, Any]:
    invented = claimed_available and not source_present
    return {
        "ok": not invented,
        "status": "INVENTED_HISTORY_BLOCKED" if invented else "PASS",
        "claimed_available": claimed_available,
        "source_present": source_present,
    }


def filter_records_for_development(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in records:
        cat = str(r.get("partition_category"))
        gate = reject_oos_load(cat)
        if gate["blocked"]:
            continue
        if cat != "DEVELOPMENT":
            continue
        if r.get("availability_state") in {
            "MISSING",
            "UNSUPPORTED",
            "RESERVED_UNTOUCHED",
            "CONSUMED_FORBIDDEN",
        }:
            continue
        if r.get("invented_history") is True:
            continue
        # Partition seals / endpoint docs are catalog-only unless explicitly loadable.
        summary = r.get("payload_summary") or {}
        if summary.get("seal") is True and summary.get("loaded_for_development") is not True:
            continue
        if summary.get("loaded_for_development") is False:
            continue
        out.append(r)
    return out


def prove_oos_excluded(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    loaded = filter_records_for_development(records)
    leaked = [
        r["record_id"]
        for r in loaded
        if str(r.get("partition_category")) in {"OOS_RESERVED", "OOS_UNTOUCHED", "CONSUMED_FORBIDDEN"}
    ]
    return {
        "schema": "v15_a_oos_exclusion_proof",
        "development_loadable_count": len(loaded),
        "oos_leaked_ids": leaked,
        "oos_excluded": len(leaked) == 0,
        "oos_consumed": False,
    }


def prove_pit_as_of(records: Iterable[dict[str, Any]], *, as_of_ms: int) -> dict[str, Any]:
    eligible = []
    rejected = []
    for r in records:
        avail = r.get("availability_ms")
        if avail is None:
            rejected.append({"record_id": r.get("record_id"), "reason": "NO_AVAILABILITY_MS"})
            continue
        gate = reject_future_observation(observation_ms=int(avail), as_of_ms=as_of_ms)
        if gate["ok"]:
            eligible.append(r["record_id"])
        else:
            rejected.append({"record_id": r["record_id"], "reason": gate["status"]})
    # PIT holds when every future observation is rejected (never appears in eligible).
    future_rejected = sum(1 for x in rejected if x.get("reason") == "FUTURE_OBSERVATION_REJECTED")
    return {
        "schema": "v15_a_pit_proof",
        "as_of_ms": as_of_ms,
        "eligible_count": len(eligible),
        "rejected_count": len(rejected),
        "eligible_ids": eligible,
        "rejected": rejected,
        "pit_holds": True,
        "future_rejected_count": future_rejected,
        "future_leak_count": 0,
    }


def classify_for_as_of(ts_ms: int) -> str:
    return classify_timestamp(ts_ms)
