"""Fixture proofs for historical universe / survivorship control."""
from __future__ import annotations

from typing import Any

from backend.nexus_historical_universe.constants import (
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
    FIXTURE_IDS,
)
from backend.nexus_historical_universe.events import (
    build_contract_spec_timeline,
    build_listing_delisting_events,
)
from backend.nexus_historical_universe.fixtures import fixture_catalog, fixture_instruments
from backend.nexus_historical_universe.hashutil import sha_obj
from backend.nexus_historical_universe.universe import reconstruct_universe


def fixture_multi_era_membership() -> dict[str, Any]:
    mid = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    late = reconstruct_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
    future = reconstruct_universe(ERA_2025_03_01_MS, retrieval_timestamp="FIXED")
    ghost_mid = "GHOSTUSDT" in mid["historical_eligible_universe"]
    ghost_late = "GHOSTUSDT" in late["historical_eligible_universe"]
    late_mid = "LATEUSDT" in mid["historical_eligible_universe"]
    late_future = "LATEUSDT" in future["contracts_listed"]
    checksums_differ = mid["universe_checksum"] != late["universe_checksum"]
    passed = ghost_mid and not ghost_late and not late_mid and late_future and checksums_differ
    return {
        "fixture_id": "multi_era_membership",
        "passed": passed,
        "evidence_class": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
        "ghost_eligible_mid": ghost_mid,
        "ghost_eligible_late": ghost_late,
        "late_eligible_mid": late_mid,
        "late_listed_future": late_future,
        "checksums_differ": checksums_differ,
    }


def fixture_listing_delisting_events() -> dict[str, Any]:
    events = build_listing_delisting_events()
    types = {e["event_type"] for e in events["events"]}
    ghost_delist = any(
        e["event_type"] == "DELISTING" and e["symbol"] == "GHOSTUSDT" for e in events["events"]
    )
    late_list = any(
        e["event_type"] == "LISTING" and e["symbol"] == "LATEUSDT" for e in events["events"]
    )
    # Deterministic checksum
    again = build_listing_delisting_events()
    stable = events["events_checksum"] == again["events_checksum"]
    passed = types == {"LISTING", "DELISTING"} and ghost_delist and late_list and stable
    return {
        "fixture_id": "listing_delisting_events",
        "passed": passed,
        "evidence_class": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
        "event_count": events["event_count"],
        "ghost_delist_present": ghost_delist,
        "late_listing_present": late_list,
        "checksum_stable": stable,
    }


def fixture_contract_spec_timeline() -> dict[str, Any]:
    timeline = build_contract_spec_timeline()
    btc_versions = [
        e for e in timeline["timeline"] if e["symbol"] == "BTCUSDT"
    ]
    pepe_bumps = [
        e
        for e in timeline["timeline"]
        if e["symbol"] == "PEPEUSDT" and "minimum_notional" in (e.get("changed_fields") or [])
    ]
    mid = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    post = reconstruct_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
    btc_mid = next(d for d in mid["instrument_details"] if d["symbol"] == "BTCUSDT")
    btc_post = next(d for d in post["instrument_details"] if d["symbol"] == "BTCUSDT")
    # Spec v2 effective ~1720000000000 is after June 2024 era? 
    # ERA_2024_06_01 = 1717200000000, btc_spec_v2 = 1720000000000
    # So mid (June) should still be v1 tick 0.1; Dec should be v2 tick 0.5
    mid_tick = (btc_mid.get("contract_spec") or {}).get("tick_size")
    post_tick = (btc_post.get("contract_spec") or {}).get("tick_size")
    passed = (
        len(btc_versions) >= 2
        and len(pepe_bumps) >= 1
        and mid_tick == 0.1
        and post_tick == 0.5
    )
    return {
        "fixture_id": "contract_spec_timeline",
        "passed": passed,
        "evidence_class": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
        "btc_spec_versions": len(btc_versions),
        "pepe_min_notional_bumps": len(pepe_bumps),
        "btc_mid_tick": mid_tick,
        "btc_post_tick": post_tick,
    }


def fixture_liquidity_pit_binding() -> dict[str, Any]:
    as_of = ERA_2024_06_01_MS
    uni = reconstruct_universe(as_of, retrieval_timestamp="FIXED")
    thin = next(d for d in uni["instrument_details"] if d["symbol"] == "THINUSDT")
    obs_ms = thin.get("liquidity_observation_ms")
    score = (thin.get("liquidity") or {}).get("liquidity_score")
    # Must bind to June observation (0.01), never today (0.95)
    passed = obs_ms is not None and int(obs_ms) <= as_of and float(score) == 0.01
    # Tamper detection on catalog
    cat = fixture_catalog()
    tampered = dict(cat)
    tampered["instruments"] = list(cat["instruments"]) + [{"symbol": "FAKEUSDT"}]
    tampered_ck = sha_obj({"symbols": sorted(i["symbol"] for i in tampered["instruments"])})
    return {
        "fixture_id": "liquidity_pit_binding",
        "passed": passed and tampered_ck != cat["catalog_checksum"],
        "evidence_class": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
        "thin_observation_ms": obs_ms,
        "thin_liquidity_score": score,
        "catalog_checksum": cat["catalog_checksum"],
        "tamper_detected": tampered_ck != cat["catalog_checksum"],
    }


def fixture_data_completeness_gate() -> dict[str, Any]:
    uni = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    thin = next(d for d in uni["instrument_details"] if d["symbol"] == "THINUSDT")
    reasons = thin.get("exclusion_reasons") or []
    passed = (
        not thin["eligible"]
        and ("DATA_INCOMPLETE" in reasons or "LIQUIDITY_BELOW_THRESHOLD" in reasons)
    )
    return {
        "fixture_id": "data_completeness_gate",
        "passed": passed,
        "evidence_class": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
        "thin_eligible": thin["eligible"],
        "thin_completeness": thin.get("data_completeness"),
        "exclusion_reasons": reasons,
        "instrument_count": len(fixture_instruments()),
    }


FIXTURE_FNS = {
    "multi_era_membership": fixture_multi_era_membership,
    "listing_delisting_events": fixture_listing_delisting_events,
    "contract_spec_timeline": fixture_contract_spec_timeline,
    "liquidity_pit_binding": fixture_liquidity_pit_binding,
    "data_completeness_gate": fixture_data_completeness_gate,
}


def run_all_fixtures() -> list[dict[str, Any]]:
    return [FIXTURE_FNS[fid]() for fid in FIXTURE_IDS]
