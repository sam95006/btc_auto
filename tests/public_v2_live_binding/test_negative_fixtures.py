"""Negative fixtures proving PUB2-B counters catch honesty violations."""
from __future__ import annotations

from backend.nexus_public_v2_live_binding.display_rules import is_unavailable_shown_as_zero
from backend.nexus_public_v2_live_binding.verifier import LiveBindingCounters


def test_negative_unavailable_as_zero_detected():
    assert is_unavailable_shown_as_zero(
        value=0,
        freshness="UNAVAILABLE",
        completeness="MISSING",
        display_text="0",
    )


def test_counters_dataclass_required_keys():
    c = LiveBindingCounters(0, 0, 0, 0)
    assert c.all_zero
    bad = LiveBindingCounters(1, 0, 0, 0)
    assert not bad.all_zero
