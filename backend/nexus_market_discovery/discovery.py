"""Point-in-Time dynamic market universe discovery orchestrator."""
from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from backend.nexus_market_discovery.constants import (
    DEFAULT_THRESHOLDS,
    DISCOVERY_SCHEMA,
    EVALUATION_DIMENSIONS,
    HARD_BANS,
    UNIVERSE_ID,
)
from backend.nexus_market_discovery.evaluator import evaluate_instrument
from backend.nexus_market_discovery.fixtures import (
    PitSnapshotError,
    select_snapshot_for_as_of,
)
from backend.nexus_market_discovery.lineage import (
    build_lineage,
    sha_obj,
    universe_checksum,
    utc_now_iso,
)


class PitDiscoveryError(ValueError):
    """Fail-closed discovery errors (today-for-past, live injection, etc.)."""


def _git_head(repo_root: Path | None) -> str:
    if repo_root is None:
        return "UNKNOWN"
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def assert_not_today_for_past(
    *,
    as_of_ms: int,
    snapshot_availability_ms: int,
    source_kind: str,
    now_ms: int | None = None,
) -> None:
    """HARD BAN: never use today's (or any later) universe to simulate the past."""
    if source_kind != "sanitized_fixture":
        raise PitDiscoveryError(f"unsupported_source_kind:{source_kind}:fixtures_only_for_pit")
    if int(snapshot_availability_ms) > int(as_of_ms):
        raise PitDiscoveryError("today_or_future_universe_used_for_past_as_of")
    if now_ms is not None and int(as_of_ms) < int(now_ms):
        # Historical query must not be answered by a live-era snapshot
        # (availability within 24h of now while as_of is older than 24h).
        day_ms = 86_400_000
        if int(now_ms) - int(as_of_ms) > day_ms and int(now_ms) - int(snapshot_availability_ms) < day_ms:
            raise PitDiscoveryError("live_today_snapshot_rejected_for_historical_as_of")


def discover_universe(
    as_of_ms: int,
    *,
    fixtures_dir: Path | None = None,
    thresholds: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    retrieval_timestamp: str | None = None,
    now_ms: int | None = None,
    reject_live_injection: bool = True,
) -> dict[str, Any]:
    """Discover eligible/rejected PIT universe as of as_of_ms.

    Uses sanitized historical fixtures only. Refuses live/today injection for
    historical as_of timestamps.
    """
    as_of_ms = int(as_of_ms)
    retrieval_timestamp = retrieval_timestamp or utc_now_iso()
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    thresholds_checksum = sha_obj(th)

    try:
        snapshot = select_snapshot_for_as_of(as_of_ms, fixtures_dir=fixtures_dir)
    except PitSnapshotError as exc:
        raise PitDiscoveryError(str(exc)) from exc

    assert_not_today_for_past(
        as_of_ms=as_of_ms,
        snapshot_availability_ms=int(snapshot["availability_ms"]),
        source_kind=str(snapshot.get("source_kind") or ""),
        now_ms=now_ms,
    )

    if reject_live_injection:
        # Guard: snapshot must declare fixture source and no trading writes
        if snapshot.get("trading_write") or snapshot.get("demo") or snapshot.get("real_money"):
            raise PitDiscoveryError("live_or_trading_snapshot_rejected")
        if str(snapshot.get("source_kind")) != "sanitized_fixture":
            raise PitDiscoveryError("non_fixture_source_rejected")

    evaluations = []
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()

    for row in snapshot.get("instruments") or []:
        ev = evaluate_instrument(row, as_of_ms=as_of_ms, thresholds=th)
        payload = ev.to_dict()
        payload["contract_specification"] = row.get("contract_specification")
        payload["metrics"] = {
            "liquidity_score": row.get("liquidity_score"),
            "turnover_usdt": row.get("turnover_usdt"),
            "volume_usdt": row.get("volume_usdt"),
            "spread_bps": row.get("spread_bps"),
            "depth_usdt": row.get("depth_usdt"),
            "open_interest_usdt": row.get("open_interest_usdt"),
            "funding_available": row.get("funding_available"),
            "data_completeness": row.get("data_completeness"),
            "staleness_ms": row.get("staleness_ms"),
            "symbol_mapping": row.get("symbol_mapping"),
            "tick_size": row.get("tick_size"),
            "qty_step": row.get("qty_step"),
            "minimum_notional": row.get("minimum_notional"),
        }
        evaluations.append(payload)
        if ev.eligible:
            eligible.append(payload)
        else:
            rejected.append(payload)
            for r in ev.rejection_reasons:
                reason_counts[r] += 1

    eligible_symbols = sorted(e["symbol"] for e in eligible)
    rejected_symbols = sorted(r["symbol"] for r in rejected)
    uni_ck = universe_checksum(
        as_of_ms=as_of_ms,
        eligible_symbols=eligible_symbols,
        rejected_symbols=rejected_symbols,
    )
    code_version = _git_head(repo_root)
    source_path = f"fixtures/{snapshot['snapshot_id']}.json"
    lineage = build_lineage(
        as_of_ms=as_of_ms,
        snapshot_id=str(snapshot["snapshot_id"]),
        snapshot_availability_ms=int(snapshot["availability_ms"]),
        source_kind="sanitized_fixture",
        source_path=source_path,
        source_checksum=str(snapshot.get("source_checksum") or ""),
        retrieval_timestamp=retrieval_timestamp,
        code_version=code_version,
        thresholds_checksum=thresholds_checksum,
        universe_checksum_value=uni_ck,
    )

    result = {
        "schema": DISCOVERY_SCHEMA,
        "universe_id": UNIVERSE_ID,
        "as_of_ms": as_of_ms,
        "availability_timestamp": lineage["availability_timestamp"],
        "availability_ms": lineage["availability_ms"],
        "retrieval_timestamp": retrieval_timestamp,
        "snapshot_id": snapshot["snapshot_id"],
        "eligible_universe": eligible_symbols,
        "rejected_universe": rejected_symbols,
        "eligible_count": len(eligible_symbols),
        "rejected_count": len(rejected_symbols),
        "eligible_details": eligible,
        "rejected_details": rejected,
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "universe_checksum": uni_ck,
        "thresholds": th,
        "thresholds_checksum": thresholds_checksum,
        "evaluation_dimensions": list(EVALUATION_DIMENSIONS),
        "hard_bans": list(HARD_BANS),
        "lineage": lineage,
        "source_checksum": snapshot.get("source_checksum"),
        "exchange_write": False,
        "demo": False,
        "pr27_merged": False,
        "mainnet_trading": False,
        "real_money": False,
        "point_in_time": True,
        "used_today_for_past": False,
    }
    result["result_checksum"] = sha_obj(
        {
            "universe_checksum": uni_ck,
            "lineage_id": lineage["lineage_id"],
            "eligible": eligible_symbols,
            "rejected": rejected_symbols,
            "rejection_reason_counts": result["rejection_reason_counts"],
        }
    )
    return result


def compare_eras(as_of_a_ms: int, as_of_b_ms: int, **kwargs: Any) -> dict[str, Any]:
    """Compare two PIT discoveries — proves listing/delisting dynamics across time."""
    a = discover_universe(as_of_a_ms, **kwargs)
    b = discover_universe(as_of_b_ms, **kwargs)
    set_a = set(a["eligible_universe"])
    set_b = set(b["eligible_universe"])
    return {
        "schema": "nexus_pit_era_comparison_v1",
        "as_of_a_ms": as_of_a_ms,
        "as_of_b_ms": as_of_b_ms,
        "eligible_a": sorted(set_a),
        "eligible_b": sorted(set_b),
        "appeared": sorted(set_b - set_a),
        "disappeared": sorted(set_a - set_b),
        "stable": sorted(set_a & set_b),
        "checksum_a": a["universe_checksum"],
        "checksum_b": b["universe_checksum"],
        "checksums_differ": a["universe_checksum"] != b["universe_checksum"],
    }
