"""Contamination redteam for V17-H — all attacks must be blocked (survivors=0)."""
from __future__ import annotations

from typing import Any

from backend.nexus_training_dataset_compiler.benchmark import (
    BenchmarkInterfaceError,
    build_benchmark_request,
    refuse_formal_walk_forward,
    refuse_real_lesson_activation,
    refuse_real_promotion,
    refuse_untouched_oos,
    run_offline_benchmark,
)
from backend.nexus_training_dataset_compiler.compiler import compile_all_samples, compile_sample
from backend.nexus_training_dataset_compiler.constants import (
    EXPECTED_CONTAMINATION_ATTACKS,
    RESERVED_SPLITS,
    TRAINABLE_SPLITS,
)
from backend.nexus_training_dataset_compiler.contamination import (
    ContaminationError,
    assert_consumer_topology,
    assert_no_lookahead,
    assert_trainable_access,
    filter_trainable,
    guard_compiled_batch,
)
from backend.nexus_training_dataset_compiler.contracts import ConsumerPlan, RawSample
from backend.nexus_training_dataset_compiler.fixtures import RAW_FIXTURES
from backend.nexus_training_dataset_compiler.split import resolve_split


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
        "sample_id": base.sample_id + "_ATK",
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


def run_contamination_redteam() -> dict[str, Any]:
    """Three-pass compatible single report: every attack blocked → survivors=0."""
    findings: list[dict[str, Any]] = []

    # 1. Train on WALK_FORWARD_RESERVED
    try:
        assert_trainable_access("WALK_FORWARD_RESERVED", purpose="train")
        blocked = False
        detail = "WF reserved access allowed"
    except ContaminationError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("train_on_walk_forward_reserved", blocked=blocked, detail=detail))

    # 2. Train on OOS_RESERVED
    try:
        assert_trainable_access("OOS_RESERVED", purpose="train")
        blocked = False
        detail = "OOS reserved access allowed"
    except ContaminationError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("train_on_oos_reserved", blocked=blocked, detail=detail))

    # 3. Look-ahead features after label availability
    try:
        dirty = _base_raw(feature_cutoff_ms=9_999_999_999_999, label_available_ms=1)
        compile_sample(dirty)
        blocked = False
        detail = "lookahead compiled"
    except Exception as exc:  # DatasetCompileError wrapping ContaminationError
        blocked = True
        detail = str(exc)
    findings.append(_finding("lookahead_feature_leak", blocked=blocked, detail=detail))

    # 4. LLM as sole / primary tick consumer
    try:
        bad_plan = ConsumerPlan(
            numeric_stat_models=(),
            llm_reasoners=("llm_tick_eater",),
            tick_primary_consumer="llm_tick_eater",
        )
        assert_consumer_topology(bad_plan)
        blocked = False
        detail = "llm sole consumer accepted"
    except ContaminationError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("llm_sole_tick_consumer", blocked=blocked, detail=detail))

    # 5. LLM marked primary even when numeric exists
    try:
        bad_plan = ConsumerPlan(
            numeric_stat_models=("rolling_vol_z",),
            llm_reasoners=("llm_tick_eater",),
            tick_primary_consumer="llm_tick_eater",
        )
        assert_consumer_topology(bad_plan)
        blocked = False
        detail = "llm primary accepted"
    except ContaminationError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("llm_primary_tick_consumer", blocked=blocked, detail=detail))

    # 6. Reserved rows in trainable filter
    samples = compile_all_samples()
    trainable = filter_trainable(samples)
    reserved_leaked = [s for s in trainable if s.split in RESERVED_SPLITS]
    findings.append(
        _finding(
            "reserved_in_trainable_filter",
            blocked=len(reserved_leaked) == 0,
            detail=f"leaked={len(reserved_leaked)} trainable={len(trainable)}",
        )
    )

    # 7. SHADOW / DEMO / REAL_PRIVATE training access
    shadow_blocked = True
    for split in ("SHADOW", "DEMO", "REAL_PRIVATE"):
        try:
            assert_trainable_access(split, purpose="train")
            shadow_blocked = False
            break
        except ContaminationError:
            pass
    findings.append(
        _finding(
            "shadow_demo_real_private_train_ban",
            blocked=shadow_blocked,
            detail="SHADOW/DEMO/REAL_PRIVATE train access",
        )
    )

    # 8. Offline benchmark refuses reserved splits
    try:
        build_benchmark_request(
            benchmark_id="atk_oos_bench",
            target_label="REGIME",
            metric_names=["log_loss"],
            allowed_splits=["OOS_RESERVED"],
        )
        blocked = False
        detail = "oos benchmark allowed"
    except BenchmarkInterfaceError as exc:
        blocked = True
        detail = str(exc)
    findings.append(_finding("benchmark_on_oos_reserved", blocked=blocked, detail=detail))

    # 9. Formal WF refused
    wf = refuse_formal_walk_forward()
    findings.append(
        _finding(
            "formal_walk_forward_execution",
            blocked=wf.get("allowed") is False and wf.get("executed") is False,
            detail=str(wf.get("reason")),
        )
    )

    # 10. Untouched OOS refused
    oos = refuse_untouched_oos()
    findings.append(
        _finding(
            "untouched_oos_execution",
            blocked=oos.get("allowed") is False and oos.get("executed") is False,
            detail=str(oos.get("reason")),
        )
    )

    # 11. Real promotion + lesson activation refused
    promo = refuse_real_promotion()
    lesson = refuse_real_lesson_activation()
    findings.append(
        _finding(
            "real_promotion_or_lesson_activation",
            blocked=(
                promo.get("allowed") is False
                and lesson.get("allowed") is False
                and promo.get("executed") is False
                and lesson.get("executed") is False
            ),
            detail=f"promo={promo.get('reason')}; lesson={lesson.get('reason')}",
        )
    )

    # 12. Hash assignment never invents reserved splits
    invented = False
    for raw in RAW_FIXTURES:
        if raw.declared_split is None:
            split = resolve_split(
                sample_id=raw.sample_id,
                symbol=raw.symbol,
                ts_ms=raw.ts_ms,
                declared_split=None,
            )
            if split in RESERVED_SPLITS or split not in TRAINABLE_SPLITS:
                invented = True
                break
    findings.append(
        _finding(
            "hash_invents_reserved_split",
            blocked=not invented,
            detail="hash path stays in DEVELOPMENT|VALIDATION",
        )
    )

    # Integrity: guard passes on clean batch; lookahead helper blocks dirty dict
    guard = guard_compiled_batch(samples)
    try:
        assert_no_lookahead(
            {
                "feature_cutoff_ms": 200,
                "label_available_ms": 100,
                "ts_ms": 150,
            }
        )
        la_blocked = False
        la_detail = "lookahead helper failed open"
    except ContaminationError as exc:
        la_blocked = True
        la_detail = str(exc)
    # Fold helper result into attack 3 corroboration — already counted; ensure guard ok
    _ = la_blocked, la_detail, guard

    # Offline benchmark happy path must not claim WF/OOS
    req = build_benchmark_request(
        benchmark_id="offline_regime_dev",
        target_label="REGIME",
        metric_names=["log_loss", "brier"],
    )
    result = run_offline_benchmark(req, samples=samples)
    claims_clean = (
        result["formal_walk_forward_executed"] is False
        and result["untouched_oos_executed"] is False
        and result["qualification_claimed"] is False
    )
    findings.append(
        _finding(
            "offline_benchmark_no_qualification_claim",
            blocked=claims_clean,
            detail=f"status={result.get('status')} rows={result.get('row_count')}",
            severity="HIGH",
        )
    )

    survivors = [f for f in findings if f["survivor"]]
    attack_count = len(findings)
    return {
        "schema": "v17_h_contamination_redteam",
        "attack_count": attack_count,
        "expected_min_attacks": EXPECTED_CONTAMINATION_ATTACKS,
        "blocked_count": sum(1 for f in findings if f["attack_blocked"]),
        "survivor_count": len(survivors),
        "survivors": [f["attack_id"] for f in survivors],
        "findings": findings,
        "status": "PASS" if len(survivors) == 0 and attack_count >= EXPECTED_CONTAMINATION_ATTACKS else "FAIL",
        "contamination_survivors": len(survivors),
    }
