"""Negative / attack-path tests for V17-H Training Dataset Compiler."""
from __future__ import annotations

import pytest

from backend.nexus_training_dataset_compiler.benchmark import (
    BenchmarkInterfaceError,
    build_benchmark_request,
)
from backend.nexus_training_dataset_compiler.compiler import DatasetCompileError, compile_sample
from backend.nexus_training_dataset_compiler.contamination import (
    ContaminationError,
    assert_consumer_topology,
    assert_trainable_access,
)
from backend.nexus_training_dataset_compiler.contracts import ConsumerPlan
from backend.nexus_training_dataset_compiler.fixtures import RAW_FIXTURES


def test_rejects_llm_sole_tick_consumer() -> None:
    with pytest.raises(ContaminationError):
        assert_consumer_topology(
            ConsumerPlan(
                numeric_stat_models=(),
                llm_reasoners=("llm_only",),
                tick_primary_consumer="llm_only",
            )
        )


def test_rejects_reserved_train_access() -> None:
    for split in (
        "WALK_FORWARD_RESERVED",
        "OOS_RESERVED",
        "SHADOW",
        "DEMO",
        "REAL_PRIVATE",
    ):
        with pytest.raises(ContaminationError):
            assert_trainable_access(split, purpose="train")


def test_rejects_lookahead_compile() -> None:
    base = RAW_FIXTURES[0]
    dirty = type(base)(
        sample_id="ATK_LOOKAHEAD",
        symbol=base.symbol,
        ts_ms=base.ts_ms,
        feature_cutoff_ms=base.label_available_ms + 1,
        label_available_ms=base.label_available_ms,
        target_label=base.target_label,
        features=dict(base.features),
        label_payload=dict(base.label_payload),
        provenance=base.provenance,
        consumer_plan=base.consumer_plan,
        declared_split="DEVELOPMENT",
    )
    with pytest.raises(DatasetCompileError):
        compile_sample(dirty)


def test_rejects_benchmark_on_reserved_split() -> None:
    with pytest.raises(BenchmarkInterfaceError):
        build_benchmark_request(
            benchmark_id="bad_bench",
            target_label="REGIME",
            metric_names=["log_loss"],
            allowed_splits=["WALK_FORWARD_RESERVED"],
        )


def test_rejects_benchmark_id_implying_wf() -> None:
    with pytest.raises(BenchmarkInterfaceError):
        build_benchmark_request(
            benchmark_id="formal_walk_forward_run",
            target_label="REGIME",
            metric_names=["log_loss"],
        )
