"""Focused tests for V18.2.19 market summary history (no fabricated points)."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from backend.market.live_radar.market_summary_history import (
    MarketSummaryHistoryStore,
    derive_regime_label,
)


def test_derive_regime_basic():
    assert derive_regime_label({"rising": 40, "falling": 10, "neutral": 20, "insufficient": 0}, 70) == "偏多"
    assert derive_regime_label({"rising": 5, "falling": 40, "neutral": 20, "insufficient": 0}, 70) == "偏空"


def test_history_refuses_empty_shell():
    with tempfile.TemporaryDirectory() as td:
        store = MarketSummaryHistoryStore(root=Path(td))
        assert store.maybe_record({"timestamp": int(time.time() * 1000)}) is False
        assert store.list_points() == []


def test_history_records_real_point_and_reports_zero_fabricated():
    with tempfile.TemporaryDirectory() as td:
        store = MarketSummaryHistoryStore(root=Path(td))
        now = int(time.time() * 1000)
        ok = store.maybe_record(
            {
                "timestamp": now,
                "rising": 12,
                "neutral": 8,
                "falling": 5,
                "regime": "偏多",
                "market_risk": 3,
                "scanner_count": 80,
                "radar_eligible_count": 40,
                "trade_count": 2,
                "qualified_count": 0,
                "events_new": 1,
                "events_up": 2,
                "events_down": 0,
                "events_out": 0,
            },
            force=True,
        )
        assert ok is True
        body = store.public_history(hours=24)
        assert body["fabricated_visual_count"] == 0
        assert body["count"] == 1
        assert body["points"][0]["fabricated"] is False
        assert body["points"][0]["radar_eligible_count"] == 40
        assert (
            store.maybe_record(
                {
                    "timestamp": now + 60_000,
                    "rising": 13,
                    "falling": 4,
                    "neutral": 8,
                    "radar_eligible_count": 41,
                }
            )
            is False
        )


def test_history_jsonl_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        store = MarketSummaryHistoryStore(root=root)
        now = int(time.time() * 1000)
        store.maybe_record(
            {
                "timestamp": now,
                "rising": 1,
                "falling": 1,
                "neutral": 1,
                "radar_eligible_count": 9,
                "regime": "多空混合",
            },
            force=True,
        )
        path = root / "market_summary_history.jsonl"
        assert path.exists()
        line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
        pt = json.loads(line)
        assert pt["radar_eligible_count"] == 9
        reloaded = MarketSummaryHistoryStore(root=root)
        assert reloaded.list_points()[0]["radar_eligible_count"] == 9
