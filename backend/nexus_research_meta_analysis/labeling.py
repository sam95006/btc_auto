"""Label helpers for V15-D meta-analysis outcomes."""
from __future__ import annotations

from typing import Any

from backend.nexus_research_meta_analysis.constants import (
    ALLOWED_LABELS,
    BANNED_LABEL_FRAGMENTS,
)


def assert_label_allowed(label: str) -> None:
    upper = str(label).upper()
    if upper not in ALLOWED_LABELS:
        for frag in BANNED_LABEL_FRAGMENTS:
            if frag in upper:
                raise ValueError(f"banned_label:{label}")
        raise ValueError(f"label_not_in_allowed_set:{label}")


def label_histogram(rows: list[dict[str, Any]]) -> dict[str, int]:
    hist: dict[str, int] = {lab: 0 for lab in sorted(ALLOWED_LABELS)}
    for row in rows:
        lab = str(row.get("label") or row.get("result_label") or "")
        assert_label_allowed(lab)
        hist[lab] = hist.get(lab, 0) + 1
    return hist
