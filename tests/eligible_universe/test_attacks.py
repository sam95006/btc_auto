"""Adversarial / attack tests for V18-C Eligible Universe."""
from __future__ import annotations

from backend.nexus_eligible_universe.engine import classify_instrument
from backend.nexus_eligible_universe.fixtures import AS_OF_MS, _healthy
from backend.nexus_eligible_universe.hard_bans import (
    refuse_archive_rebuild,
    refuse_demo,
    refuse_exchange_write,
    refuse_mainnet,
    refuse_pr_merge,
    refuse_report_edit,
    refuse_unknown_as_eligible,
)
from backend.nexus_eligible_universe.models import InstrumentSnapshot


def test_attack_zero_turnover_not_eligible():
    """Inventing 0.0 turnover must not pass as healthy liquidity."""
    row = _healthy(symbol="ZERO_TURN", turnover_24h=0.0)
    d = classify_instrument(InstrumentSnapshot(**row), as_of_ms=AS_OF_MS)
    assert d.universe_class != "ELIGIBLE"
    assert d.universe_class == "LOW_LIQUIDITY"


def test_attack_missing_fields_as_zero_rejected_path():
    """None (unknown) vs 0.0 (known bad) — both non-eligible, different paths."""
    unknown = InstrumentSnapshot(**_healthy(symbol="U", turnover_24h=None))
    zero = InstrumentSnapshot(**_healthy(symbol="Z", turnover_24h=0.0))
    du = classify_instrument(unknown, as_of_ms=AS_OF_MS)
    dz = classify_instrument(zero, as_of_ms=AS_OF_MS)
    assert du.universe_class == "UNAVAILABLE"
    assert dz.universe_class == "LOW_LIQUIDITY"


def test_attack_ai_style_promotion_blocked():
    """Even with all other fields perfect, unknown trust blocks ELIGIBLE."""
    row = _healthy(symbol="PROMOTE", data_trust_status=None)
    d = classify_instrument(InstrumentSnapshot(**row), as_of_ms=AS_OF_MS)
    assert d.universe_class == "UNAVAILABLE"
    assert refuse_unknown_as_eligible()["allowed"] is False


def test_attack_hard_ban_surfaces():
    assert refuse_exchange_write()["executed"] is False
    assert refuse_mainnet()["allowed"] is False
    assert refuse_demo()["allowed"] is False
    assert refuse_pr_merge("26")["allowed"] is False
    assert refuse_pr_merge("27")["allowed"] is False
    assert refuse_report_edit()["allowed"] is False
    assert refuse_archive_rebuild()["allowed"] is False
