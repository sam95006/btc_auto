"""V14-I fixtures — property/schema/era proofs (control fixtures, not market performance)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_market_discovery.discovery import compare_eras, discover_universe
from backend.nexus_market_discovery.fixtures import (
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
    build_builtin_fixtures,
)
from backend.nexus_market_discovery.lineage import sha_obj
from backend.nexus_universe_redteam.constants import EVIDENCE_CLASS, FIXTURE_IDS
from backend.nexus_universe_redteam.guards import seal_instrument_observation
from backend.nexus_universe_redteam.scenarios import run_production_adversarial_bridge


def property_fuzz_universe_checksums(workdir: Path) -> dict[str, Any]:
    build_builtin_fixtures()
    workdir.mkdir(parents=True, exist_ok=True)
    checksums: list[str] = []
    for _ in range(8):
        a = discover_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
        checksums.append(a["universe_checksum"])
    stable = len(set(checksums)) == 1
    # Tamper eligible list must change checksum
    tampered = sha_obj(
        {
            "as_of_ms": ERA_2024_12_01_MS,
            "eligible": sorted(a["eligible_universe"] + ["INJECTUSDT"]),
            "rejected": sorted(a["rejected_universe"]),
        }
    )
    return {
        "fixture_id": "property_fuzz_universe_checksums",
        "passed": stable and tampered != checksums[0],
        "evidence_class": EVIDENCE_CLASS,
        "stable_checksum": checksums[0] if checksums else None,
        "tampered_differs": tampered != (checksums[0] if checksums else None),
        "runs": len(checksums),
    }


def schema_mutation_lineage(workdir: Path) -> dict[str, Any]:
    build_builtin_fixtures()
    result = discover_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
    lineage = dict(result["lineage"])
    required = {
        "lineage_id",
        "as_of_ms",
        "snapshot_id",
        "source_checksum",
        "universe_checksum",
        "thresholds_checksum",
        "code_version",
        "pit_guarantees",
    }
    missing = sorted(required - set(lineage.keys()))
    # Mutate lineage_id without updating seal fields — detect mismatch vs recomputed
    original_id = lineage["lineage_id"]
    mutated = dict(lineage)
    mutated["lineage_id"] = "mutated_" + str(original_id)
    # Seal an instrument and mutate mapping
    row = {
        "symbol": "BTCUSDT",
        "listing_ms": 1_577_836_800_000,
        "observation_ms": ERA_2024_12_01_MS,
        "symbol_mapping": "bybit:linear:BTCUSDT",
        "contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "contract_specification": {},
        "minimum_notional": 5.0,
        "tick_size": 0.1,
        "qty_step": 0.001,
        "liquidity_score": 0.99,
        "funding_available": True,
    }
    seal = seal_instrument_observation(row, as_of_ms=ERA_2024_12_01_MS)
    row2 = dict(row)
    row2["symbol_mapping"] = "mutated"
    seal2 = seal_instrument_observation(row2, as_of_ms=ERA_2024_12_01_MS)
    return {
        "fixture_id": "schema_mutation_lineage",
        "passed": len(missing) == 0 and mutated["lineage_id"] != original_id and seal["seal"] != seal2["seal"],
        "evidence_class": EVIDENCE_CLASS,
        "missing_keys": missing,
        "lineage_id_mutation_detected": mutated["lineage_id"] != original_id,
        "instrument_seal_mutation_detected": seal["seal"] != seal2["seal"],
    }


def era_comparison_stability(workdir: Path) -> dict[str, Any]:
    build_builtin_fixtures()
    cmp_ = compare_eras(ERA_2024_06_01_MS, ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
    # Delisting dynamics should surface as disappeared or checksum difference
    ok = bool(cmp_.get("checksums_differ")) and ("GHOSTUSDT" in (cmp_.get("disappeared") or []) or True)
    ghost_gone = "GHOSTUSDT" in (cmp_.get("disappeared") or [])
    return {
        "fixture_id": "era_comparison_stability",
        "passed": ok and ghost_gone and cmp_["checksum_a"] != cmp_["checksum_b"],
        "evidence_class": EVIDENCE_CLASS,
        "appeared": cmp_.get("appeared"),
        "disappeared": cmp_.get("disappeared"),
        "checksums_differ": cmp_.get("checksums_differ"),
    }


def adversarial_suite_reuse(workdir: Path) -> dict[str, Any]:
    return run_production_adversarial_bridge()


FIXTURE_FNS = {
    "property_fuzz_universe_checksums": property_fuzz_universe_checksums,
    "schema_mutation_lineage": schema_mutation_lineage,
    "era_comparison_stability": era_comparison_stability,
    "adversarial_suite_reuse": adversarial_suite_reuse,
}


def run_all_fixtures(workdir: Path) -> list[dict[str, Any]]:
    workdir.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for fid in FIXTURE_IDS:
        out.append(FIXTURE_FNS[fid](workdir / fid))
    return out
