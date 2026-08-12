"""Offline benchmark interface — contract only; no formal WF / untouched OOS."""
from __future__ import annotations

from typing import Any

from backend.nexus_training_dataset_compiler.constants import (
    RESERVED_SPLITS,
    TARGET_LABELS,
    TRAINABLE_SPLITS,
)
from backend.nexus_training_dataset_compiler.contamination import (
    ContaminationError,
    assert_trainable_access,
    filter_trainable,
)
from backend.nexus_training_dataset_compiler.contracts import BenchmarkRequest, CompiledSample
from backend.nexus_training_dataset_compiler.compiler import compile_all_samples


class BenchmarkInterfaceError(Exception):
    """Fail-closed offline benchmark rejection."""


ALLOWED_OFFLINE_METRICS = frozenset(
    {
        "log_loss",
        "brier",
        "accuracy",
        "mae",
        "spearman_rank",
        "calibration_ece",
        "abstention_rate",
        "confusion_trace",
    }
)


def build_benchmark_request(
    *,
    benchmark_id: str,
    target_label: str,
    metric_names: tuple[str, ...] | list[str],
    allowed_splits: tuple[str, ...] | list[str] | None = None,
) -> BenchmarkRequest:
    label = str(target_label).strip().upper()
    if label not in TARGET_LABELS:
        raise BenchmarkInterfaceError(f"unsupported_target:{label}")
    splits = tuple(allowed_splits) if allowed_splits is not None else tuple(sorted(TRAINABLE_SPLITS))
    for s in splits:
        if s in RESERVED_SPLITS:
            raise BenchmarkInterfaceError(f"reserved_split_in_benchmark:{s}")
        try:
            assert_trainable_access(s, purpose="offline_benchmark")
        except ContaminationError as exc:
            raise BenchmarkInterfaceError(str(exc)) from exc
    metrics = tuple(str(m).strip().lower() for m in metric_names)
    if not metrics:
        raise BenchmarkInterfaceError("metrics_empty")
    bad = [m for m in metrics if m not in ALLOWED_OFFLINE_METRICS]
    if bad:
        raise BenchmarkInterfaceError(f"unknown_metrics:{bad}")
    banned_tokens = ("walk_forward", "oos", "mainnet", "promotion", "real_money")
    bid = benchmark_id.lower()
    if any(tok in bid for tok in banned_tokens):
        raise BenchmarkInterfaceError(f"benchmark_id_implies_banned_stage:{benchmark_id}")
    return BenchmarkRequest(
        benchmark_id=benchmark_id,
        allowed_splits=splits,
        metric_names=metrics,
        target_label=label,
    )


def select_benchmark_rows(
    request: BenchmarkRequest,
    samples: list[CompiledSample] | None = None,
) -> list[CompiledSample]:
    rows = samples if samples is not None else compile_all_samples()
    trainable = filter_trainable(rows)
    allowed = set(request.allowed_splits)
    selected = [
        s
        for s in trainable
        if s.split in allowed and s.target_label == request.target_label
    ]
    for s in selected:
        if s.split in RESERVED_SPLITS:
            raise BenchmarkInterfaceError(f"reserved_row_selected:{s.sample_id}")
    return selected


def run_offline_benchmark(
    request: BenchmarkRequest,
    samples: list[CompiledSample] | None = None,
) -> dict[str, Any]:
    """Execute offline-only stub evaluation. Never claims WF/OOS/qualification."""
    selected = select_benchmark_rows(request, samples=samples)
    metric_stub = {m: None for m in request.metric_names}
    return {
        "schema": "v17_h_offline_benchmark_result",
        "benchmark_id": request.benchmark_id,
        "target_label": request.target_label,
        "allowed_splits": list(request.allowed_splits),
        "row_count": len(selected),
        "sample_ids": [s.sample_id for s in selected],
        "metrics": metric_stub,
        "status": "INTERFACE_READY",
        "formal_walk_forward_executed": False,
        "untouched_oos_executed": False,
        "oos_consumed": False,
        "qualification_claimed": False,
        "promotion_claimed": False,
        "offline_only": True,
        "request": request.to_public_dict(),
    }


def refuse_formal_walk_forward() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "FORMAL_WALK_FORWARD",
        "reason": "FORMAL_WF_BANNED_V17_H_COMPILER_ONLY",
    }


def refuse_untouched_oos() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "UNTOUCHED_OOS",
        "reason": "UNTOUCHED_OOS_BANNED_V17_H_COMPILER_ONLY",
    }


def refuse_real_promotion() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "REAL_PROMOTION",
        "reason": "REAL_PROMOTION_BANNED_V17_H_COMPILER_ONLY",
    }


def refuse_real_lesson_activation() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "REAL_LESSON_ACTIVATION",
        "reason": "REAL_LESSON_ACTIVATION_BANNED_V17_H_COMPILER_ONLY",
    }
