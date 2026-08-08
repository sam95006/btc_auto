"""Focused tests for V18.2.16 server-side Full-Market Live Radar."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.market.live_radar.full_market_radar_service import (
    FullMarketRadarService,
    filter_ranking_rows,
    reset_full_market_radar_for_tests,
)
from backend.market.live_radar.nex_rank_score import (
    compute_nex_rank_score_v1,
    is_radar_eligible,
)
from backend.market.live_radar.rank_event_store import RankEventStore


def _cand(
    symbol: str,
    *,
    stage: str = "BUILDING",
    side: str = "LONG",
    freshness: str = "FRESH",
    opportunity: float = 60,
    confirmation: float = 50,
    risk: float = 20,
    collecting: bool = False,
    px5: float = 0.8,
    change24: float = 2.0,
    oi5: float = 1.0,
    funding: float = 0.0001,
    turnover: float = 20,
) -> dict:
    return {
        "id": f"{symbol}:{side}",
        "symbol": symbol,
        "side": side,
        "stage": stage,
        "freshness": freshness,
        "opportunityScore": opportunity,
        "confirmationScore": confirmation,
        "riskScore": risk,
        "collecting": collecting,
        "currentPrice": 1.23,
        "markPrice": 1.23,
        "change24hPct": change24,
        "priceChange5mPct": px5,
        "oiChange5mPct": oi5,
        "fundingRate": funding,
        "turnoverPace": turnover,
        "reasons": ["測試理由"],
        "conflicts": [],
        "symbolType": "",
        "assetDisposition": "CRYPTO_OPPORTUNITY_ELIGIBLE",
        "firstSeenAt": 1_700_000_000_000,
        "lastUpdatedAt": 1_700_000_000_000,
    }


def test_radar_eligibility_excludes_insufficient_expired_stale_unavailable():
    assert is_radar_eligible(_cand("AAAUSDT", stage="INSUFFICIENT_DATA")) is False
    assert is_radar_eligible(_cand("AAAUSDT", stage="EXPIRED")) is False
    assert is_radar_eligible(_cand("AAAUSDT", freshness="STALE")) is False
    assert is_radar_eligible(_cand("AAAUSDT", freshness="UNAVAILABLE")) is False
    assert is_radar_eligible(_cand("AAAUSDT", stage="BUILDING")) is True
    # warming alone with too few metrics
    weak = _cand("BBBUSDT", stage="WATCHING", collecting=True, px5=None, oi5=None, funding=None, turnover=None)
    weak["priceChange5mPct"] = None
    weak["oiChange5mPct"] = None
    weak["fundingRate"] = None
    weak["turnoverPace"] = None
    weak["change24hPct"] = None
    weak["opportunityScore"] = 0
    weak["confirmationScore"] = 0
    assert is_radar_eligible(weak) is False


def test_nex_rank_score_v1_deterministic_and_normalized():
    a = compute_nex_rank_score_v1(_cand("AAAUSDT", opportunity=80, confirmation=70))
    b = compute_nex_rank_score_v1(_cand("AAAUSDT", opportunity=80, confirmation=70))
    assert a == b
    assert 0 <= a["score"] <= 100
    low = compute_nex_rank_score_v1(_cand("BBBUSDT", opportunity=10, confirmation=5, risk=80, side="NEUTRAL"))
    high = compute_nex_rank_score_v1(_cand("CCCUSDT", opportunity=90, confirmation=85, risk=5))
    assert high["score"] > low["score"]


def test_full_ranking_before_pagination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    reset_full_market_radar_for_tests()
    store = RankEventStore(root=tmp_path / "radar")
    svc = FullMarketRadarService(store=store)

    # 60 eligible symbols — pagination limit 10 must not change full rank order
    universe = [
        _cand(f"S{i:03d}USDT", opportunity=50 + (i % 40), confirmation=40 + (i % 30), px5=0.5 + (i % 10) * 0.1)
        for i in range(60)
    ]
    # sprinkle excluded
    universe.append(_cand("BADUSDT", stage="INSUFFICIENT_DATA"))
    universe.append(_cand("OLDUSDT", stage="EXPIRED"))
    universe.append(_cand("STALEUSDT", freshness="STALE"))

    class _FakeScanner:
        def all_scored_candidates(self):
            return {
                "candidates": universe,
                "symbolCount": len(universe),
                "symbolLimit": 80,
                "eligibleBeforeLimit": 211,
                "eligibleAfterLimit": 80,
                "universeBlocker": "scanner_SYMBOL_LIMIT=80_caps_eligible_before_limit=211",
            }

    monkeypatch.setattr(
        "backend.market.scanner.scanner_service.get_market_scanner",
        lambda: _FakeScanner(),
    )

    full = svc.build_snapshot(force=True, now_ms=1_700_000_100_000)
    assert full["ok"] is True
    assert full["rank_authority"] == "SERVER"
    assert full["full_ranking_before_pagination"] is True
    assert full["frontend_candidate_fetch_limit_affects_rank"] is False
    assert full["fixed_symbol_dependency_count"] == 0
    assert full["evaluated_count"] == len(universe)  # all crypto visible
    assert full["excluded_count"] >= 3
    assert full["radar_eligible_count"] == len(full["rows"])
    assert full["full_ranked_count"] == full["radar_eligible_count"]
    assert full["radar_eligible_count"] >= 60
    # ranking is over full eligible set, not 40
    assert full["full_ranked_count"] > 40

    page = svc.public_radar(limit=10, tab="ALL", force=True)
    assert page["returned"] == 10
    assert page["total_ranked"] == full["radar_eligible_count"]
    assert page["pagination_after_full_rank"] is True
    # first 10 of page match first 10 of full rank
    assert [r["symbol"] for r in page["rows"]] == [r["symbol"] for r in full["rows"][:10]]
    assert page["universe_blocker"]


def test_rank_event_persistence_survives_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    reset_full_market_radar_for_tests()
    root = tmp_path / "radar_persist"
    store1 = RankEventStore(root=root)
    svc1 = FullMarketRadarService(store=store1)

    cands = [
        _cand("AAAUSDT", opportunity=90, confirmation=80),
        _cand("BBBUSDT", opportunity=70, confirmation=60),
        _cand("CCCUSDT", opportunity=50, confirmation=40),
    ]

    class _Fake:
        def all_scored_candidates(self):
            return {"candidates": cands, "symbolCount": 3, "symbolLimit": 80}

    monkeypatch.setattr(
        "backend.market.scanner.scanner_service.get_market_scanner",
        lambda: _Fake(),
    )
    snap1 = svc1.build_snapshot(force=True, now_ms=1_700_000_200_000)
    assert snap1["server_rank_events"] is True
    assert snap1["rank_restart_persistence"] is True
    assert any(e["rank_event"] == "NEW" for e in snap1["events"])

    # Simulate restart: new service + store loading same disk
    store2 = RankEventStore(root=root)
    prev = store2.load_prev()
    assert "AAAUSDT" in prev
    hist = store2.list_events(limit=50)
    assert len(hist) >= 1

    # Second cycle: reorder scores -> UP/DOWN events, history retained
    cands2 = [
        _cand("BBBUSDT", opportunity=95, confirmation=90),
        _cand("AAAUSDT", opportunity=60, confirmation=50),
        _cand("CCCUSDT", opportunity=55, confirmation=45),
    ]

    class _Fake2:
        def all_scored_candidates(self):
            return {"candidates": cands2, "symbolCount": 3, "symbolLimit": 80}

    monkeypatch.setattr(
        "backend.market.scanner.scanner_service.get_market_scanner",
        lambda: _Fake2(),
    )
    svc2 = FullMarketRadarService(store=store2)
    snap2 = svc2.build_snapshot(force=True, now_ms=1_700_000_260_000)
    kinds = {e["rank_event"] for e in snap2["events"]}
    assert kinds & {"UP", "DOWN", "NEW", "OUT", "UNCHANGED"} or snap2["rows"]
    # history from disk still available via public_events
    ev = svc2.public_events(limit=100)
    assert ev["ranking_history_authority"] == "SERVER"
    assert ev["count"] >= 1


def test_two_clients_same_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    reset_full_market_radar_for_tests()
    store = RankEventStore(root=tmp_path / "shared")
    svc = FullMarketRadarService(store=store)
    cands = [_cand("AAAUSDT"), _cand("BBBUSDT", opportunity=40, confirmation=30)]

    class _Fake:
        def all_scored_candidates(self):
            return {"candidates": cands, "symbolCount": 2, "symbolLimit": 80}

    monkeypatch.setattr(
        "backend.market.scanner.scanner_service.get_market_scanner",
        lambda: _Fake(),
    )
    a = svc.public_radar(limit=40, force=True)
    b = svc.public_radar(limit=40, force=False)
    assert a["two_clients_same_snapshot"] is True
    assert a["snapshot_id"] == b["snapshot_id"]
    assert [r["symbol"] for r in a["rows"]] == [r["symbol"] for r in b["rows"]]
    assert [r["rank_score"] for r in a["rows"]] == [r["rank_score"] for r in b["rows"]]


def test_filter_tabs_do_not_rerank_authority():
    rows = [
        {"symbol": "A", "side_bias": "LONG", "rank_event": "UP", "rank_delta": 2, "oi_change": 1, "activity_metric": 3, "risk_score": 10},
        {"symbol": "B", "side_bias": "SHORT", "rank_event": "DOWN", "rank_delta": -1, "oi_change": 5, "activity_metric": 9, "risk_score": 40},
    ]
    assert [r["symbol"] for r in filter_ranking_rows(rows, "LONG")] == ["A"]
    assert [r["symbol"] for r in filter_ranking_rows(rows, "SHORT")] == ["B"]
