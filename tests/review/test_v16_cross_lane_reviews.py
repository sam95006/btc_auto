"""Reviewer-owned negative tests for V16 cross-lane review wave."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("EXCHANGE_WRITE", "false")

from tools.review.v16_cross_lane.probes import (  # noqa: E402
    REVIEW_RUNNERS,
    review_a_reviews_e,
    review_b_reviews_h,
    review_c_reviews_d,
    review_d_reviews_g,
    review_e_reviews_f,
    review_f_reviews_a,
    review_g_reviews_c,
    review_h_reviews_b,
    run_all_cross_lane_reviews,
)


@pytest.mark.parametrize(
    "runner",
    REVIEW_RUNNERS,
    ids=[
        "A_reviews_E",
        "B_reviews_H",
        "C_reviews_D",
        "D_reviews_G",
        "E_reviews_F",
        "F_reviews_A",
        "G_reviews_C",
        "H_reviews_B",
    ],
)
def test_v16_cross_lane_pair_review(runner) -> None:
    result = runner()
    open_findings = [f for f in result["findings"] if f["disposition"] == "OPEN"]
    assert result["status"] == "PASS", open_findings
    assert not open_findings, open_findings


def test_v16_cross_lane_wave_aggregate() -> None:
    bundle = run_all_cross_lane_reviews()
    assert bundle["pair_count"] == 8
    assert bundle["status"] == "PASS", bundle.get("blockers")
    assert bundle["blockers"] == []
    assert bundle["survivors"] == []
    assert bundle["findings_fixed"] >= 8


def test_named_pair_entrypoints_callable() -> None:
    # Smoke that each named reviewer entrypoint remains importable.
    for fn in (
        review_a_reviews_e,
        review_b_reviews_h,
        review_c_reviews_d,
        review_d_reviews_g,
        review_e_reviews_f,
        review_f_reviews_a,
        review_g_reviews_c,
        review_h_reviews_b,
    ):
        assert callable(fn)
