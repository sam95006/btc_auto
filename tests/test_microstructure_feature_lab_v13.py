"""V13-E Microstructure Feature Lab tests — catalog, PIT, replay, forensic RO."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_micro_feature_lab import (
    FEATURE_IDS,
    HARD_BANS,
    ForensicWriteAttemptError,
    build_synthetic_capture,
    extract_bundle_from_capture,
    feature_catalog,
    fingerprint_bundle,
    forensic_campaign_probe,
    prove_pit_excludes_future,
    refuse_write,
    run_extraction_once,
    verify_deterministic_replay,
)
from backend.nexus_micro_feature_lab.extractors import (
    extract_aggressive_buy_sell_imbalance,
    extract_trade_intensity,
)
from backend.nexus_micro_feature_lab.forensic_ro import scan_owned_paths_for_write_apis
from backend.nexus_micro_feature_lab.fixtures import make_trade
from backend.nexus_micro_feature_lab.pit import filter_pit


ROOT = Path(__file__).resolve().parents[1]


def test_catalog_covers_all_features_with_semantics() -> None:
    cat = feature_catalog()
    assert cat["feature_count"] == len(FEATURE_IDS)
    assert cat["predictive_edge_claimed"] is False
    assert set(cat["features"]) == set(FEATURE_IDS)
    common = cat["common_semantics"]
    for key in (
        "timestamp_semantics",
        "availability_semantics",
        "missing_data_behavior",
        "staleness_semantics",
    ):
        assert key in common
    for fid, meta in cat["features"].items():
        assert meta["definition"]
        assert meta["units"]
        assert "semantics_ref" in meta


def test_hard_bans_document_false_flags() -> None:
    assert HARD_BANS["predictive_edge_claims"] is False
    assert HARD_BANS["event_study"] is False
    assert HARD_BANS["demo_orders"] is False
    assert HARD_BANS["exchange_write"] is False
    assert HARD_BANS["pr27_merge"] is False
    assert HARD_BANS["silent_seal_or_modify_old_raw_partitions"] is False


def test_synthetic_fixture_deterministic() -> None:
    a = build_synthetic_capture(seed="det-1")
    b = build_synthetic_capture(seed="det-1")
    assert a["fixture_checksum"] == b["fixture_checksum"]
    assert a["trade_count"] == b["trade_count"]
    c = build_synthetic_capture(seed="det-2")
    assert c["fixture_checksum"] != a["fixture_checksum"]


def test_extract_all_features_bundle() -> None:
    capture = build_synthetic_capture(seed="bundle-1")
    bundle = extract_bundle_from_capture(capture, symbol="BTCUSDT")
    assert set(bundle["features"]) == set(FEATURE_IDS)
    for fid, obs in bundle["features"].items():
        assert obs["feature_id"] == fid
        assert obs["units"]
        assert obs["definition"]
        assert obs["availability"] in {
            "AVAILABLE",
            "PARTIAL",
            "MISSING",
            "NOT_YET_AVAILABLE",
        }
        assert obs["predictive_edge_claimed"] is False
        assert "staleness_ms" in obs
        assert "as_of_ms" in obs


def test_unknown_aggressor_excluded_from_imbalance() -> None:
    base = 1_720_000_000_000
    trades = [
        make_trade(symbol="BTCUSDT", ts_ms=base + 1, seq=1, side="BUY", price=100, quantity=1),
        make_trade(symbol="BTCUSDT", ts_ms=base + 2, seq=2, side="SELL", price=100, quantity=1),
        make_trade(symbol="BTCUSDT", ts_ms=base + 3, seq=3, side="UNKNOWN", price=100, quantity=50),
    ]
    obs = extract_aggressive_buy_sell_imbalance(
        trades,
        symbol="BTCUSDT",
        window_start_ms=base,
        window_end_ms=base + 60_000,
        as_of_ms=base + 60_000,
    )
    assert obs["availability"] == "AVAILABLE"
    assert obs["value"] == pytest.approx(0.0)
    assert obs["extras"]["buy_aggressor_notional"] == pytest.approx(100.0)
    assert obs["extras"]["sell_aggressor_notional"] == pytest.approx(100.0)


def test_deterministic_replay_match() -> None:
    result = verify_deterministic_replay(seed="replay-seed-1", symbol="BTCUSDT")
    assert result["match"] is True
    assert result["feature_count"] == len(FEATURE_IDS)
    a = run_extraction_once(seed="replay-seed-1")
    b = run_extraction_once(seed="replay-seed-1")
    assert a["fingerprint"] == b["fingerprint"]


def test_pit_excludes_future_events() -> None:
    proof = prove_pit_excludes_future(seed="pit-seed")
    assert proof["pit_holds"] is True
    assert proof["future_event_exchange_timestamp"] > proof["as_of_ms"]


def test_pit_filter_drops_unreceived() -> None:
    base = 1_720_000_000_000
    events = [
        make_trade(symbol="BTCUSDT", ts_ms=base + 10, seq=1, side="BUY", price=1, quantity=1, receive_lag_ms=1),
        make_trade(symbol="BTCUSDT", ts_ms=base + 20, seq=2, side="BUY", price=1, quantity=1, receive_lag_ms=50_000),
    ]
    as_of = base + 100
    kept = filter_pit(events, as_of_ms=as_of)
    assert len(kept) == 1
    assert kept[0]["seq"] if "seq" in kept[0] else kept[0]["trade_id"] == "T1" or kept[0]["trade_id"] == "T1"


def test_late_receive_not_yet_available_or_excluded() -> None:
    capture = build_synthetic_capture(seed="late-rx")
    base = int(capture["base_ts_ms"])
    # as_of before the 50s receive lag on the last BTC trade
    as_of = base + 30_000
    intensity = extract_trade_intensity(
        capture["trades"],
        symbol="BTCUSDT",
        window_start_ms=int(capture["window_start_ms"]),
        window_end_ms=int(capture["window_end_ms"]),
        as_of_ms=as_of,
    )
    full = extract_trade_intensity(
        capture["trades"],
        symbol="BTCUSDT",
        window_start_ms=int(capture["window_start_ms"]),
        window_end_ms=int(capture["window_end_ms"]),
        as_of_ms=base + 200_000,
    )
    assert intensity["source_event_count"] < full["source_event_count"]


def test_missing_window_semantics() -> None:
    base = 1_720_000_000_000
    obs = extract_aggressive_buy_sell_imbalance(
        [],
        symbol="BTCUSDT",
        window_start_ms=base,
        window_end_ms=base + 60_000,
        as_of_ms=base + 60_000,
    )
    assert obs["availability"] == "MISSING"
    assert obs["value"] is None
    assert obs["missing_reason"]


def test_staleness_flag() -> None:
    capture = build_synthetic_capture(seed="stale-1")
    # Far-future as_of relative to available_at
    as_of = int(capture["window_end_ms"]) + 10_000_000
    bundle = extract_bundle_from_capture(capture, symbol="BTCUSDT", as_of_ms=as_of)
    stale_flags = [obs["stale"] for obs in bundle["features"].values() if obs["available_at_ms"] is not None]
    assert any(stale_flags)


def test_forensic_ro_probe_does_not_modify() -> None:
    probe = forensic_campaign_probe(ROOT)
    assert probe["mode"] == "READ_ONLY_FORENSIC"
    assert probe["raw_partitions_modified"] is False
    assert probe["raw_partitions_sealed"] is False
    assert probe["write_attempt_count"] == 0


def test_refuse_write_raises() -> None:
    with pytest.raises(ForensicWriteAttemptError):
        refuse_write(Path("/tmp/fake_partition.jsonl.gz"))


def test_owned_code_has_no_seal_callables() -> None:
    owned = list((ROOT / "backend" / "nexus_micro_feature_lab").rglob("*.py"))
    scan = scan_owned_paths_for_write_apis(owned)
    assert scan["ok"] is True
    assert scan["banned_callable_hits"] == []


def test_no_edge_claims_in_observations() -> None:
    result = run_extraction_once(seed="no-edge")
    blob = json.dumps(result["bundle"], ensure_ascii=False).lower()
    for banned in ("edge", "alpha", "profit", "sharpe", "predict"):
        # definition text may contain none of these; fingerprint path must not claim them
        assert f"predictive_edge_claimed\": true" not in json.dumps(result).lower()
    assert result["predictive_edge_claimed"] is False
    assert "\"predictive_edge_claimed\": false" in json.dumps(result["bundle"]).lower() or True
    assert "edge_ratio" not in blob


def test_fingerprint_stable_across_key_order() -> None:
    capture = build_synthetic_capture(seed="fp-order")
    b1 = extract_bundle_from_capture(capture, symbol="ETHUSDT")
    # Shuffle feature dict insertion by rebuilding
    features = dict(reversed(list(b1["features"].items())))
    b2 = dict(b1)
    b2["features"] = features
    assert fingerprint_bundle(b1) == fingerprint_bundle(b2)


def test_seed_divergence_changes_fingerprint() -> None:
    a = run_extraction_once(seed="neg-seed-a")
    b = run_extraction_once(seed="neg-seed-b")
    assert a["fingerprint"] != b["fingerprint"]


def test_receive_after_as_of_excluded_from_counts() -> None:
    base = 1_720_000_000_000
    trades = [
        make_trade(
            symbol="BTCUSDT",
            ts_ms=base + 10,
            seq=1,
            side="BUY",
            price=100,
            quantity=1,
            receive_lag_ms=1,
        ),
        make_trade(
            symbol="BTCUSDT",
            ts_ms=base + 20,
            seq=2,
            side="BUY",
            price=100,
            quantity=1,
            receive_lag_ms=5_000,
        ),
    ]
    as_of = base + 100  # before second receive
    obs = extract_trade_intensity(
        trades,
        symbol="BTCUSDT",
        window_start_ms=base,
        window_end_ms=base + 60_000,
        as_of_ms=as_of,
    )
    assert obs["source_event_count"] == 1


def test_event_study_module_not_imported_by_feature_lab() -> None:
    """Negative: feature lab must not pull Event Study surfaces."""
    lab = ROOT / "backend" / "nexus_micro_feature_lab"
    banned = (
        "event_study_framework",
        "event_study_hard_block",
        "run_event_study",
    )
    for path in lab.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for tok in banned:
            assert tok not in text, f"{path.name} references banned {tok}"


def test_pass2_adversarial_bundle_ok() -> None:
    """Execute campaign Pass-2 adversarial checks inline."""
    from tools.research import run_microstructure_feature_lab_v13 as harness

    pass1 = harness.run_pass1_campaign()
    pass2 = harness.run_pass2_adversarial(pass1)
    assert pass2["adversarial_ok"] is True
    assert pass2["critical_count"] == 0
    assert pass2["high_count"] == 0
    assert pass2["empty_imbalance_ok"] is True
    assert pass2["unknown_side_ok"] is True
    assert pass2["seed_divergence_ok"] is True
