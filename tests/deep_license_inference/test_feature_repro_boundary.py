"""Tests — feature reproducibility via private import boundary only."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_deep_license_inference.feature_repro_boundary import (
    public_tree_must_not_vendor_gold_factory,
    run_feature_repro_checks,
)


def test_feature_repro_checks_pass() -> None:
    report = run_feature_repro_checks()
    assert report["status"] == "PASS"
    assert report["survivor_count"] == 0


def test_public_tree_does_not_vendor_gold_factory() -> None:
    root = Path(__file__).resolve().parents[2]
    finding = public_tree_must_not_vendor_gold_factory(root)
    assert finding["survivor"] is False
    assert not (root / "backend" / "nexus_gold_feature_factory").exists()
