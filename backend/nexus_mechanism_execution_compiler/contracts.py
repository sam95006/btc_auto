"""Executor contract types for V15-B Mechanism Execution Compiler."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class InputContract:
    required_fields: tuple[str, ...]
    pit_semantics: str
    data_lineage: str
    as_of_rule: str


@dataclass(frozen=True, slots=True)
class FeatureContract:
    primary_feature: str
    secondary_feature: str
    horizon_bars: int
    hold_bars: int


@dataclass(frozen=True, slots=True)
class SignalContract:
    signal_kind: str
    direction_mode: str
    lookahead_forbidden: bool
    future_bar_reference_allowed: bool


@dataclass(frozen=True, slots=True)
class CostDependency:
    cost_sensitivity: str
    capacity_assumptions: str
    cost_authority: str
    cost_components_required: tuple[str, ...]
    spread_impact_gate: bool


@dataclass(frozen=True, slots=True)
class RiskCompatibility:
    risk_profile: str
    invalidating_conditions: tuple[str, ...]
    compatible: bool
    control_overlay_only: bool
    max_leverage_dev: float
    position_notional_cap_dev: float


@dataclass(frozen=True, slots=True)
class DeterministicReplaySpec:
    replay_seed: int
    digest_algorithm: str
    requires_identical_pass_digests: bool


@dataclass(frozen=True, slots=True)
class NegativeTestSpec:
    test_id: str
    rejects: str
    assertion: str


@dataclass(frozen=True, slots=True)
class EconomicRationaleLinkage:
    mechanism_id: str
    economic_rationale: str
    rationale_sha256: str
    source_lane: str


@dataclass(frozen=True, slots=True)
class ExecutorContract:
    executor_id: str
    mechanism_id: str
    family: str
    economic_rationale: str
    input_contract: InputContract
    feature_contract: FeatureContract
    signal_contract: SignalContract
    entry_hypothesis: str
    exit_hypothesis: str
    failure_condition: str
    cost_dependency: CostDependency
    risk_compatibility: RiskCompatibility
    deterministic_replay: DeterministicReplaySpec
    negative_test: NegativeTestSpec
    economic_rationale_linkage: EconomicRationaleLinkage
    source_lane: str
    catalog_version: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "executor_id": self.executor_id,
            "mechanism_id": self.mechanism_id,
            "family": self.family,
            "economic_rationale": self.economic_rationale,
            "input_contract": asdict(self.input_contract),
            "feature_contract": asdict(self.feature_contract),
            "signal_contract": asdict(self.signal_contract),
            "entry_hypothesis": self.entry_hypothesis,
            "exit_hypothesis": self.exit_hypothesis,
            "failure_condition": self.failure_condition,
            "cost_dependency": {
                **asdict(self.cost_dependency),
                "cost_components_required": list(self.cost_dependency.cost_components_required),
            },
            "risk_compatibility": {
                **asdict(self.risk_compatibility),
                "invalidating_conditions": list(self.risk_compatibility.invalidating_conditions),
            },
            "deterministic_replay": asdict(self.deterministic_replay),
            "negative_test": asdict(self.negative_test),
            "economic_rationale_linkage": asdict(self.economic_rationale_linkage),
            "source_lane": self.source_lane,
            "catalog_version": self.catalog_version,
        }
