"""Provider-independent Reflection interface tests (no real AI quality claims)."""
from __future__ import annotations

import os

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_autonomy.process_classification import (
    CANONICAL_CLASSES,
    classify_completed_trade,
    control_fixture_process_evidence,
)


def test_canonical_classes_include_bad_process_win():
    assert "BAD_PROCESS_WIN" in CANONICAL_CLASSES
    assert "UNDETERMINED" in CANONICAL_CLASSES
    assert len(CANONICAL_CLASSES) == 5


def test_good_process_loss_protection_not_from_pnl_alone():
    # PnL negative with good evidence => GOOD_PROCESS_LOSS
    assert (
        classify_completed_trade(pnl=-1.0, process_evidence=control_fixture_process_evidence(bad=False))
        == "GOOD_PROCESS_LOSS"
    )
    # PnL negative alone with no evidence => UNDETERMINED
    assert classify_completed_trade(pnl=-1.0, process_evidence=None) == "UNDETERMINED"


def test_lesson_signature_stability_material():
    a = control_fixture_process_evidence(bad=True)
    b = control_fixture_process_evidence(bad=True)
    assert a["rule_violation_ids"] == b["rule_violation_ids"]


def test_undetermined_migration_path():
    assert classify_completed_trade(pnl=1.0, process_evidence={"sparse": True}) == "UNDETERMINED"
