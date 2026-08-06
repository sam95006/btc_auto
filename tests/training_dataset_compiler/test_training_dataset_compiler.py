"""Tests for V17-H Training Dataset Compiler."""
from __future__ import annotations

from backend.nexus_training_dataset_compiler.benchmark import (
    build_benchmark_request,
    refuse_formal_walk_forward,
    refuse_real_lesson_activation,
    refuse_real_promotion,
    refuse_untouched_oos,
    run_offline_benchmark,
)
from backend.nexus_training_dataset_compiler.compiler import (
    assert_samples_safe,
    compile_all_samples,
    compile_campaign,
    dataset_catalog,
)
from backend.nexus_training_dataset_compiler.constants import (
    DATASET_SPLITS,
    EXPECTED_FIXTURE_SAMPLES,
    HARD_BANS,
    MIN_FIXTURE_SAMPLES,
    REQUIRED_SAMPLE_FIELDS,
    RESERVED_SPLITS,
    TARGET_LABELS,
    TRAINABLE_SPLITS,
)
from backend.nexus_training_dataset_compiler.contamination import filter_trainable
from backend.nexus_training_dataset_compiler.fixtures import RAW_FIXTURES
from backend.nexus_training_dataset_compiler.redteam import run_contamination_redteam
from backend.nexus_training_dataset_compiler.split import assign_trainable_split, resolve_split


def test_compiles_fixture_catalog() -> None:
    samples = compile_all_samples()
    assert_samples_safe(samples)
    assert len(samples) == EXPECTED_FIXTURE_SAMPLES
    assert len(RAW_FIXTURES) == EXPECTED_FIXTURE_SAMPLES
    assert len(samples) >= MIN_FIXTURE_SAMPLES
    catalog = dataset_catalog(samples)
    assert len(catalog) == len(samples)
    for row in catalog:
        for field in REQUIRED_SAMPLE_FIELDS:
            assert field in row
        assert row["labels_only"] is True
        assert row["consumer_plan"]["llm_sole_tick_consumer"] is False
        assert row["target_label"] in TARGET_LABELS
        assert row["split"] in DATASET_SPLITS


def test_all_splits_and_targets_represented() -> None:
    samples = compile_all_samples()
    splits = {s.split for s in samples}
    targets = {s.target_label for s in samples}
    assert set(DATASET_SPLITS).issubset(splits)
    assert set(TARGET_LABELS) == targets


def test_deterministic_split_assignment() -> None:
    a = assign_trainable_split("TDS_HASH_ERR_007", "BTCUSDT", 1_700_000_360_000)
    b = assign_trainable_split("TDS_HASH_ERR_007", "BTCUSDT", 1_700_000_360_000)
    assert a == b
    assert a in TRAINABLE_SPLITS
    # Hash path never invents reserved
    for i in range(50):
        s = assign_trainable_split(f"ID_{i}", "ETHUSDT", 1_700_000_000_000 + i)
        assert s in TRAINABLE_SPLITS
        assert s not in RESERVED_SPLITS


def test_explicit_reserved_splits_honored() -> None:
    split = resolve_split(
        sample_id="X",
        symbol="BTCUSDT",
        ts_ms=1,
        declared_split="OOS_RESERVED",
    )
    assert split == "OOS_RESERVED"
    samples = compile_all_samples()
    reserved = [s for s in samples if s.split in RESERVED_SPLITS]
    assert reserved
    assert all(not s.trainable for s in reserved)


def test_trainable_filter_excludes_reserved() -> None:
    samples = compile_all_samples()
    trainable = filter_trainable(samples)
    assert trainable
    assert all(s.split in TRAINABLE_SPLITS for s in trainable)
    assert all(s.trainable for s in trainable)
    assert not any(s.split in RESERVED_SPLITS for s in trainable)


def test_campaign_hard_bans() -> None:
    report = compile_campaign(pass_id=1)
    assert report["sample_count"] == EXPECTED_FIXTURE_SAMPLES
    assert report["formal_walk_forward_executed"] is False
    assert report["untouched_oos_executed"] is False
    assert report["oos_consumed"] is False
    assert report["real_promotion_executed"] is False
    assert report["real_lesson_activated"] is False
    assert report["mainnet_touched"] is False
    assert report["real_money_touched"] is False
    assert report["exchange_write_attempted"] is False
    assert report["pr26_merge_attempted"] is False
    assert report["pr27_merge_attempted"] is False
    assert report["llm_sole_tick_consumer"] is False
    assert report["contamination_survivors"] == 0
    assert set(HARD_BANS).issubset(set(report["hard_bans"]))


def test_deterministic_three_pass_sample_digests() -> None:
    r1 = compile_campaign(pass_id=1)
    r2 = compile_campaign(pass_id=2)
    r3 = compile_campaign(pass_id=3)
    d1 = [s["compile_digest"] for s in r1["samples"]]
    d2 = [s["compile_digest"] for s in r2["samples"]]
    d3 = [s["compile_digest"] for s in r3["samples"]]
    assert d1 == d2 == d3


def test_offline_benchmark_interface() -> None:
    req = build_benchmark_request(
        benchmark_id="offline_regime_dev",
        target_label="REGIME",
        metric_names=["log_loss", "brier"],
    )
    assert req.to_public_dict()["offline_only"] is True
    assert req.to_public_dict()["formal_walk_forward"] is False
    result = run_offline_benchmark(req)
    assert result["status"] == "INTERFACE_READY"
    assert result["formal_walk_forward_executed"] is False
    assert result["untouched_oos_executed"] is False
    assert result["qualification_claimed"] is False
    assert result["offline_only"] is True
    assert all(s.split in TRAINABLE_SPLITS for s in compile_all_samples() if s.sample_id in result["sample_ids"])


def test_banned_stage_refusals() -> None:
    assert refuse_formal_walk_forward()["allowed"] is False
    assert refuse_untouched_oos()["allowed"] is False
    assert refuse_real_promotion()["allowed"] is False
    assert refuse_real_lesson_activation()["allowed"] is False


def test_contamination_redteam_survivors_zero() -> None:
    report = run_contamination_redteam()
    assert report["status"] == "PASS"
    assert report["survivor_count"] == 0
    assert report["contamination_survivors"] == 0
    assert report["survivors"] == []
    assert report["attack_count"] >= 12
    assert all(f["attack_blocked"] for f in report["findings"])
    assert all(not f["survivor"] for f in report["findings"])
