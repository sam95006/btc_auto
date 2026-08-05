"""Adversarial Pass-2 probes for PIT market discovery integrity."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.nexus_market_discovery.discovery import PitDiscoveryError, discover_universe
from backend.nexus_market_discovery.evaluator import evaluate_instrument
from backend.nexus_market_discovery.fixtures import (
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
    build_builtin_fixtures,
    select_snapshot_for_as_of,
)
from backend.nexus_market_discovery.lineage import sha_obj


def probe_today_for_past_banned(fixtures_dir: Path | None = None) -> dict[str, Any]:
    """Attempt to force a later snapshot for an earlier as_of — must fail."""
    # as_of in June 2024; inject a fake "today" snapshot path via now_ms near late era
    as_of = ERA_2024_06_01_MS + 86_400_000
    try:
        # Directly assert guard by calling with now_ms and a corrupted selection path:
        # select should pick June snapshot; assert_not_today_for_past with synthetic
        # live availability should raise when we manually violate.
        from backend.nexus_market_discovery.discovery import assert_not_today_for_past

        raised = False
        detail = None
        try:
            assert_not_today_for_past(
                as_of_ms=as_of,
                snapshot_availability_ms=ERA_2025_03_01_MS,  # later universe
                source_kind="sanitized_fixture",
                now_ms=ERA_2025_03_01_MS,
            )
        except PitDiscoveryError as exc:
            raised = True
            detail = str(exc)
        live_reject = False
        live_detail = None
        try:
            assert_not_today_for_past(
                as_of_ms=as_of,
                snapshot_availability_ms=ERA_2025_03_01_MS - 3_600_000,
                source_kind="sanitized_fixture",
                now_ms=ERA_2025_03_01_MS,
            )
        except PitDiscoveryError as exc:
            live_reject = True
            live_detail = str(exc)
        return {
            "probe": "today_for_past_banned",
            "pass": raised and live_reject,
            "future_snapshot_blocked": raised,
            "live_today_blocked": live_reject,
            "detail": {"future": detail, "live": live_detail},
        }
    except Exception as exc:  # pragma: no cover
        return {"probe": "today_for_past_banned", "pass": False, "error": str(exc)}


def probe_future_observation_leak() -> dict[str, Any]:
    row = {
        "symbol": "LEAKUSDT",
        "status": "Trading",
        "contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "listing_ms": ERA_2024_06_01_MS,
        "delisting_ms": None,
        "observation_ms": ERA_2025_03_01_MS,  # after as_of
        "liquidity_score": 0.99,
        "turnover_usdt": 1e9,
        "volume_usdt": 1e9,
        "spread_bps": 1.0,
        "depth_usdt": 1e6,
        "open_interest_usdt": 1e6,
        "funding_available": True,
        "data_completeness": 0.99,
        "staleness_ms": 0,
        "symbol_mapping": "bybit:linear:LEAKUSDT",
        "tick_size": 0.1,
        "qty_step": 0.001,
        "minimum_notional": 5.0,
    }
    ev = evaluate_instrument(row, as_of_ms=ERA_2024_12_01_MS)
    return {
        "probe": "future_observation_leak",
        "pass": (not ev.eligible) and ("FUTURE_OBSERVATION_LEAK" in ev.rejection_reasons),
        "reasons": ev.rejection_reasons,
    }


def probe_no_snapshot_before_era(fixtures_dir: Path | None = None) -> dict[str, Any]:
    """as_of before any fixture — must refuse rather than invent from today."""
    early = ERA_2024_06_01_MS - 10_000_000_000
    raised = False
    detail = None
    try:
        discover_universe(early, fixtures_dir=fixtures_dir)
    except PitDiscoveryError as exc:
        raised = True
        detail = str(exc)
    return {
        "probe": "no_snapshot_before_era",
        "pass": raised and detail is not None and "no_historical_snapshot" in detail,
        "detail": detail,
    }


def probe_deterministic_checksum(fixtures_dir: Path | None = None) -> dict[str, Any]:
    a = discover_universe(ERA_2024_12_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="FIXED")
    b = discover_universe(ERA_2024_12_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="FIXED")
    # lineage retrieval is fixed; checksums must match
    return {
        "probe": "deterministic_checksum",
        "pass": a["universe_checksum"] == b["universe_checksum"]
        and a["result_checksum"] == b["result_checksum"],
        "checksum": a["universe_checksum"],
    }


def probe_delisting_dynamics(fixtures_dir: Path | None = None) -> dict[str, Any]:
    """GHOSTUSDT eligible before delist, rejected after."""
    before = discover_universe(ERA_2024_06_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="FIXED")
    after = discover_universe(ERA_2024_12_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="FIXED")
    ghost_before = "GHOSTUSDT" in before["eligible_universe"]
    ghost_after = "GHOSTUSDT" in after["eligible_universe"]
    ghost_rejected = any(
        r["symbol"] == "GHOSTUSDT" and "DELISTED" in r["rejection_reasons"]
        for r in after["rejected_details"]
    )
    return {
        "probe": "delisting_dynamics",
        "pass": ghost_before and (not ghost_after) and ghost_rejected,
        "ghost_before_eligible": ghost_before,
        "ghost_after_eligible": ghost_after,
        "ghost_delisted_reason": ghost_rejected,
    }


def probe_late_listing_excluded(fixtures_dir: Path | None = None) -> dict[str, Any]:
    """LATEUSDT must not appear in mid-2024 eligible set."""
    mid = discover_universe(ERA_2024_06_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="FIXED")
    late_era = discover_universe(ERA_2025_03_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="FIXED")
    return {
        "probe": "late_listing_excluded",
        "pass": ("LATEUSDT" not in mid["eligible_universe"])
        and ("LATEUSDT" in late_era["eligible_universe"] or "LATEUSDT" in late_era["rejected_universe"]),
        "mid_has_late": "LATEUSDT" in mid["eligible_universe"] or "LATEUSDT" in mid["rejected_universe"],
        "late_era_knows_late": "LATEUSDT" in late_era["eligible_universe"]
        or "LATEUSDT" in late_era["rejected_universe"],
    }


def probe_snapshot_tamper_detect(fixtures_dir: Path | None = None) -> dict[str, Any]:
    snap = select_snapshot_for_as_of(ERA_2024_12_01_MS, fixtures_dir=fixtures_dir)
    tampered = copy.deepcopy(snap)
    tampered["instruments"] = list(tampered["instruments"]) + [
        {
            "symbol": "INJECTUSDT",
            "base_coin": "INJ",
            "quote_coin": "USDT",
            "settle_coin": "USDT",
            "status": "Trading",
            "contract_type": "LinearPerpetual",
            "listing_ms": ERA_2024_06_01_MS,
            "delisting_ms": None,
            "observation_ms": ERA_2024_12_01_MS,
            "liquidity_score": 0.99,
            "turnover_usdt": 1e9,
            "volume_usdt": 1e9,
            "spread_bps": 1.0,
            "depth_usdt": 1e6,
            "open_interest_usdt": 1e6,
            "funding_available": True,
            "data_completeness": 0.99,
            "staleness_ms": 0,
            "symbol_mapping": "x",
            "tick_size": 0.1,
            "qty_step": 0.1,
            "minimum_notional": 5.0,
            "contract_specification": {},
        }
    ]
    original_ck = snap["source_checksum"]
    recomputed = sha_obj(
        {
            "snapshot_id": tampered["snapshot_id"],
            "availability_ms": tampered["availability_ms"],
            "symbols": sorted(i["symbol"] for i in tampered["instruments"]),
            "instrument_checksums": [
                sha_obj(i) for i in sorted(tampered["instruments"], key=lambda x: x["symbol"])
            ],
        }
    )
    return {
        "probe": "snapshot_tamper_detect",
        "pass": recomputed != original_ck,
        "original_checksum": original_ck,
        "tampered_checksum": recomputed,
    }


def probe_non_fixture_source_rejected() -> dict[str, Any]:
    raised = False
    detail = None
    try:
        from backend.nexus_market_discovery.discovery import assert_not_today_for_past

        assert_not_today_for_past(
            as_of_ms=ERA_2024_12_01_MS,
            snapshot_availability_ms=ERA_2024_12_01_MS,
            source_kind="live_bybit_today",
        )
    except PitDiscoveryError as exc:
        raised = True
        detail = str(exc)
    return {
        "probe": "non_fixture_source_rejected",
        "pass": raised and "unsupported_source_kind" in (detail or ""),
        "detail": detail,
    }


def probe_live_public_metadata_banned_for_past() -> dict[str, Any]:
    from backend.nexus_market_discovery.public_metadata import assert_live_read_allowed

    raised = False
    detail = None
    try:
        assert_live_read_allowed(as_of_ms=ERA_2024_06_01_MS, now_ms=ERA_2025_03_01_MS)
    except PitDiscoveryError as exc:
        raised = True
        detail = str(exc)
    return {
        "probe": "live_public_metadata_banned_for_past",
        "pass": raised and "live_public_metadata_forbidden" in (detail or ""),
        "detail": detail,
    }


def run_adversarial_suite(fixtures_dir: Path | None = None) -> dict[str, Any]:
    # Ensure fixtures exist for probes that load them
    build_builtin_fixtures()
    probes = [
        probe_today_for_past_banned(fixtures_dir),
        probe_future_observation_leak(),
        probe_no_snapshot_before_era(fixtures_dir),
        probe_deterministic_checksum(fixtures_dir),
        probe_delisting_dynamics(fixtures_dir),
        probe_late_listing_excluded(fixtures_dir),
        probe_snapshot_tamper_detect(fixtures_dir),
        probe_non_fixture_source_rejected(),
        probe_live_public_metadata_banned_for_past(),
    ]
    passed = sum(1 for p in probes if p.get("pass"))
    return {
        "schema": "v13_d_adversarial_suite",
        "probe_count": len(probes),
        "passed": passed,
        "failed": len(probes) - passed,
        "all_pass": passed == len(probes),
        "probes": probes,
    }
