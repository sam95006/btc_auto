"""Compile V14-C semantic mechanisms into V15-B executor contracts."""
from __future__ import annotations

import hashlib
from typing import Any

from backend.nexus_mechanism_execution_compiler.constants import (
    CANONICAL_COST_AUTHORITY,
    CATALOG_VERSION,
    EXPECTED_MECHANISM_COUNT,
    FAMILY_TO_RISK_PROFILE,
    MIN_EXECUTOR_COUNT,
    RANDOM_SEED,
    REQUIRED_EXECUTOR_FIELDS,
    SOURCE_LANE,
)
from backend.nexus_mechanism_execution_compiler.contracts import (
    CostDependency,
    DeterministicReplaySpec,
    EconomicRationaleLinkage,
    ExecutorContract,
    FeatureContract,
    InputContract,
    NegativeTestSpec,
    RiskCompatibility,
    SignalContract,
)
from backend.nexus_mechanism_lab_v4.catalog import SPECS, MechanismSpec, assert_catalog_distinct


COST_COMPONENTS = (
    "entry_fee",
    "exit_fee",
    "spread_cost",
    "slippage_cost",
    "market_impact_approximation",
)


def _rationale_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _risk_profile(spec: MechanismSpec) -> str:
    if spec.signal_kind == "regime_transition_shutdown":
        return "CONTROL_OVERLAY"
    return FAMILY_TO_RISK_PROFILE.get(spec.family, "FLOW_MICROSTRUCTURE")


def _spread_impact_gate(spec: MechanismSpec) -> bool:
    sens = spec.cost_sensitivity.lower()
    return "high" in sens or spec.family in {"SPREAD_SHOCK", "LIQUIDITY_WITHDRAWAL", "MARKET_IMPACT_ASYMMETRY"}


def compile_one(spec: MechanismSpec) -> ExecutorContract:
    """Compile a single V14-C mechanism into a distinct executor contract."""
    executor_id = f"EXEC_{spec.mechanism_id}"
    control = spec.signal_kind == "regime_transition_shutdown"
    profile = _risk_profile(spec)
    rationale_hash = _rationale_sha(spec.economic_rationale)
    return ExecutorContract(
        executor_id=executor_id,
        mechanism_id=spec.mechanism_id,
        family=spec.family,
        economic_rationale=spec.economic_rationale,
        input_contract=InputContract(
            required_fields=tuple(spec.required_data),
            pit_semantics=spec.pit_semantics,
            data_lineage="SYNTHETIC_DEVELOPMENT_FIXTURE",
            as_of_rule="exchange_ts_ms<=as_of_ms AND receive_ts_ms<=as_of_ms",
        ),
        feature_contract=FeatureContract(
            primary_feature=spec.primary_feature,
            secondary_feature=spec.secondary_feature,
            horizon_bars=spec.horizon_bars,
            hold_bars=spec.hold_bars,
        ),
        signal_contract=SignalContract(
            signal_kind=spec.signal_kind,
            direction_mode=spec.direction_mode,
            lookahead_forbidden=True,
            future_bar_reference_allowed=False,
        ),
        entry_hypothesis=spec.entry_hypothesis,
        exit_hypothesis=spec.exit_hypothesis,
        failure_condition=spec.failure_hypothesis,
        cost_dependency=CostDependency(
            cost_sensitivity=spec.cost_sensitivity,
            capacity_assumptions=spec.capacity_assumptions,
            cost_authority=CANONICAL_COST_AUTHORITY,
            cost_components_required=COST_COMPONENTS,
            spread_impact_gate=_spread_impact_gate(spec),
        ),
        risk_compatibility=RiskCompatibility(
            risk_profile=profile,
            invalidating_conditions=tuple(spec.invalidating_conditions),
            compatible=not control,
            control_overlay_only=control,
            max_leverage_dev=1.0,
            position_notional_cap_dev=1000.0,
        ),
        deterministic_replay=DeterministicReplaySpec(
            replay_seed=RANDOM_SEED,
            digest_algorithm="sha256",
            requires_identical_pass_digests=True,
        ),
        negative_test=NegativeTestSpec(
            test_id=f"NEG_{spec.mechanism_id}",
            rejects="param_clone_collapse_or_lookahead_or_qualification_claim",
            assertion=(
                "Executor must reject cosmetic param-only clones, future-bar peeking, "
                "and any qualification/profitability claim vocabulary."
            ),
        ),
        economic_rationale_linkage=EconomicRationaleLinkage(
            mechanism_id=spec.mechanism_id,
            economic_rationale=spec.economic_rationale,
            rationale_sha256=rationale_hash,
            source_lane=SOURCE_LANE,
        ),
        source_lane=SOURCE_LANE,
        catalog_version=CATALOG_VERSION,
    )


def assert_executors_distinct(contracts: list[ExecutorContract]) -> None:
    if len(contracts) < MIN_EXECUTOR_COUNT:
        raise AssertionError(f"executor_count_below_min:{len(contracts)}<{MIN_EXECUTOR_COUNT}")
    ids = [c.executor_id for c in contracts]
    mechs = [c.mechanism_id for c in contracts]
    if len(ids) != len(set(ids)):
        raise AssertionError("duplicate_executor_id")
    if len(mechs) != len(set(mechs)):
        raise AssertionError("duplicate_mechanism_id")
    rationales = [c.economic_rationale for c in contracts]
    if len(rationales) != len(set(rationales)):
        raise AssertionError("cosmetic_clone_rationale_detected")
    signal_keys = [
        (
            c.signal_contract.signal_kind,
            c.feature_contract.primary_feature,
            c.feature_contract.secondary_feature,
            c.signal_contract.direction_mode,
        )
        for c in contracts
    ]
    if len(signal_keys) != len(set(signal_keys)):
        raise AssertionError("cosmetic_clone_signal_contract_detected")
    # Distinct hold/horizon alone must not differentiate identical signal+feature+rationale.
    by_core: dict[tuple[str, str, str], list[ExecutorContract]] = {}
    for c in contracts:
        key = (
            c.signal_contract.signal_kind,
            c.feature_contract.primary_feature,
            c.feature_contract.secondary_feature,
        )
        by_core.setdefault(key, []).append(c)
    for key, group in by_core.items():
        if len(group) > 1:
            dirs = {g.signal_contract.direction_mode for g in group}
            rats = {g.economic_rationale for g in group}
            if len(dirs) == 1 and len(rats) == 1:
                raise AssertionError(f"param_only_variants:{key}")


def compile_all_executors() -> list[ExecutorContract]:
    """Compile every V14-C mechanism into a one-to-one executor (no collapse)."""
    assert_catalog_distinct()
    if len(SPECS) != EXPECTED_MECHANISM_COUNT:
        raise AssertionError(
            f"unexpected_source_mechanism_count:{len(SPECS)}!={EXPECTED_MECHANISM_COUNT}"
        )
    contracts = [compile_one(spec) for spec in SPECS]
    assert_executors_distinct(contracts)
    for c in contracts:
        public = c.to_public_dict()
        for field in REQUIRED_EXECUTOR_FIELDS:
            if field not in public or public[field] in (None, "", [], {}):
                raise AssertionError(f"missing_required_field:{c.executor_id}:{field}")
    return contracts


def executor_catalog() -> list[dict[str, Any]]:
    return [c.to_public_dict() for c in compile_all_executors()]
