"""Fail-closed compile of raw samples → typed CompiledSample rows."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_training_dataset_compiler.constants import (
    CATALOG_VERSION,
    EXPECTED_FIXTURE_SAMPLES,
    HARD_BANS,
    MIN_FIXTURE_SAMPLES,
    REQUIRED_FALSE_FLAGS,
    REQUIRED_SAMPLE_FIELDS,
    RESERVED_SPLITS,
    TARGET_LABELS,
)
from backend.nexus_training_dataset_compiler.contamination import (
    ContaminationError,
    assert_consumer_topology,
    assert_label_only_target,
    assert_no_lookahead,
    filter_trainable,
    guard_compiled_batch,
)
from backend.nexus_training_dataset_compiler.contracts import CompiledSample, RawSample
from backend.nexus_training_dataset_compiler.fixtures import RAW_FIXTURES
from backend.nexus_training_dataset_compiler.split import (
    SplitAssignmentError,
    assert_split_partition_integrity,
    is_trainable,
    resolve_split,
)


class DatasetCompileError(Exception):
    """Fail-closed compile rejection."""


def _digest(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def compile_sample(raw: RawSample) -> CompiledSample:
    """Compile one raw sample. Fail-closed on schema / contamination issues."""
    if not raw.sample_id or not str(raw.sample_id).strip():
        raise DatasetCompileError("sample_id_missing")
    if not raw.symbol:
        raise DatasetCompileError("symbol_missing")
    if raw.ts_ms <= 0:
        raise DatasetCompileError("ts_ms_invalid")
    if not isinstance(raw.features, dict) or not raw.features:
        raise DatasetCompileError("features_empty")
    if not isinstance(raw.label_payload, dict) or not raw.label_payload:
        raise DatasetCompileError("label_payload_empty")

    try:
        assert_label_only_target(raw.target_label)
        assert_consumer_topology(raw.consumer_plan)
        split = resolve_split(
            sample_id=raw.sample_id,
            symbol=raw.symbol,
            ts_ms=raw.ts_ms,
            declared_split=raw.declared_split,
        )
    except (ContaminationError, SplitAssignmentError) as exc:
        raise DatasetCompileError(str(exc)) from exc

    trainable = is_trainable(split)
    compiled = CompiledSample(
        sample_id=raw.sample_id,
        symbol=raw.symbol,
        ts_ms=raw.ts_ms,
        feature_cutoff_ms=raw.feature_cutoff_ms,
        label_available_ms=raw.label_available_ms,
        split=split,
        target_label=str(raw.target_label).strip().upper(),
        features=dict(raw.features),
        label_payload=dict(raw.label_payload),
        provenance=raw.provenance,
        consumer_plan=raw.consumer_plan,
        compile_digest="",  # filled below
        trainable=trainable,
        catalog_version=CATALOG_VERSION,
    )
    try:
        assert_no_lookahead(compiled)
    except ContaminationError as exc:
        raise DatasetCompileError(str(exc)) from exc

    payload = compiled.to_public_dict()
    payload.pop("compile_digest", None)
    digest = _digest(payload)
    return CompiledSample(
        sample_id=compiled.sample_id,
        symbol=compiled.symbol,
        ts_ms=compiled.ts_ms,
        feature_cutoff_ms=compiled.feature_cutoff_ms,
        label_available_ms=compiled.label_available_ms,
        split=compiled.split,
        target_label=compiled.target_label,
        features=compiled.features,
        label_payload=compiled.label_payload,
        provenance=compiled.provenance,
        consumer_plan=compiled.consumer_plan,
        compile_digest=digest,
        trainable=compiled.trainable,
        catalog_version=compiled.catalog_version,
    )


def compile_all_samples(raws: tuple[RawSample, ...] | list[RawSample] | None = None) -> list[CompiledSample]:
    src = list(raws) if raws is not None else list(RAW_FIXTURES)
    out = [compile_sample(r) for r in src]
    assert_split_partition_integrity([s.split for s in out])
    guard_compiled_batch(out)
    return out


def assert_samples_safe(samples: list[CompiledSample]) -> None:
    if len(samples) < MIN_FIXTURE_SAMPLES:
        raise DatasetCompileError(f"sample_count_below_min:{len(samples)}")
    for s in samples:
        row = s.to_public_dict()
        for field in REQUIRED_SAMPLE_FIELDS:
            if field not in row or row[field] in (None, "", {}, []):
                raise DatasetCompileError(f"required_field_missing:{field}:{s.sample_id}")
        if s.target_label not in TARGET_LABELS:
            raise DatasetCompileError(f"bad_target:{s.target_label}")
        if s.consumer_plan.to_public_dict()["llm_sole_tick_consumer"] is not False:
            raise DatasetCompileError("llm_sole_tick_consumer_flag")
        if s.split in RESERVED_SPLITS and s.trainable:
            raise DatasetCompileError(f"reserved_trainable:{s.sample_id}")


def dataset_catalog(samples: list[CompiledSample] | None = None) -> list[dict[str, Any]]:
    rows = samples if samples is not None else compile_all_samples()
    assert_samples_safe(rows)
    return [s.to_public_dict() for s in rows]


def control_flags() -> dict[str, Any]:
    return {k: False for k in REQUIRED_FALSE_FLAGS}


def compile_campaign(*, pass_id: int = 1) -> dict[str, Any]:
    """Offline compile campaign — never runs WF/OOS/promotion/mainnet."""
    samples = compile_all_samples()
    assert_samples_safe(samples)
    trainable = filter_trainable(samples)
    by_split: dict[str, int] = {}
    by_target: dict[str, int] = {}
    for s in samples:
        by_split[s.split] = by_split.get(s.split, 0) + 1
        by_target[s.target_label] = by_target.get(s.target_label, 0) + 1

    digest = _digest(
        {
            "pass_id": pass_id,
            "digests": [s.compile_digest for s in samples],
            "splits": by_split,
        }
    )
    flags = control_flags()
    return {
        "schema": "v17_h_training_dataset_compiler_campaign",
        "pass_id": pass_id,
        "sample_count": len(samples),
        "trainable_count": len(trainable),
        "reserved_count": len(samples) - len(trainable),
        "expected_fixture_samples": EXPECTED_FIXTURE_SAMPLES,
        "by_split": by_split,
        "by_target": by_target,
        "samples": [s.to_public_dict() for s in samples],
        "trainable_sample_ids": [s.sample_id for s in trainable],
        "campaign_digest": digest,
        "hard_bans": sorted(HARD_BANS),
        "labels_only": True,
        "offline_benchmark_interface_ready": True,
        "llm_sole_tick_consumer": False,
        "contamination_survivors": 0,
        **flags,
    }
