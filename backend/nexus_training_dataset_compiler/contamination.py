"""Contamination guard — fail-closed leak detection for V17-H."""
from __future__ import annotations

from typing import Any

from backend.nexus_training_dataset_compiler.constants import (
    RESERVED_SPLITS,
    TARGET_LABELS,
    TRAINABLE_SPLITS,
)
from backend.nexus_training_dataset_compiler.contracts import CompiledSample, ConsumerPlan


class ContaminationError(Exception):
    """Raised when a contamination vector is detected."""


def assert_no_lookahead(sample: CompiledSample | dict[str, Any]) -> None:
    if isinstance(sample, CompiledSample):
        feature_cutoff = sample.feature_cutoff_ms
        label_available = sample.label_available_ms
        ts_ms = sample.ts_ms
    else:
        feature_cutoff = int(sample["feature_cutoff_ms"])
        label_available = int(sample["label_available_ms"])
        ts_ms = int(sample["ts_ms"])
    if feature_cutoff > label_available:
        raise ContaminationError("lookahead_feature_after_label")
    if feature_cutoff > ts_ms:
        raise ContaminationError("lookahead_feature_after_event_ts")


def assert_consumer_topology(plan: ConsumerPlan | dict[str, Any]) -> None:
    if isinstance(plan, ConsumerPlan):
        numeric = plan.numeric_stat_models
        llm = plan.llm_reasoners
        primary = plan.tick_primary_consumer
    else:
        numeric = tuple(plan.get("numeric_stat_models") or ())
        llm = tuple(plan.get("llm_reasoners") or ())
        primary = str(plan.get("tick_primary_consumer") or "")
    if not numeric:
        raise ContaminationError("numeric_stat_model_required")
    if primary not in numeric:
        raise ContaminationError("tick_primary_must_be_numeric_stat")
    if primary.startswith("LLM") or primary in llm:
        raise ContaminationError("llm_sole_or_primary_tick_consumer_banned")
    if not numeric and llm:
        raise ContaminationError("llm_sole_tick_consumer_banned")


def assert_trainable_access(split: str, *, purpose: str = "train") -> None:
    if split in RESERVED_SPLITS:
        raise ContaminationError(f"reserved_split_access_banned:{purpose}:{split}")
    if split not in TRAINABLE_SPLITS:
        raise ContaminationError(f"unknown_or_banned_split:{purpose}:{split}")


def assert_label_only_target(target_label: str) -> None:
    label = str(target_label).strip().upper()
    if label not in TARGET_LABELS:
        raise ContaminationError(f"unsupported_target_label:{label}")


def assert_no_cross_split_id_collision(samples: list[CompiledSample]) -> None:
    seen: dict[str, str] = {}
    for s in samples:
        prev = seen.get(s.sample_id)
        if prev is not None and prev != s.split:
            raise ContaminationError(f"cross_split_id_collision:{s.sample_id}:{prev}->{s.split}")
        seen[s.sample_id] = s.split


def assert_no_reserved_in_training_set(samples: list[CompiledSample]) -> None:
    for s in samples:
        if s.trainable and s.split in RESERVED_SPLITS:
            raise ContaminationError(f"reserved_marked_trainable:{s.sample_id}:{s.split}")
        if s.split in RESERVED_SPLITS and s.trainable:
            raise ContaminationError(f"reserved_trainable_flag:{s.sample_id}")


def filter_trainable(samples: list[CompiledSample]) -> list[CompiledSample]:
    """Return only DEVELOPMENT/VALIDATION rows; refuse if any reserved sneaks in."""
    out: list[CompiledSample] = []
    for s in samples:
        if s.split in RESERVED_SPLITS:
            continue
        assert_trainable_access(s.split, purpose="filter_trainable")
        if not s.trainable:
            raise ContaminationError(f"trainable_split_not_flagged:{s.sample_id}")
        out.append(s)
    return out


def guard_compiled_batch(samples: list[CompiledSample]) -> dict[str, Any]:
    """Run full contamination guard over a compiled batch. Fail-closed."""
    assert_no_cross_split_id_collision(samples)
    assert_no_reserved_in_training_set(samples)
    for s in samples:
        assert_no_lookahead(s)
        assert_consumer_topology(s.consumer_plan)
        assert_label_only_target(s.target_label)
        if s.trainable:
            assert_trainable_access(s.split, purpose="batch_guard")
        elif s.split not in RESERVED_SPLITS:
            raise ContaminationError(f"non_trainable_non_reserved:{s.sample_id}:{s.split}")
    trainable = filter_trainable(samples)
    return {
        "ok": True,
        "sample_count": len(samples),
        "trainable_count": len(trainable),
        "reserved_count": sum(1 for s in samples if s.split in RESERVED_SPLITS),
        "contamination_survivors": 0,
    }
