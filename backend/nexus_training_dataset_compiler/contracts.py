"""Typed contracts for V17-H Training Dataset Compiler."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ConsumerPlan:
    """Tick/feature consumer topology — numeric/stat required; LLM optional reasoner."""

    numeric_stat_models: tuple[str, ...]
    llm_reasoners: tuple[str, ...]
    tick_primary_consumer: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "numeric_stat_models": list(self.numeric_stat_models),
            "llm_reasoners": list(self.llm_reasoners),
            "tick_primary_consumer": self.tick_primary_consumer,
            "llm_sole_tick_consumer": False,
        }


@dataclass(frozen=True, slots=True)
class Provenance:
    source_id: str
    lineage: str
    license_class: str
    synthetic: bool

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RawSample:
    """Pre-compile sample row (fixture or ingest stub)."""

    sample_id: str
    symbol: str
    ts_ms: int
    feature_cutoff_ms: int
    label_available_ms: int
    target_label: str
    features: dict[str, Any]
    label_payload: dict[str, Any]
    provenance: Provenance
    consumer_plan: ConsumerPlan
    declared_split: str | None = None


@dataclass(frozen=True, slots=True)
class CompiledSample:
    """Compiled, split-assigned, contamination-checked training row."""

    sample_id: str
    symbol: str
    ts_ms: int
    feature_cutoff_ms: int
    label_available_ms: int
    split: str
    target_label: str
    features: dict[str, Any]
    label_payload: dict[str, Any]
    provenance: Provenance
    consumer_plan: ConsumerPlan
    compile_digest: str
    trainable: bool
    catalog_version: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "symbol": self.symbol,
            "ts_ms": self.ts_ms,
            "feature_cutoff_ms": self.feature_cutoff_ms,
            "label_available_ms": self.label_available_ms,
            "split": self.split,
            "target_label": self.target_label,
            "features": dict(self.features),
            "label_payload": dict(self.label_payload),
            "provenance": self.provenance.to_public_dict(),
            "consumer_plan": self.consumer_plan.to_public_dict(),
            "compile_digest": self.compile_digest,
            "trainable": self.trainable,
            "catalog_version": self.catalog_version,
            "labels_only": True,
        }


@dataclass(frozen=True, slots=True)
class ContaminationFinding:
    attack_id: str
    severity: str
    blocked: bool
    survivor: bool
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkRequest:
    """Offline benchmark interface request — never executes formal WF/OOS."""

    benchmark_id: str
    allowed_splits: tuple[str, ...]
    metric_names: tuple[str, ...]
    target_label: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "allowed_splits": list(self.allowed_splits),
            "metric_names": list(self.metric_names),
            "target_label": self.target_label,
            "formal_walk_forward": False,
            "untouched_oos": False,
            "offline_only": True,
        }
