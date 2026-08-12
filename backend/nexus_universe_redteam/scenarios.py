"""V14-I attack scenarios — universe lineage and listing-bias fail-closed proofs.

All attacks are local/simulated against PIT discovery + owned guards.
No Demo/exchange/mainnet/real money. Platform-blocked never counts as PASS.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.nexus_market_discovery.adversarial import run_adversarial_suite
from backend.nexus_market_discovery.discovery import PitDiscoveryError, assert_not_today_for_past, discover_universe
from backend.nexus_market_discovery.evaluator import evaluate_instrument
from backend.nexus_market_discovery.fixtures import (
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
    build_builtin_fixtures,
)
from backend.nexus_universe_redteam.constants import ATTACK_SCENARIO_IDS
from backend.nexus_universe_redteam.guards import (
    detect_contract_spec_drift,
    detect_delisting_leakage,
    detect_future_funding_leakage,
    detect_future_liquidity_leakage,
    detect_listing_date_leakage,
    detect_mapping_drift,
    detect_min_notional_drift,
    detect_rename_leakage,
    detect_survivorship_bias,
    detect_today_universe_substitution,
    require_attack_disposition,
    seal_instrument_observation,
    verify_instrument_seal,
)


@dataclass
class ScenarioResult:
    scenario_id: str
    passed: bool
    fail_closed: bool
    detail: str = ""
    critical: bool = False
    attack_blocked: bool = False
    platform_blocked: bool = False
    disposition: str = ""
    critical_blocker_code: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "fail_closed": self.fail_closed,
            "detail": self.detail,
            "critical": self.critical,
            "attack_blocked": self.attack_blocked,
            "platform_blocked": self.platform_blocked,
            "disposition": self.disposition,
            "critical_blocker_code": self.critical_blocker_code,
            "evidence": dict(self.evidence),
        }


def _ok(
    scenario_id: str,
    *,
    detail: str,
    evidence: dict[str, Any],
    disposition: str = "BLOCKED_BY_CODE",
    critical_blocker_code: str | None = None,
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        passed=True,
        fail_closed=True,
        detail=detail,
        critical=False,
        attack_blocked=True,
        platform_blocked=False,
        disposition=disposition,
        critical_blocker_code=critical_blocker_code,
        evidence=evidence,
    )


def _fail(
    scenario_id: str,
    *,
    detail: str,
    evidence: dict[str, Any] | None = None,
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        passed=False,
        fail_closed=True,
        detail=detail,
        critical=True,
        attack_blocked=False,
        platform_blocked=False,
        disposition="UNRESOLVED_ATTACK_SURVIVOR",
        evidence=evidence or {},
    )


def scenario_survivorship_bias(workdir: Path) -> ScenarioResult:
    """Today-survivors-only reconstruction must not match full PIT membership."""
    build_builtin_fixtures()
    as_of = ERA_2024_06_01_MS
    pit = discover_universe(as_of, retrieval_timestamp="FIXED")
    later = discover_universe(ERA_2025_03_01_MS, retrieval_timestamp="FIXED")
    # Attack: reconstruct mid-2024 using only symbols still eligible "today"
    today_survivors = list(later["eligible_universe"])
    survivor_only = sorted(set(pit["eligible_universe"]) & set(today_survivors))
    # GHOST may be eligible in June and gone later — classic survivorship drop
    det = detect_survivorship_bias(
        claimed_symbols=survivor_only,
        pit_eligible_symbols=pit["eligible_universe"],
        today_survivor_symbols=today_survivors,
    )
    # Honest reconstruction must equal PIT
    honest = detect_survivorship_bias(
        claimed_symbols=pit["eligible_universe"],
        pit_eligible_symbols=pit["eligible_universe"],
        today_survivor_symbols=today_survivors,
    )
    disposition = require_attack_disposition(
        attack_blocked_by_code=(not det["ok"]) and honest["ok"],
        critical_blocker_code=None,
    )
    if not disposition["ok"]:
        return _fail("survivorship_bias", detail="survivorship_attack_not_blocked", evidence={"det": det})
    return _ok(
        "survivorship_bias",
        detail="survivorship_only_reconstruction_blocked",
        evidence={
            "attack": det,
            "honest": honest,
            "ghost_in_pit": "GHOSTUSDT" in pit["eligible_universe"],
            "ghost_in_survivor_only": "GHOSTUSDT" in survivor_only,
        },
        disposition=disposition["status"],
    )


def scenario_listing_date_leakage(workdir: Path) -> ScenarioResult:
    build_builtin_fixtures()
    mid = discover_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    late_eligible = "LATEUSDT" in mid["eligible_universe"]
    # Direct evaluator attack: claim late listing as eligible early
    row = {
        "symbol": "LATEUSDT",
        "status": "Trading",
        "contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "listing_ms": ERA_2025_03_01_MS,
        "delisting_ms": None,
        "observation_ms": ERA_2024_06_01_MS,
        "liquidity_score": 0.99,
        "turnover_usdt": 1e9,
        "volume_usdt": 1e9,
        "spread_bps": 1.0,
        "depth_usdt": 1e6,
        "open_interest_usdt": 1e6,
        "funding_available": True,
        "data_completeness": 0.99,
        "staleness_ms": 0,
        "symbol_mapping": "bybit:linear:LATEUSDT",
        "tick_size": 0.1,
        "qty_step": 0.001,
        "minimum_notional": 5.0,
        "contract_specification": {},
    }
    ev = evaluate_instrument(row, as_of_ms=ERA_2024_06_01_MS)
    guard = detect_listing_date_leakage(
        symbol="LATEUSDT",
        listing_ms=int(row["listing_ms"]),
        as_of_ms=ERA_2024_06_01_MS,
        claimed_eligible=True,
    )
    blocked = (not late_eligible) and (not ev.eligible) and ("NOT_YET_LISTED" in ev.rejection_reasons) and (not guard["ok"])
    disposition = require_attack_disposition(attack_blocked_by_code=blocked, critical_blocker_code=None)
    if not disposition["ok"]:
        return _fail("listing_date_leakage", detail="listing_leak_survived", evidence={"ev": ev.to_dict(), "guard": guard})
    return _ok(
        "listing_date_leakage",
        detail="listing_date_leakage_blocked",
        evidence={"late_in_mid": late_eligible, "reasons": ev.rejection_reasons, "guard": guard},
        disposition=disposition["status"],
    )


def scenario_delisting_leakage(workdir: Path) -> ScenarioResult:
    build_builtin_fixtures()
    before = discover_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    after = discover_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
    ghost_before = "GHOSTUSDT" in before["eligible_universe"]
    ghost_after = "GHOSTUSDT" in after["eligible_universe"]
    ghost_rejected = any(
        r["symbol"] == "GHOSTUSDT" and "DELISTED" in (r.get("rejection_reasons") or [])
        for r in after["rejected_details"]
    )
    # Attack: claim eligible after delist
    attack = detect_delisting_leakage(
        symbol="GHOSTUSDT",
        delisting_ms=1_725_000_000_000,
        as_of_ms=ERA_2024_12_01_MS,
        claimed_eligible=True,
        historically_listed=True,
    )
    blocked = ghost_before and (not ghost_after) and ghost_rejected and (not attack["ok"])
    disposition = require_attack_disposition(attack_blocked_by_code=blocked, critical_blocker_code=None)
    if not disposition["ok"]:
        return _fail("delisting_leakage", detail="delisting_leak_survived", evidence={"attack": attack})
    return _ok(
        "delisting_leakage",
        detail="delisting_leakage_blocked",
        evidence={
            "ghost_before": ghost_before,
            "ghost_after": ghost_after,
            "ghost_rejected": ghost_rejected,
            "attack": attack,
        },
        disposition=disposition["status"],
    )


def scenario_rename_leakage(workdir: Path) -> ScenarioResult:
    """Silent rename without lineage must be blocked by owned rename guard."""
    as_of_before = ERA_2024_06_01_MS
    rename_ms = ERA_2024_12_01_MS
    # Attack A: use new symbol before rename effective, no lineage
    a = detect_rename_leakage(
        old_symbol="PEPEUSDT",
        new_symbol="1000PEPEUSDT",
        rename_effective_ms=rename_ms,
        as_of_ms=as_of_before,
        rename_lineage_id=None,
        claimed_identity="1000PEPEUSDT",
    )
    # Attack B: silent rename (any remapping without lineage)
    b = detect_rename_leakage(
        old_symbol="PEPEUSDT",
        new_symbol="1000PEPEUSDT",
        rename_effective_ms=rename_ms,
        as_of_ms=rename_ms + 1,
        rename_lineage_id=None,
        claimed_identity="1000PEPEUSDT",
    )
    # Honest: lineage present, identity consistent with era
    honest = detect_rename_leakage(
        old_symbol="PEPEUSDT",
        new_symbol="1000PEPEUSDT",
        rename_effective_ms=rename_ms,
        as_of_ms=rename_ms + 1,
        rename_lineage_id="rename:pepe->1000pepe:v1",
        claimed_identity="1000PEPEUSDT",
    )
    blocked = (not a["ok"]) and (not b["ok"]) and honest["ok"]
    disposition = require_attack_disposition(attack_blocked_by_code=blocked, critical_blocker_code=None)
    if not disposition["ok"]:
        return _fail("rename_leakage", detail="rename_leak_survived", evidence={"a": a, "b": b, "honest": honest})
    return _ok(
        "rename_leakage",
        detail="rename_without_lineage_blocked",
        evidence={"pre_effective": a, "silent": b, "honest": honest},
        disposition=disposition["status"],
    )


def scenario_contract_spec_changes(workdir: Path) -> ScenarioResult:
    as_of = ERA_2024_06_01_MS
    sealed_row = {
        "symbol": "BTCUSDT",
        "contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "contract_specification": {"tick_size": 0.1, "qty_step": 0.001, "minimum_notional": 5.0},
        "listing_ms": 1_577_836_800_000,
        "observation_ms": as_of,
        "minimum_notional": 5.0,
        "tick_size": 0.1,
        "qty_step": 0.001,
        "symbol_mapping": "bybit:linear:BTCUSDT",
        "liquidity_score": 0.99,
        "funding_available": True,
    }
    seal = seal_instrument_observation(sealed_row, as_of_ms=as_of)
    # Attack: future-era contract tick change applied to past as_of
    attacked = copy.deepcopy(sealed_row)
    attacked["contract_specification"] = {"tick_size": 0.5, "qty_step": 0.001, "minimum_notional": 5.0}
    attacked["tick_size"] = 0.5
    attacked["observation_ms"] = ERA_2025_03_01_MS
    drift = detect_contract_spec_drift(
        sealed_spec=seal["body"]["contract_specification"],
        observed_spec=attacked["contract_specification"],
        as_of_ms=as_of,
        observation_ms=attacked["observation_ms"],
    )
    # Production evaluator also rejects future observation
    ev = evaluate_instrument(
        {
            **attacked,
            "status": "Trading",
            "delisting_ms": None,
            "turnover_usdt": 1e9,
            "volume_usdt": 1e9,
            "spread_bps": 1.0,
            "depth_usdt": 1e6,
            "open_interest_usdt": 1e6,
            "data_completeness": 0.99,
            "staleness_ms": 0,
        },
        as_of_ms=as_of,
    )
    verify_fail = verify_instrument_seal(attacked, as_of_ms=as_of, expected_seal=seal["seal"])
    blocked = (not drift["ok"]) and (not ev.eligible) and (not verify_fail["ok"])
    disposition = require_attack_disposition(attack_blocked_by_code=blocked, critical_blocker_code=None)
    if not disposition["ok"]:
        return _fail("contract_spec_changes", detail="contract_spec_drift_survived", evidence={"drift": drift})
    return _ok(
        "contract_spec_changes",
        detail="contract_spec_change_blocked",
        evidence={"drift": drift, "reasons": ev.rejection_reasons, "seal_verify": verify_fail},
        disposition=disposition["status"],
    )


def scenario_today_universe_substitution(workdir: Path) -> ScenarioResult:
    as_of = ERA_2024_06_01_MS + 86_400_000
    guard = detect_today_universe_substitution(
        as_of_ms=as_of,
        snapshot_availability_ms=ERA_2025_03_01_MS,
        source_kind="sanitized_fixture",
        now_ms=ERA_2025_03_01_MS,
    )
    raised = False
    detail = None
    try:
        assert_not_today_for_past(
            as_of_ms=as_of,
            snapshot_availability_ms=ERA_2025_03_01_MS,
            source_kind="sanitized_fixture",
            now_ms=ERA_2025_03_01_MS,
        )
    except PitDiscoveryError as exc:
        raised = True
        detail = str(exc)
    live_reject = False
    try:
        assert_not_today_for_past(
            as_of_ms=as_of,
            snapshot_availability_ms=ERA_2025_03_01_MS - 3_600_000,
            source_kind="sanitized_fixture",
            now_ms=ERA_2025_03_01_MS,
        )
    except PitDiscoveryError:
        live_reject = True
    blocked = (not guard["ok"]) and raised and live_reject
    disposition = require_attack_disposition(attack_blocked_by_code=blocked, critical_blocker_code=None)
    if not disposition["ok"]:
        return _fail("today_universe_substitution", detail="today_for_past_survived", evidence={"guard": guard})
    return _ok(
        "today_universe_substitution",
        detail="today_universe_substitution_blocked",
        evidence={"guard": guard, "production_detail": detail, "live_reject": live_reject},
        disposition=disposition["status"],
    )


def scenario_future_liquidity_leakage(workdir: Path) -> ScenarioResult:
    as_of = ERA_2024_06_01_MS
    # Attack: inject future-era liquidity observation into past eligibility
    row = {
        "symbol": "THINUSDT",
        "status": "Trading",
        "contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "listing_ms": 1_672_531_200_000,
        "delisting_ms": None,
        "observation_ms": ERA_2025_03_01_MS,
        "liquidity_score": 0.99,
        "turnover_usdt": 1e9,
        "volume_usdt": 1e9,
        "spread_bps": 1.0,
        "depth_usdt": 1e6,
        "open_interest_usdt": 1e6,
        "funding_available": True,
        "data_completeness": 0.99,
        "staleness_ms": 0,
        "symbol_mapping": "bybit:linear:THINUSDT",
        "tick_size": 0.01,
        "qty_step": 1.0,
        "minimum_notional": 5.0,
    }
    ev = evaluate_instrument(row, as_of_ms=as_of)
    guard = detect_future_liquidity_leakage(
        as_of_ms=as_of,
        observation_ms=int(row["observation_ms"]),
        liquidity_score=float(row["liquidity_score"]),
        claimed_from_future_era=True,
    )
    blocked = (not ev.eligible) and ("FUTURE_OBSERVATION_LEAK" in ev.rejection_reasons) and (not guard["ok"])
    disposition = require_attack_disposition(attack_blocked_by_code=blocked, critical_blocker_code=None)
    if not disposition["ok"]:
        return _fail("future_liquidity_leakage", detail="future_liquidity_survived", evidence={"ev": ev.to_dict()})
    return _ok(
        "future_liquidity_leakage",
        detail="future_liquidity_leakage_blocked",
        evidence={"reasons": ev.rejection_reasons, "guard": guard},
        disposition=disposition["status"],
    )


def scenario_future_funding_availability(workdir: Path) -> ScenarioResult:
    as_of = ERA_2024_06_01_MS
    # Historical: funding unavailable; attack upgrades via future observation
    guard = detect_future_funding_leakage(
        as_of_ms=as_of,
        observation_ms=ERA_2025_03_01_MS,
        funding_available=True,
        historical_funding_available=False,
    )
    row = {
        "symbol": "NOFUNDUSDT",
        "status": "Trading",
        "contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "listing_ms": 1_672_531_200_000,
        "delisting_ms": None,
        "observation_ms": ERA_2025_03_01_MS,
        "liquidity_score": 0.9,
        "turnover_usdt": 1e8,
        "volume_usdt": 5e7,
        "spread_bps": 2.0,
        "depth_usdt": 5e5,
        "open_interest_usdt": 1e6,
        "funding_available": True,
        "data_completeness": 0.99,
        "staleness_ms": 0,
        "symbol_mapping": "bybit:linear:NOFUNDUSDT",
        "tick_size": 0.01,
        "qty_step": 0.1,
        "minimum_notional": 5.0,
    }
    ev = evaluate_instrument(row, as_of_ms=as_of)
    blocked = (not guard["ok"]) and (not ev.eligible) and ("FUTURE_OBSERVATION_LEAK" in ev.rejection_reasons)
    disposition = require_attack_disposition(attack_blocked_by_code=blocked, critical_blocker_code=None)
    if not disposition["ok"]:
        return _fail("future_funding_availability", detail="future_funding_survived", evidence={"guard": guard})
    return _ok(
        "future_funding_availability",
        detail="future_funding_availability_blocked",
        evidence={"guard": guard, "reasons": ev.rejection_reasons},
        disposition=disposition["status"],
    )


def scenario_mapping_drift(workdir: Path) -> ScenarioResult:
    as_of = ERA_2024_06_01_MS
    sealed_mapping = "bybit:linear:PEPEUSDT"
    # Attack: later mapping rewrite applied to past research
    drift = detect_mapping_drift(
        sealed_mapping=sealed_mapping,
        observed_mapping="bybit:linear:1000PEPEUSDT",
        as_of_ms=as_of,
        observation_ms=ERA_2025_03_01_MS,
    )
    row = {
        "symbol": "PEPEUSDT",
        "listing_ms": 1_704_067_200_000,
        "observation_ms": as_of,
        "symbol_mapping": sealed_mapping,
        "contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "contract_specification": {},
        "minimum_notional": 5.0,
        "tick_size": 0.0000001,
        "qty_step": 100.0,
        "liquidity_score": 0.55,
        "funding_available": True,
    }
    seal = seal_instrument_observation(row, as_of_ms=as_of)
    attacked = copy.deepcopy(row)
    attacked["symbol_mapping"] = "bybit:linear:1000PEPEUSDT"
    attacked["observation_ms"] = ERA_2025_03_01_MS
    verify = verify_instrument_seal(attacked, as_of_ms=as_of, expected_seal=seal["seal"])
    blocked = (not drift["ok"]) and (not verify["ok"])
    disposition = require_attack_disposition(attack_blocked_by_code=blocked, critical_blocker_code=None)
    if not disposition["ok"]:
        return _fail("mapping_drift", detail="mapping_drift_survived", evidence={"drift": drift})
    return _ok(
        "mapping_drift",
        detail="mapping_drift_blocked",
        evidence={"drift": drift, "seal_verify": verify},
        disposition=disposition["status"],
    )


def scenario_min_notional_drift(workdir: Path) -> ScenarioResult:
    as_of = ERA_2024_06_01_MS
    sealed = 5.0
    # Attack: apply today's higher min notional to past sizing / eligibility
    drift = detect_min_notional_drift(
        sealed_min_notional=sealed,
        observed_min_notional=50.0,
        as_of_ms=as_of,
        observation_ms=ERA_2025_03_01_MS,
    )
    row = {
        "symbol": "BTCUSDT",
        "listing_ms": 1_577_836_800_000,
        "observation_ms": as_of,
        "symbol_mapping": "bybit:linear:BTCUSDT",
        "contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "contract_specification": {"minimum_notional": sealed},
        "minimum_notional": sealed,
        "tick_size": 0.1,
        "qty_step": 0.001,
        "liquidity_score": 0.99,
        "funding_available": True,
    }
    seal = seal_instrument_observation(row, as_of_ms=as_of)
    attacked = copy.deepcopy(row)
    attacked["minimum_notional"] = 50.0
    attacked["contract_specification"] = {"minimum_notional": 50.0}
    attacked["observation_ms"] = ERA_2025_03_01_MS
    verify = verify_instrument_seal(attacked, as_of_ms=as_of, expected_seal=seal["seal"])
    blocked = (not drift["ok"]) and (not verify["ok"])
    disposition = require_attack_disposition(attack_blocked_by_code=blocked, critical_blocker_code=None)
    if not disposition["ok"]:
        return _fail("min_notional_drift", detail="min_notional_drift_survived", evidence={"drift": drift})
    return _ok(
        "min_notional_drift",
        detail="min_notional_drift_blocked",
        evidence={"drift": drift, "seal_verify": verify},
        disposition=disposition["status"],
    )


SCENARIO_FNS: dict[str, Callable[[Path], ScenarioResult]] = {
    "survivorship_bias": scenario_survivorship_bias,
    "listing_date_leakage": scenario_listing_date_leakage,
    "delisting_leakage": scenario_delisting_leakage,
    "rename_leakage": scenario_rename_leakage,
    "contract_spec_changes": scenario_contract_spec_changes,
    "today_universe_substitution": scenario_today_universe_substitution,
    "future_liquidity_leakage": scenario_future_liquidity_leakage,
    "future_funding_availability": scenario_future_funding_availability,
    "mapping_drift": scenario_mapping_drift,
    "min_notional_drift": scenario_min_notional_drift,
}


def run_all_scenarios(workdir: Path) -> list[ScenarioResult]:
    workdir.mkdir(parents=True, exist_ok=True)
    results: list[ScenarioResult] = []
    for sid in ATTACK_SCENARIO_IDS:
        fn = SCENARIO_FNS[sid]
        results.append(fn(workdir / sid))
    return results


def run_production_adversarial_bridge() -> dict[str, Any]:
    """Reuse V13-D adversarial suite as production integrity bridge (fixture control)."""
    suite = run_adversarial_suite()
    return {
        "fixture_id": "adversarial_suite_reuse",
        "passed": bool(suite.get("all_pass")),
        "evidence_class": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
        "suite": suite,
    }
