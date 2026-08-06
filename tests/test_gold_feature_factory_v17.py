"""V17-G Gold Feature Factory — fixture-only tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_gold_feature_factory import (
    FEATURE_IDS,
    HARD_BANS,
    REQUIRED_METADATA_FIELDS,
    FeatureFactoryBanError,
    build_synthetic_market,
    compute_all_features,
    compute_feature,
    feature_catalog,
    formula_authority_map,
    prove_pit_excludes_future,
    reject_duplicate_authority,
    run_factory_guards,
    verify_deterministic_replay,
)
from backend.nexus_gold_feature_factory.formulas import compute_funding, compute_order_flow
from backend.nexus_gold_feature_factory.guards import assert_observation_marks_missing

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_covers_all_features_with_required_fields() -> None:
    cat = feature_catalog()
    assert cat["feature_count"] == len(FEATURE_IDS)
    assert cat["predictive_edge_claimed"] is False
    assert cat["authoritative_formula_count_per_name"] == 1
    assert set(cat["features"]) == set(FEATURE_IDS)
    for fid, meta in cat["features"].items():
        assert meta["definition"]
        assert meta["units"]
        assert meta["normalization"]
        assert meta["missing_policy"]
        assert meta["license_scope"]
        assert meta["formula_id"]
        assert meta["source_lineage"]


def test_hard_bans_document_false_flags() -> None:
    assert HARD_BANS["silent_forward_fill"] is False
    assert HARD_BANS["future_price_labels"] is False
    assert HARD_BANS["unmarked_missing"] is False
    assert HARD_BANS["multiple_authoritative_formulas_same_name"] is False
    assert HARD_BANS["exchange_write"] is False
    assert HARD_BANS["mainnet"] is False
    assert HARD_BANS["pr26_merge"] is False
    assert HARD_BANS["pr27_merge"] is False
    assert HARD_BANS["report_edit"] is False


def test_fixture_deterministic_checksum() -> None:
    a = build_synthetic_market(seed="det-1")
    b = build_synthetic_market(seed="det-1")
    c = build_synthetic_market(seed="det-2")
    assert a["fixture_checksum"] == b["fixture_checksum"]
    assert a["evidence_class"] == "fixture"
    assert a["mainnet"] is False
    assert a["exchange_write_attempt_count"] == 0
    assert c["fixture_checksum"] != a["fixture_checksum"]


def test_compute_all_features_metadata_and_coverage() -> None:
    market = build_synthetic_market(seed="bundle-1")
    bundle = compute_all_features(market)
    assert bundle["feature_count"] == len(FEATURE_IDS)
    assert set(bundle["features"]) == set(FEATURE_IDS)
    assert bundle["evidence_class"] == "fixture"
    for fid, obs in bundle["features"].items():
        assert obs["feature_id"] == fid
        for field in REQUIRED_METADATA_FIELDS:
            assert field in obs
            assert obs[field] is not None or field == "available_at"
        assert obs["feature_version"]
        assert obs["source_lineage"]
        assert obs["as_of"] == bundle["as_of"]
        assert obs["lookback"] is not None
        assert obs["normalization"]
        assert obs["missing_policy"]
        assert obs["license_scope"]
        assert str(obs["calculation_hash"]).startswith("sha256:")
        assert obs["quality"] in {"COMPLETE", "PARTIAL", "UNAVAILABLE", "MISSING"}
        assert obs["predictive_edge_claimed"] is False
        assert_observation_marks_missing(obs)


def test_deterministic_replay() -> None:
    market = build_synthetic_market(seed="replay-1")
    result = verify_deterministic_replay(market)
    assert result["ok"] is True


def test_pit_excludes_future() -> None:
    market = build_synthetic_market(seed="pit-1")
    as_of = int(market["as_of_default"])
    proof = prove_pit_excludes_future(market, as_of=as_of)
    assert proof["ok"] is True
    # Earlier as_of should not see later bars' effects on checksum equality with full
    early = compute_all_features(market, as_of=as_of - 20 * market["bar_ms"])
    late = compute_all_features(market, as_of=as_of)
    assert early["bundle_checksum"] != late["bundle_checksum"]


def test_no_silent_forward_fill_on_funding_gap() -> None:
    market = build_synthetic_market(seed="funding-gap")
    # Choose as_of before any funding row exists
    first_bar = market["ohlcv"][market["primary_symbol"]][0]["exchange_ts"]
    obs = compute_funding(market, as_of=first_bar - 1)
    assert obs.value is None
    assert obs.quality == "UNAVAILABLE"
    assert obs.reason == "no_eligible_funding"
    assert obs.missing_policy == "MARK_UNAVAILABLE"


def test_order_flow_excludes_unknown_side() -> None:
    market = build_synthetic_market(seed="flow-1")
    # Inject a huge UNKNOWN trade that must not skew imbalance if excluded
    as_of = int(market["as_of_default"])
    market["trades"].append(
        {
            "symbol": market["primary_symbol"],
            "exchange_ts": as_of - 1000,
            "receive_ts": as_of - 900,
            "side": "UNKNOWN",
            "price": 100.0,
            "quantity": 1_000_000.0,
            "notional": 100_000_000.0,
        }
    )
    obs = compute_order_flow(market, as_of=as_of)
    assert obs.extras.get("unknown_excluded") is True
    if obs.value is not None:
        assert -1.0 <= float(obs.value) <= 1.0


def test_reject_multiple_authoritative_formulas_same_name() -> None:
    auth = formula_authority_map()
    assert len(auth) == len(FEATURE_IDS)
    with pytest.raises(FeatureFactoryBanError):
        reject_duplicate_authority("volatility", "volatility.rogue_alt.v2")
    # Same formula id is allowed (idempotent)
    reject_duplicate_authority("volatility", auth["volatility"])


def test_future_price_label_ban_via_guards() -> None:
    from backend.nexus_gold_feature_factory.guards import assert_no_future_price_labels

    assert_no_future_price_labels(as_of=1000, used_exchange_ts=[900, 1000])
    with pytest.raises(FeatureFactoryBanError):
        assert_no_future_price_labels(as_of=1000, used_exchange_ts=[1001])


def test_unmarked_missing_banned() -> None:
    with pytest.raises(FeatureFactoryBanError):
        assert_observation_marks_missing(
            {
                "feature_id": "trend",
                "value": None,
                "quality": "COMPLETE",  # illegal for null value
                "missing_policy": "MARK_UNAVAILABLE",
                "reason": "x",
            }
        )


def test_factory_source_guards() -> None:
    result = run_factory_guards(ROOT)
    assert result["silent_forward_fill_ok"] is True
    assert result["single_authority_ok"] is True
    assert result["future_label_ast_ok"] is True


def test_individual_features_callable() -> None:
    market = build_synthetic_market(seed="each-1")
    for fid in FEATURE_IDS:
        obs = compute_feature(fid, market)
        assert obs.feature_id == fid
        assert obs.calculation_hash.startswith("sha256:")
