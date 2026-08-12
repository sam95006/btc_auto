"""V18-C Eligible Universe Engine tests."""
from __future__ import annotations

from backend.nexus_eligible_universe.constants import (
    FUNNEL_KEYS,
    GATES,
    UNIVERSE_CLASSES,
)
from backend.nexus_eligible_universe.engine import (
    classify_instrument,
    compute_funnel,
    evaluate_universe,
)
from backend.nexus_eligible_universe.fixtures import (
    AS_OF_MS,
    expected_class_for_symbol,
    fixture_instruments,
)
from backend.nexus_eligible_universe.hard_bans import hard_ban_probe_matrix
from backend.nexus_eligible_universe.models import InstrumentSnapshot


def test_all_universe_classes_covered():
    result = evaluate_universe(fixture_instruments(), as_of_ms=AS_OF_MS)
    seen = {d["universe_class"] for d in result["decisions"]}
    # Every founder class must appear at least once in fixtures
    for cls in UNIVERSE_CLASSES:
        assert cls in seen, f"missing class coverage: {cls}"


def test_expected_class_mapping():
    result = evaluate_universe(fixture_instruments(), as_of_ms=AS_OF_MS)
    by_sym = {d["symbol"]: d["universe_class"] for d in result["decisions"]}
    for sym, got in by_sym.items():
        exp = expected_class_for_symbol(sym)
        assert exp is not None
        assert got == exp, f"{sym}: got {got} expected {exp}"


def test_unknown_never_eligible():
    """UNKNOWN/missing fields must not default to ELIGIBLE."""
    cases = [
        InstrumentSnapshot(symbol="X1", status=None),
        InstrumentSnapshot(
            symbol="X2",
            status="Trading",
            quote_coin="USDT",
            tick_size=0.1,
            lot_size=0.01,
            min_notional=5.0,
            launch_time_ms=AS_OF_MS - 30 * 86_400_000,
            turnover_24h=None,  # unknown
            trade_count_24h=10_000,
            spread_bps=1.0,
            book_depth_usdt=100_000,
            funding_available=True,
            oi_available=True,
            open_interest_value=2_000_000,
            history_bars=200,
            data_completeness=0.99,
            data_trust_status="TRUSTED",
            delisting_flag=False,
            round_trip_cost_bps=5.0,
        ),
        InstrumentSnapshot(
            symbol="X3",
            status="Trading",
            quote_coin="USDT",
            tick_size=0.1,
            lot_size=0.01,
            min_notional=5.0,
            launch_time_ms=AS_OF_MS - 30 * 86_400_000,
            turnover_24h=10_000_000,
            trade_count_24h=10_000,
            spread_bps=1.0,
            book_depth_usdt=100_000,
            funding_available=True,
            oi_available=True,
            open_interest_value=2_000_000,
            history_bars=200,
            data_completeness=0.99,
            data_trust_status=None,  # unknown trust
            delisting_flag=False,
            round_trip_cost_bps=5.0,
        ),
    ]
    for inst in cases:
        d = classify_instrument(inst, as_of_ms=AS_OF_MS)
        assert d.universe_class != "ELIGIBLE", inst.symbol
        assert any(not g.known for g in d.gates) or d.universe_class == "UNAVAILABLE"


def test_funnel_keys_and_invariants():
    result = evaluate_universe(fixture_instruments(), as_of_ms=AS_OF_MS)
    funnel = result["funnel"]
    for k in FUNNEL_KEYS:
        assert k in funnel
        assert isinstance(funnel[k], int)
    assert (
        funnel["eligible_contracts"]
        + funnel["observe_only_contracts"]
        + funnel["blocked_contracts"]
        == funnel["total_exchange_contracts"]
    )
    assert funnel["total_exchange_contracts"] == len(fixture_instruments())
    assert funnel["total_exchange_contracts"] >= funnel["catalog_valid_contracts"]
    assert funnel["catalog_valid_contracts"] >= funnel["data_available_contracts"]
    assert funnel["data_available_contracts"] >= funnel["liquidity_pass_contracts"]
    assert funnel["liquidity_pass_contracts"] >= funnel["cost_pass_contracts"]
    assert funnel["cost_pass_contracts"] >= funnel["eligible_contracts"]
    # Must not be a fake hardcoded constant like all zeros or a magic 42
    assert funnel["total_exchange_contracts"] > 0
    assert funnel["eligible_contracts"] >= 1
    assert funnel["blocked_contracts"] >= 1


def test_funnel_not_hardcoded_changes_with_input():
    full = evaluate_universe(fixture_instruments(), as_of_ms=AS_OF_MS)["funnel"]
    subset = evaluate_universe(fixture_instruments()[:5], as_of_ms=AS_OF_MS)["funnel"]
    assert full["total_exchange_contracts"] != subset["total_exchange_contracts"]
    assert compute_funnel(
        [
            classify_instrument(i, as_of_ms=AS_OF_MS)
            for i in fixture_instruments()[:5]
        ]
    ) == subset


def test_gates_present():
    d = classify_instrument(fixture_instruments()[0], as_of_ms=AS_OF_MS)
    names = {g.gate for g in d.gates}
    for g in GATES:
        assert g in names
    assert "history_bars" in names


def test_hard_bans_refuse():
    probes = hard_ban_probe_matrix()
    assert probes["all_refused"] is True
    assert probes["env_guard"]["ok"] is True
    assert probes["probes"]["exchange_write"]["allowed"] is False
    assert probes["probes"]["unknown_as_eligible"]["allowed"] is False


def test_btc_eligible_and_halt_blocked():
    by = {
        d.symbol: d
        for d in (
            classify_instrument(i, as_of_ms=AS_OF_MS) for i in fixture_instruments()
        )
    }
    assert by["BTCUSDT"].universe_class == "ELIGIBLE"
    assert by["HALTUSDT"].universe_class == "MARKET_HALTED"
    assert by["LICUSDT"].universe_class == "LICENSE_BLOCKED"
    assert by["COSTUSDT"].universe_class == "COST_INFEASIBLE"
