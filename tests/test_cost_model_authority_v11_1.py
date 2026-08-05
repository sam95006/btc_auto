"""V11.1 cost-model authority consolidation tests.

Covers: CostModelContract, version migration, serialization, drift detection,
property-style bridge algebra, cross-module reconciliation, and negative paths.
"""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.nexus_execution.cost_model import (
    CANONICAL_COST_AUTHORITY,
    CANONICAL_COST_AUTHORITY_COUNT,
    COMPATIBLE_COST_MODEL_VERSIONS,
    COST_MODEL_SCHEMA,
    COST_MODEL_VERSION,
    CostBridgeFailure,
    CostModelContract,
    CostModelVersionError,
    DEFAULT_TAKER_FEE,
    LEGACY_COST_MODEL_VERSIONS,
    apply_leg_costs_float,
    authority_metrics,
    compose_cost_bridge,
    deserialize_cost_bridge,
    detect_cost_formula_divergence,
    estimate_round_trip_costs_float,
    get_cost_model_contract,
    migrate_cost_model_version,
    net_pnl_float,
    net_pnl_from_components,
    serialize_cost_bridge,
    validate_cost_model_version,
    versions_compatible,
)
from backend.nexus_execution.contracts import CostBridge
from backend.nexus_strategy_engine import cost_semantics
from backend.nexus_strategy_engine.constants import TAKER_FEE_RATE
from backend.nexus_autonomy import execution_simulator_v1_1 as autonomy_sim
from backend.nexus_demo_execution.trade_geometry import estimate_costs


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_authority_singleton_metrics():
    m = authority_metrics()
    assert m["canonical_cost_authority_count"] == 1
    assert m["canonical_cost_authority"] == CANONICAL_COST_AUTHORITY
    assert m["cost_formula_divergence_count"] == 0
    assert m["cost_version_divergence_count"] == 0
    assert m["cost_bridge_failure_count"] == 0
    assert m["passed"] is True
    assert CANONICAL_COST_AUTHORITY_COUNT == 1


def test_cost_model_contract_roundtrip():
    c = get_cost_model_contract()
    c.validate()
    payload = c.to_dict()
    restored = CostModelContract.from_dict(payload)
    assert restored == c
    assert restored.version == COST_MODEL_VERSION
    assert restored.schema == COST_MODEL_SCHEMA


def test_migrate_legacy_versions():
    for legacy in LEGACY_COST_MODEL_VERSIONS:
        assert migrate_cost_model_version(legacy) == COST_MODEL_VERSION
        assert versions_compatible(legacy, COST_MODEL_VERSION)


def test_unknown_version_rejected():
    with pytest.raises(CostModelVersionError):
        validate_cost_model_version("totally-unknown-cost-v9")
    with pytest.raises(CostModelVersionError):
        migrate_cost_model_version("totally-unknown-cost-v9")
    with pytest.raises(CostModelVersionError):
        validate_cost_model_version(None)
    with pytest.raises(CostModelVersionError):
        validate_cost_model_version("")


def test_serialization_schema_requires_keys():
    bridge = compose_cost_bridge(
        side="LONG",
        qty=Decimal("0.1"),
        entry_price=Decimal("100"),
        exit_price=Decimal("101"),
        entry_fee=Decimal("0.01"),
        exit_fee=Decimal("0.01"),
        entry_spread=Decimal("0.001"),
        exit_spread=Decimal("0.001"),
        entry_slippage=Decimal("0.002"),
        exit_slippage=Decimal("0.002"),
        funding=Decimal("0"),
        partial_fill=Decimal("0"),
        cancel_replace=Decimal("0"),
    )
    payload = serialize_cost_bridge(bridge)
    assert payload["cost_model_version"] == COST_MODEL_VERSION
    assert payload["schema"] == COST_MODEL_SCHEMA
    restored = deserialize_cost_bridge(payload)
    assert restored == bridge

    bad = dict(payload)
    del bad["net_pnl"]
    with pytest.raises(CostBridgeFailure):
        deserialize_cost_bridge(bad)

    tampered = dict(payload)
    tampered["net_pnl"] = "999"
    with pytest.raises(CostBridgeFailure):
        deserialize_cost_bridge(tampered)


def test_negative_silent_fallback_forbidden_on_bad_contract_payload():
    with pytest.raises(CostModelVersionError):
        CostModelContract.from_dict({"version": COST_MODEL_VERSION})  # missing keys


def test_strategy_cost_semantics_reexports_canonical():
    assert cost_semantics.COST_MODEL_VERSION == COST_MODEL_VERSION
    summary = cost_semantics.cost_semantics_summary()
    assert summary["cost_model_version"] == COST_MODEL_VERSION
    assert summary["formula_authority"] == CANONICAL_COST_AUTHORITY
    row = cost_semantics.annotate_trade_costs(
        {"trade_id": "t1"}, spread_bps=1.0, slip_bps=2.0
    )
    assert row["cost_model_version"] == COST_MODEL_VERSION


def test_strategy_constants_fee_from_canonical():
    assert TAKER_FEE_RATE == float(DEFAULT_TAKER_FEE)
    assert TAKER_FEE_RATE == autonomy_sim.TAKER_FEE


def test_demo_estimate_costs_delegates():
    a = estimate_costs(
        notional=1000.0,
        fee_rate=0.00055,
        spread_bps=1.0,
        slippage_bps=2.0,
        funding_rate=None,
    )
    b = estimate_round_trip_costs_float(
        notional=1000.0,
        fee_rate=0.00055,
        spread_bps=1.0,
        slippage_bps=2.0,
        funding_rate=None,
        include_uncertainty_buffer=True,
    )
    assert a["entry_fee"] == pytest.approx(b["entry_fee"])
    assert a["exit_fee"] == pytest.approx(b["exit_fee"])
    assert a["total_cost"] == pytest.approx(b["total_cost"])
    assert b["cost_model_version"] == COST_MODEL_VERSION


def test_autonomy_shim_applies_canonical_leg_costs():
    via_shim = autonomy_sim.AutonomousExecutionSimulatorV1_1()._apply_costs(
        notional=1000.0, is_taker=True
    )
    via_auth = apply_leg_costs_float(notional=1000.0, is_taker=True)
    assert via_shim["fee"] == pytest.approx(via_auth["fee"])
    assert via_shim["spread_cost"] == pytest.approx(via_auth["spread_cost"])
    assert via_shim["slippage_cost"] == pytest.approx(via_auth["slippage_cost"])
    assert via_auth["cost_model_version"] == COST_MODEL_VERSION


@pytest.mark.parametrize(
    "gross,entry_fee,exit_fee,spread,slip,funding,partial,cancel",
    [
        (1.0, 0.01, 0.01, 0.001, 0.002, 0.0, 0.0, 0.0),
        (0.5, 0.02, 0.02, 0.0, 0.0, 0.01, 0.005, 0.01),
        (-0.25, 0.01, 0.01, 0.001, 0.001, -0.005, 0.0, 0.0),
        (10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ],
)
def test_property_net_pnl_identity(
    gross, entry_fee, exit_fee, spread, slip, funding, partial, cancel
):
    g = Decimal(str(gross))
    ef = Decimal(str(entry_fee))
    xf = Decimal(str(exit_fee))
    sp = Decimal(str(spread))
    sl = Decimal(str(slip))
    fu = Decimal(str(funding))
    pf = Decimal(str(partial))
    cr = Decimal(str(cancel))
    expected = g - ef - xf - sp - sl - fu - pf - cr
    got = net_pnl_from_components(
        gross_pnl=g,
        entry_fee=ef,
        exit_fee=xf,
        spread_cost=sp,
        slippage_cost=sl,
        funding_cost=fu,
        partial_fill_cost=pf,
        cancel_replace_cost=cr,
    )
    assert got == expected
    assert net_pnl_float(
        gross_pnl=gross,
        entry_fee=entry_fee,
        exit_fee=exit_fee,
        spread_cost=spread,
        slippage_cost=slip,
        funding_cost=funding,
        partial_fill_cost=partial,
        cancel_replace_cost=cancel,
    ) == pytest.approx(float(expected))


def test_cross_module_version_reconciliation():
    report = detect_cost_formula_divergence(
        competitor_versions={
            "backend.nexus_strategy_engine.cost_semantics": cost_semantics.COST_MODEL_VERSION,
            "backend.nexus_autonomy.execution_simulator_v1_1": COST_MODEL_VERSION,
        }
    )
    assert report["cost_version_divergence_count"] == 0
    assert report["cost_formula_divergence_count"] == 0
    assert report["passed"] is True


def test_divergence_detector_flags_unknown_competitor():
    report = detect_cost_formula_divergence(
        competitor_versions={"evil.module": "parallel-cost-v0"}
    )
    assert report["cost_version_divergence_count"] == 1
    assert report["passed"] is False


def test_no_independent_cost_model_version_assign_in_strategy_shim():
    path = ROOT / "backend" / "nexus_strategy_engine" / "cost_semantics.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "COST_MODEL_VERSION":
                    pytest.fail("strategy cost_semantics must not assign COST_MODEL_VERSION")


def test_contract_from_legacy_serialized_version():
    payload = get_cost_model_contract().to_dict()
    payload["version"] = "NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1"
    restored = CostModelContract.from_dict(payload)
    assert restored.version == COST_MODEL_VERSION


def test_false_pass_guard_broken_bridge_raises():
    with pytest.raises(CostBridgeFailure):
        serialize_cost_bridge(
            CostBridge(
                gross_pnl=Decimal("1"),
                entry_fee=Decimal("0"),
                exit_fee=Decimal("0"),
                spread_cost=Decimal("0"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                partial_fill_cost=Decimal("0"),
                cancel_replace_cost=Decimal("0"),
                net_pnl=Decimal("0.5"),  # deliberately wrong
            )
        )


def test_compatible_set_covers_canonical_and_legacy():
    assert COST_MODEL_VERSION in COMPATIBLE_COST_MODEL_VERSIONS
    assert LEGACY_COST_MODEL_VERSIONS <= COMPATIBLE_COST_MODEL_VERSIONS


# --- Pass 2 adversarial / negative ---


def test_pass2_schema_drift_wrong_authority_rejected():
    bad = CostModelContract(authority="evil.parallel.cost")
    with pytest.raises(CostModelVersionError, match="authority_mismatch"):
        bad.validate()


def test_pass2_schema_drift_wrong_schema_rejected():
    bad = CostModelContract(schema="nexus_cost_model_contract_v0")
    with pytest.raises(CostModelVersionError, match="schema_mismatch"):
        bad.validate()


def test_pass2_negative_fee_rejected():
    bad = CostModelContract(taker_fee=Decimal("-0.001"))
    with pytest.raises(CostModelVersionError, match="non_negative"):
        bad.validate()


def test_pass2_no_silent_fallback_on_empty_version():
    with pytest.raises(CostModelVersionError):
        migrate_cost_model_version("   ")


def test_pass2_fixture_only_divergence_not_counted_as_pass():
    """A fixture claiming a foreign version must fail metrics, not soft-pass."""
    report = detect_cost_formula_divergence(
        competitor_versions={"fixtures.only": "fixture-cost-v-fake"}
    )
    metrics = authority_metrics(
        formula_divergence_count=report["cost_formula_divergence_count"],
        version_divergence_count=report["cost_version_divergence_count"],
    )
    assert metrics["passed"] is False
    assert metrics["cost_version_divergence_count"] == 1


def test_pass2_bridge_failure_increments_metric():
    metrics = authority_metrics(bridge_failures=1)
    assert metrics["cost_bridge_failure_count"] == 1
    assert metrics["passed"] is False


def test_pass2_no_secrets_in_cost_model_module():
    text = (ROOT / "backend" / "nexus_execution" / "cost_model.py").read_text(
        encoding="utf-8"
    )
    for needle in ("API_KEY", "SECRET", "PASSWORD", "private_key", "BEGIN RSA"):
        assert needle not in text


def test_pass2_drift_checker_clears_cost_divergence():
    from tools.architecture.check_contract_drift import check_cost_drift

    findings = check_cost_drift(ROOT)
    codes = {f["code"] for f in findings}
    assert "COST_MODEL_VERSION_DIVERGENCE" not in codes
    assert "COMPAT_SIM_HARDCODED_FEE" not in codes
