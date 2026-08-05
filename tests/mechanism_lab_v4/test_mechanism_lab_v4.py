"""Tests for V14-C Strategy Mechanism Lab V4."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_mechanism_lab_v4.adversarial import run_adversarial_review
from backend.nexus_mechanism_lab_v4.catalog import (
    SPECS,
    assert_catalog_distinct,
    mechanism_catalog,
)
from backend.nexus_mechanism_lab_v4.constants import (
    HARD_BANS,
    MECHANISM_FAMILIES,
    MIN_MECHANISM_COUNT,
    REQUIRED_MECHANISM_FIELDS,
)
from backend.nexus_mechanism_lab_v4.lab import ALLOWED_LABELS, run_mechanism_lab
from backend.nexus_mechanism_lab_v4.artifacts import (
    build_status_payload,
    write_immutable_artifacts,
    write_runtime_status,
)
from backend.nexus_mechanism_lab_v4.signals import signal_for
from backend.nexus_mechanism_lab_v4.synthetic import generate_synthetic_series


def test_catalog_meets_min_and_distinct() -> None:
    assert_catalog_distinct()
    catalog = mechanism_catalog()
    assert len(catalog) >= MIN_MECHANISM_COUNT
    assert len(catalog) == len(SPECS)
    assert set(MECHANISM_FAMILIES).issubset({c["family"] for c in catalog})
    assert len({c["mechanism_id"] for c in catalog}) == len(catalog)
    assert len({c["economic_rationale"] for c in catalog}) == len(catalog)
    contracts = {
        (c["signal_kind"], c["primary_feature"], c["secondary_feature"], c["direction_mode"])
        for c in catalog
    }
    assert len(contracts) == len(catalog)
    for c in catalog:
        for field in REQUIRED_MECHANISM_FIELDS:
            assert c.get(field)


def test_lab_hard_bans_and_no_claims() -> None:
    report = run_mechanism_lab(pass_id=1)
    assert report["mechanism_count"] >= MIN_MECHANISM_COUNT
    assert report["qualification_ready_count"] == 0
    assert report["edge_claim_count"] == 0
    assert report["profitability_claim_count"] == 0
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_executed"] is False
    assert report["oos_consumed"] is False
    assert report["demo_order_count"] == 0
    assert report["shadow_order_count"] == 0
    assert report["exchange_write_attempt_count"] == 0
    assert report["mainnet_touch_count"] == 0
    assert report["profitability_claimed"] is False
    assert report["edge_claimed"] is False
    assert report["qualified_claimed"] is False
    assert report["pr27_merge_attempted"] is False
    assert report["auto_integrate_attempted"] is False
    assert set(HARD_BANS).issubset(set(report["hard_bans"]))
    for m in report["mechanisms"]:
        assert m["label"] in ALLOWED_LABELS
        assert m["qualified"] is False
        assert m["qualification_ready"] is False
        assert m["edge_claimed"] is False
        assert m["profitability_claimed"] is False
        assert m["data_lineage"] == "SYNTHETIC_DEVELOPMENT_FIXTURE"
        assert m["point_in_time_proof"]["lookahead_forbidden"] is True
        assert m["point_in_time_proof"]["future_bar_reference_count"] == 0


def test_two_pass_adversarial() -> None:
    r1 = run_mechanism_lab(pass_id=1)
    a1 = run_adversarial_review(r1, pass_name="pass_1")
    r2 = run_mechanism_lab(pass_id=2)
    a2 = run_adversarial_review(r2, pass_name="pass_2")
    assert a1["pass_ok"] is True
    assert a2["pass_ok"] is True
    assert a1["remaining_count"] == 0
    assert a2["remaining_count"] == 0
    assert a2["qualification_ready_count"] == 0
    assert r1["code_checksum"] == r2["code_checksum"]


def test_artifacts_and_runtime_status(tmp_path: Path) -> None:
    report = run_mechanism_lab(pass_id=2)
    a1 = run_adversarial_review(report, pass_name="pass_1")
    a2 = run_adversarial_review(report, pass_name="pass_2")
    paths = write_immutable_artifacts(report, [a1, a2], root=tmp_path)
    assert paths["status"].is_file()
    assert paths["mechanism_catalog"].is_file()
    summary = build_status_payload(report, [a1, a2], root=tmp_path)
    assert summary["qualification_ready_count"] == 0
    assert summary["auto_integrate"] is False
    runtime = write_runtime_status(summary, runtime_root=tmp_path)
    assert runtime.name == "v14_c_status.json"
    text = runtime.read_text(encoding="utf-8")
    assert '"qualification_ready_count": 0' in text
    assert '"auto_integrate": false' in text


def test_signals_deterministic_and_pit_safe() -> None:
    bars = generate_synthetic_series(n_bars=120, seed=20260805)
    # Same inputs => same signal; never reads beyond prev/bar.
    for spec in SPECS[:5]:
        s1 = signal_for(spec, bars[50], bars[49])
        s2 = signal_for(spec, bars[50], bars[49])
        assert s1 == s2
        assert s1 in (None, -1, 1)
