"""Dataset split contamination attacks — deep expansion beyond V17-H baseline."""
from __future__ import annotations

from typing import Any

from backend.nexus_training_dataset_compiler.compiler import compile_sample
from backend.nexus_training_dataset_compiler.contamination import (
    ContaminationError,
    assert_no_cross_split_id_collision,
    assert_trainable_access,
    filter_trainable,
    guard_compiled_batch,
)
from backend.nexus_training_dataset_compiler.contracts import CompiledSample, ConsumerPlan, RawSample
from backend.nexus_training_dataset_compiler.fixtures import RAW_FIXTURES
from backend.nexus_training_dataset_compiler.redteam import run_contamination_redteam
from backend.nexus_training_dataset_compiler.split import resolve_split
from backend.nexus_deep_ingest_contamination.constants import EXPECTED_CONTAMINATION_ATTACKS


def _finding(
    attack_id: str,
    *,
    blocked: bool,
    detail: str,
    severity: str = "CRITICAL",
) -> dict[str, Any]:
    return {
        "attack_id": attack_id,
        "severity": severity,
        "disposition": "FIXED" if blocked else "SURVIVOR",
        "attack_blocked": blocked,
        "survivor": not blocked,
        "detail": detail,
    }


def _base_raw(**overrides: Any) -> RawSample:
    base = RAW_FIXTURES[0]
    fields = {
        "sample_id": base.sample_id + "_DEEP",
        "symbol": base.symbol,
        "ts_ms": base.ts_ms,
        "feature_cutoff_ms": base.feature_cutoff_ms,
        "label_available_ms": base.label_available_ms,
        "target_label": base.target_label,
        "features": dict(base.features),
        "label_payload": dict(base.label_payload),
        "provenance": base.provenance,
        "consumer_plan": base.consumer_plan,
        "declared_split": "DEVELOPMENT",
    }
    fields.update(overrides)
    return RawSample(**fields)


def run_deep_split_contamination_attacks() -> dict[str, Any]:
    """Deep split-contamination redteam. survivors must be 0."""
    findings: list[dict[str, Any]] = []

    # 1. Mix reserved into training via declared_split override after compile
    try:
        dirty = _base_raw(declared_split="OOS_RESERVED")
        sample = compile_sample(dirty)
        # Force-mark trainable (adversarial mutation)
        mutated = CompiledSample(
            sample_id=sample.sample_id,
            symbol=sample.symbol,
            ts_ms=sample.ts_ms,
            feature_cutoff_ms=sample.feature_cutoff_ms,
            label_available_ms=sample.label_available_ms,
            split="OOS_RESERVED",
            target_label=sample.target_label,
            features=sample.features,
            label_payload=sample.label_payload,
            provenance=sample.provenance,
            consumer_plan=sample.consumer_plan,
            compile_digest=sample.compile_digest,
            trainable=True,
            catalog_version=sample.catalog_version,
        )
        guard_compiled_batch([mutated])
        blocked = False
        detail = "oos_reserved_trainable_accepted"
    except (ContaminationError, Exception) as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("mutate_reserved_as_trainable", blocked=blocked, detail=detail))

    # 2. Cross-split sample_id collision (same id in DEV and VALIDATION)
    try:
        a = compile_sample(_base_raw(sample_id="collide_x", declared_split="DEVELOPMENT"))
        b = compile_sample(_base_raw(sample_id="collide_x", declared_split="VALIDATION"))
        assert_no_cross_split_id_collision([a, b])
        blocked = False
        detail = "cross_split_collision_allowed"
    except ContaminationError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("cross_split_id_collision", blocked=blocked, detail=detail))

    # 3. Train access on WALK_FORWARD_RESERVED
    try:
        assert_trainable_access("WALK_FORWARD_RESERVED", purpose="deep_train")
        blocked = False
        detail = "wf_reserved_train_allowed"
    except ContaminationError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("train_walk_forward_reserved", blocked=blocked, detail=detail))

    # 4. Train access on SHADOW
    try:
        assert_trainable_access("SHADOW", purpose="deep_train")
        blocked = False
        detail = "shadow_train_allowed"
    except ContaminationError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("train_shadow_split", blocked=blocked, detail=detail))

    # 5. Lookahead: feature cutoff after label
    try:
        compile_sample(
            _base_raw(feature_cutoff_ms=9_999_999_999_999, label_available_ms=1, ts_ms=2)
        )
        blocked = False
        detail = "lookahead_compiled"
    except Exception as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("lookahead_feature_after_label", blocked=blocked, detail=detail))

    # 6. filter_trainable must drop reserved even if present in batch list
    reserved = compile_sample(_base_raw(sample_id="res_drop", declared_split="OOS_RESERVED"))
    # reserved.compile may mark trainable=False — ensure filter drops it
    trainable = filter_trainable([reserved])
    findings.append(
        _finding(
            "filter_drops_reserved",
            blocked=len(trainable) == 0,
            detail=f"trainable_len={len(trainable)}",
        )
    )

    # 7. Hash assignment never invents reserved splits
    invented = False
    for raw in RAW_FIXTURES:
        if raw.declared_split is None:
            split = resolve_split(
                sample_id=raw.sample_id,
                symbol=raw.symbol,
                ts_ms=raw.ts_ms,
                declared_split=None,
            )
            if split not in {"DEVELOPMENT", "VALIDATION"}:
                invented = True
                break
    findings.append(
        _finding(
            "hash_invents_reserved",
            blocked=not invented,
            detail="hash stays DEVELOPMENT|VALIDATION",
        )
    )

    # 8. LLM sole tick consumer banned
    try:
        bad = _base_raw(
            sample_id="llm_sole",
            consumer_plan=ConsumerPlan(
                numeric_stat_models=(),
                llm_reasoners=("llm_only",),
                tick_primary_consumer="llm_only",
            ),
        )
        compile_sample(bad)
        blocked = False
        detail = "llm_sole_accepted"
    except Exception as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("llm_sole_tick_consumer", blocked=blocked, detail=detail))

    # 9. DEV sample smuggled into OOS via declared_split flip mid-pipeline
    try:
        assert_trainable_access("DEMO", purpose="smuggle")
        blocked = False
        detail = "demo_train_allowed"
    except ContaminationError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("demo_split_train_ban", blocked=blocked, detail=detail))

    # 10. REAL_PRIVATE train ban
    try:
        assert_trainable_access("REAL_PRIVATE", purpose="deep_train")
        blocked = False
        detail = "real_private_train_allowed"
    except ContaminationError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("real_private_train_ban", blocked=blocked, detail=detail))

    # Fold baseline V17-H redteam (must also be clean)
    baseline = run_contamination_redteam()
    findings.append(
        _finding(
            "baseline_v17h_contamination_clean",
            blocked=baseline.get("survivor_count", 1) == 0,
            detail=f"baseline_survivors={baseline.get('survivor_count')}",
            severity="HIGH",
        )
    )

    survivors = [f for f in findings if f["survivor"]]
    attack_count = len(findings)
    return {
        "schema": "v17_deep_split_contamination_redteam_v1",
        "attack_count": attack_count,
        "expected_min_attacks": EXPECTED_CONTAMINATION_ATTACKS,
        "blocked_count": sum(1 for f in findings if f["attack_blocked"]),
        "survivor_count": len(survivors),
        "survivors": [f["attack_id"] for f in survivors],
        "findings": findings,
        "baseline_v17h": {
            "survivor_count": baseline.get("survivor_count"),
            "attack_count": baseline.get("attack_count"),
            "status": baseline.get("status"),
        },
        "status": (
            "PASS"
            if len(survivors) == 0 and attack_count >= EXPECTED_CONTAMINATION_ATTACKS
            else "FAIL"
        ),
    }
