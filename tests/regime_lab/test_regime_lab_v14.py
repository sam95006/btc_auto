"""V14-F Regime and Cross-Asset Lab tests — catalog, PIT, lead-lag, replay."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_regime_lab import (
    HARD_BANS,
    REGIME_IDS,
    ForensicWriteAttemptError,
    build_synthetic_bars,
    classify_bundle_from_capture,
    fingerprint_bundle,
    forensic_campaign_probe,
    lead_lag_from_capture,
    lead_lag_pair,
    prove_lead_lag_no_negative_receive_leak,
    prove_pit_excludes_future,
    refuse_write,
    regime_catalog,
    run_classification_once,
    verify_deterministic_replay,
)
from backend.nexus_regime_lab.fixtures import make_bar
from backend.nexus_regime_lab.forensic_ro import scan_owned_paths_for_write_apis
from backend.nexus_regime_lab.pit import filter_pit
from backend.nexus_regime_lab.regimes import classify_volatility_regime

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_covers_all_regimes_with_semantics() -> None:
    cat = regime_catalog()
    assert cat["regime_count"] == len(REGIME_IDS)
    assert cat["predictive_edge_claimed"] is False
    assert set(cat["regimes"]) == set(REGIME_IDS)
    common = cat["common_semantics"]
    for key in (
        "timestamp_semantics",
        "availability_semantics",
        "missing_data_behavior",
        "staleness_semantics",
        "lead_lag_semantics",
    ):
        assert key in common
    for rid, meta in cat["regimes"].items():
        assert meta["definition"]
        assert meta["units"]
        assert "semantics_ref" in meta
        assert meta["labels"]


def test_hard_bans_document_false_flags() -> None:
    assert HARD_BANS["predictive_edge_claims"] is False
    assert HARD_BANS["demo_orders"] is False
    assert HARD_BANS["exchange_write"] is False
    assert HARD_BANS["pr27_merge"] is False
    assert HARD_BANS["auto_integrate"] is False
    assert HARD_BANS["formal_walk_forward"] is False
    assert HARD_BANS["strategy_promotion"] is False


def test_synthetic_fixture_deterministic() -> None:
    a = build_synthetic_bars(seed="det-1")
    b = build_synthetic_bars(seed="det-1")
    assert a["fixture_checksum"] == b["fixture_checksum"]
    assert a["bar_count"] == b["bar_count"]
    c = build_synthetic_bars(seed="det-2")
    assert c["fixture_checksum"] != a["fixture_checksum"]


def test_classify_all_regimes_bundle() -> None:
    capture = build_synthetic_bars(seed="bundle-1")
    as_of = int(capture["window_end_ms"]) + 1_000
    bundle = classify_bundle_from_capture(capture, symbol="BTCUSDT", as_of_ms=as_of)
    assert set(bundle["regimes"]) == set(REGIME_IDS)
    for rid, obs in bundle["regimes"].items():
        assert obs["regime_id"] == rid
        assert obs["units"]
        assert obs["definition"]
        assert obs["availability"] in {
            "AVAILABLE",
            "PARTIAL",
            "MISSING",
            "NOT_YET_AVAILABLE",
        }
        assert obs["predictive_edge_claimed"] is False
        assert obs["strategy_signal"] is False
        assert "staleness_ms" in obs
        assert "as_of_ms" in obs


def test_deterministic_replay_match() -> None:
    result = verify_deterministic_replay(seed="replay-seed-1", symbol="BTCUSDT")
    assert result["match"] is True
    assert result["regime_count"] == len(REGIME_IDS)
    a = run_classification_once(seed="replay-seed-1")
    b = run_classification_once(seed="replay-seed-1")
    assert a["fingerprint"] == b["fingerprint"]
    assert a["lead_lag_fingerprint"] == b["lead_lag_fingerprint"]


def test_pit_excludes_future_bars() -> None:
    proof = prove_pit_excludes_future(seed="pit-seed")
    assert proof["pit_holds"] is True
    assert proof["regime_pit_holds"] is True
    assert proof["lead_lag_pit_holds"] is True
    assert proof["future_bar_exchange_timestamp"] > proof["as_of_ms"]


def test_lead_lag_receive_pit() -> None:
    proof = prove_lead_lag_no_negative_receive_leak(seed="ll-rx")
    assert proof["pit_holds"] is True
    assert proof["injected_receive_timestamp"] > proof["as_of_ms"]
    assert proof["trading_claim"] is False


def test_lead_lag_non_claim() -> None:
    capture = build_synthetic_bars(seed="ll-1")
    as_of = int(capture["window_end_ms"]) + 1_000
    ll = lead_lag_from_capture(capture, as_of_ms=as_of)
    assert ll["predictive_edge_claimed"] is False
    assert ll["trading_claim"] is False
    assert ll["strategy_signal"] is False
    assert "lags" in ll
    assert ll["availability"] in {"AVAILABLE", "PARTIAL", "NOT_YET_AVAILABLE", "MISSING"}


def test_pit_filter_drops_unreceived() -> None:
    base = 1_720_000_000_000
    bars = [
        make_bar(
            symbol="BTCUSDT",
            exchange_timestamp=base + 10,
            receive_lag_ms=1,
            close=100,
            volume_notional=1,
            seq=1,
        ),
        make_bar(
            symbol="BTCUSDT",
            exchange_timestamp=base + 20,
            receive_lag_ms=50_000,
            close=101,
            volume_notional=1,
            seq=2,
        ),
    ]
    as_of = base + 100
    kept = filter_pit(bars, as_of_ms=as_of)
    assert len(kept) == 1
    assert kept[0]["sequence_or_dedup_key"].endswith(":1")


def test_missing_window_semantics() -> None:
    base = 1_720_000_000_000
    obs = classify_volatility_regime(
        [],
        symbol="BTCUSDT",
        as_of_ms=base + 60_000,
    )
    assert obs["availability"] == "MISSING"
    assert obs["label"] is None
    assert obs["missing_reason"]


def test_staleness_flag() -> None:
    capture = build_synthetic_bars(seed="stale-1")
    # Beyond late-receive lag (90s) + default stale_after_ms (180s)
    as_of = int(capture["window_end_ms"]) + 300_000
    bundle = classify_bundle_from_capture(capture, symbol="BTCUSDT", as_of_ms=as_of)
    stale_flags = [
        obs["stale"] for obs in bundle["regimes"].values() if obs["available_at_ms"] is not None
    ]
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
    owned = list((ROOT / "backend" / "nexus_regime_lab").rglob("*.py"))
    scan = scan_owned_paths_for_write_apis(owned)
    assert scan["ok"] is True
    assert scan["banned_callable_hits"] == []


def test_seed_divergence_changes_fingerprint() -> None:
    a = run_classification_once(seed="adv-a")
    b = run_classification_once(seed="adv-b")
    assert a["fingerprint"] != b["fingerprint"]


def test_lead_lag_pair_structure() -> None:
    capture = build_synthetic_bars(seed="pair-1")
    as_of = int(capture["window_end_ms"]) + 1_000
    pair = lead_lag_pair(
        capture["bars"],
        leader="BTCUSDT",
        follower="ETHUSDT",
        as_of_ms=as_of,
        bar_ms=int(capture["bar_ms"]),
    )
    assert pair["schema"] == "v14_f_lead_lag_pair"
    assert "0" in pair["lags"]
    assert pair["non_claim"]
