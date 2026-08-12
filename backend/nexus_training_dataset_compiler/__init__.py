"""NEXUS V17-H — Training Dataset Compiler.

Compiler + schema + deterministic split + contamination guard +
sample fixture + offline benchmark interface.

Does NOT run formal WF, untouched OOS, real promotion, real Lesson activation,
mainnet, or real-money. LLM is never the sole tick consumer.
"""
from __future__ import annotations

from backend.nexus_training_dataset_compiler.artifacts import (
    build_summary_payload,
    write_immutable_artifacts,
)
from backend.nexus_training_dataset_compiler.benchmark import (
    build_benchmark_request,
    refuse_formal_walk_forward,
    refuse_real_lesson_activation,
    refuse_real_promotion,
    refuse_untouched_oos,
    run_offline_benchmark,
)
from backend.nexus_training_dataset_compiler.compiler import (
    DatasetCompileError,
    assert_samples_safe,
    compile_all_samples,
    compile_campaign,
    compile_sample,
    dataset_catalog,
)
from backend.nexus_training_dataset_compiler.constants import (
    CAMPAIGN_ID,
    DATASET_SPLITS,
    EXPECTED_FIXTURE_SAMPLES,
    HARD_BANS,
    PACKAGE,
    SCHEMA,
    TARGET_LABELS,
    TRAINABLE_SPLITS,
)
from backend.nexus_training_dataset_compiler.contamination import (
    ContaminationError,
    filter_trainable,
    guard_compiled_batch,
)
from backend.nexus_training_dataset_compiler.redteam import run_contamination_redteam
from backend.nexus_training_dataset_compiler.split import assign_trainable_split, resolve_split

__all__ = [
    "CAMPAIGN_ID",
    "DATASET_SPLITS",
    "EXPECTED_FIXTURE_SAMPLES",
    "HARD_BANS",
    "PACKAGE",
    "SCHEMA",
    "TARGET_LABELS",
    "TRAINABLE_SPLITS",
    "ContaminationError",
    "DatasetCompileError",
    "assert_samples_safe",
    "assign_trainable_split",
    "build_benchmark_request",
    "build_summary_payload",
    "compile_all_samples",
    "compile_campaign",
    "compile_sample",
    "dataset_catalog",
    "filter_trainable",
    "guard_compiled_batch",
    "refuse_formal_walk_forward",
    "refuse_real_lesson_activation",
    "refuse_real_promotion",
    "refuse_untouched_oos",
    "resolve_split",
    "run_contamination_redteam",
    "run_offline_benchmark",
    "write_immutable_artifacts",
]
