"""Tests — V17 deep public inference leakage attacks."""
from __future__ import annotations

from backend.nexus_deep_license_inference.inference_attacks import run_deep_inference_attacks
from backend.nexus_private_to_public_projection_v3.inference_redteam import run_inference_redteam


def test_deep_inference_survivors_zero() -> None:
    report = run_deep_inference_attacks()
    assert report["status"] == "PASS"
    assert report["survivor_count"] == 0
    assert report["survivors"] == []
    assert report["attack_count"] >= 5


def test_baseline_pub17c_still_zero() -> None:
    report = run_inference_redteam()
    assert report["survivor_count"] == 0
    assert report["status"] == "PASS"
