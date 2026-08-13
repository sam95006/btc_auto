"""P0.7 — V2 selected Top1 outcome backfill must not starve behind V1 cursor."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    existing_path_key_status,
    load_path_records,
    refresh_mature_shadow_outcomes,
    v2_priority_horizon_budget,
)
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    load_backfill_progress,
    persist_shadow_signals,
    save_backfill_progress,
    shadow_dir,
)
from backend.nexus_research_ai_autonomy.shadow_v2_challenger_v1 import persist_v2_evidence


class _FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def public_get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        self.calls += 1
        start = int(params.get("start") or 0)
        end = int(params.get("end") or start)
        rows = []
        t = start
        while t <= end:
            rows.append([str(t), "100", "100.5", "99.8", "100.2", "1", "1"])
            t += 60_000
        rows.reverse()
        return {"result": {"list": rows}}


def _v1_sig(sid: str, *, ts: int) -> dict[str, Any]:
    return {
        "signal_id": sid,
        "lifecycle_state": "READY",
        "detected_at_ms": ts,
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "entry_price": 100.0,
        "snapshot_decision_id": f"dec_{sid}",
    }


def _v2_selected(
    sid: str,
    *,
    ts: int,
    action: str = "WAIT",
    episode_id: int,
) -> dict[str, Any]:
    return {
        "schema": "v30_v2_c1_challenger_evidence_v1",
        "signal_id": sid,
        "v2_signal_id": sid,
        "evidence_generation": "POST_V2_FREEZE",
        "selected_cohort": "V2_C1_SELECTED_TOP1_LONG",
        "lane": "LONG_TOP1",
        "action": action,
        "direction": "LONG",
        "symbol": "ETHUSDT",
        "entry_price": 100.0,
        "detected_at_ms": ts,
        "episode_id": episode_id,
        "outcome_eligible": True,
    }


def _v2_short(sid: str, *, ts: int) -> dict[str, Any]:
    return {
        "schema": "v30_v2_c1_challenger_evidence_v1",
        "signal_id": sid,
        "v2_signal_id": sid,
        "evidence_generation": "POST_V2_FREEZE",
        "lane": "SHORT_SHADOW_RESEARCH",
        "action": "WATCH",
        "direction": "SHORT",
        "symbol": "SOLUSDT",
        "entry_price": 100.0,
        "detected_at_ms": ts,
        "episode_id": 777,
    }


def test_v2_priority_budget_leaves_legacy_floor() -> None:
    v2_cap, legacy_floor = v2_priority_horizon_budget(40, v2_pending=10)
    assert v2_cap == 30
    assert legacy_floor == 10
    none_v2, all_legacy = v2_priority_horizon_budget(40, v2_pending=0)
    assert none_v2 == 0
    assert all_legacy == 40


def test_v2_selected_matures_before_legacy_cursor_caught_up(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE", "10")
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_SEC", "30")
    now = int(time.time() * 1000)
    old = now - 3_600_000
    v1 = [_v1_sig(f"sig_{i:04d}", ts=old - i * 1000) for i in range(200)]
    for i in range(0, len(v1), 40):
        persist_shadow_signals(tmp_path, v1[i : i + 40])
    save_backfill_progress(
        tmp_path,
        {"cursor_index": 80, "last_processed_signal_id": "sig_0080", "backfill_status": "PARTIAL"},
    )
    persist_v2_evidence(
        tmp_path,
        [
            _v2_selected("v2sig_wait01", ts=now - 2_000_000, action="WAIT", episode_id=1001),
            _v2_selected("v2sig_block01", ts=now - 2_000_000, action="BLOCK", episode_id=1002),
            _v2_short("v2sig_short01", ts=now - 2_000_000),
        ],
    )
    cursor_before = int(load_backfill_progress(tmp_path)["cursor_index"])
    assert cursor_before == 80

    out = refresh_mature_shadow_outcomes(_FakeClient(), campaign_root=tmp_path)
    keys = existing_path_key_status(tmp_path)
    v2_keys = [k for k in keys if k[0].startswith("v2sig_")]
    v2_selected_keys = [k for k in v2_keys if k[0] in {"v2sig_wait01", "v2sig_block01"}]
    short_keys = [k for k in v2_keys if k[0] == "v2sig_short01"]

    assert out["priority_starvation_prevented"] is True
    assert out["v2_priority_processed_this_cycle"] > 0
    assert out["horizons_processed_this_cycle"] <= 10
    assert v2_selected_keys, "mature V2 selected Top1 must write path/outcome rows in one cycle"
    assert any(sid == "v2sig_wait01" for sid, _h in v2_selected_keys)
    assert any(sid == "v2sig_block01" for sid, _h in v2_selected_keys)
    assert not short_keys, "SHORT research must not enter selected Top1 priority cohort"
    cursor_after = int(load_backfill_progress(tmp_path)["cursor_index"])
    assert cursor_after != 0 or cursor_before == 0
    # Legacy cursor must not have walked the entire V1 ledger in one bounded cycle.
    assert cursor_after < 200
    n_v1 = 200
    assert cursor_after != n_v1
    # Duplicate (signal_id, horizon) forbidden
    recs = load_path_records(tmp_path)
    pairs = [(r.get("signal_id"), int(r.get("horizon_sec") or 0)) for r in recs]
    assert len(pairs) == len(set(pairs))


def test_restart_resumes_without_duplicate_keys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE", "4")
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_SEC", "30")
    now = int(time.time() * 1000)
    old = now - 3_600_000
    persist_shadow_signals(tmp_path, [_v1_sig(f"sig_{i:03d}", ts=old) for i in range(30)])
    save_backfill_progress(tmp_path, {"cursor_index": 10, "backfill_status": "PARTIAL"})
    persist_v2_evidence(
        tmp_path,
        [_v2_selected("v2sig_r1", ts=now - 2_000_000, action="WAIT", episode_id=1)],
    )
    c = _FakeClient()
    a = refresh_mature_shadow_outcomes(c, campaign_root=tmp_path)
    b = refresh_mature_shadow_outcomes(c, campaign_root=tmp_path)
    recs = load_path_records(tmp_path)
    pairs = [(r.get("signal_id"), int(r.get("horizon_sec") or 0)) for r in recs]
    assert len(pairs) == len(set(pairs))
    assert a["horizons_processed_this_cycle"] <= 4
    assert b["horizons_processed_this_cycle"] <= 4
    cursor = int(load_backfill_progress(tmp_path)["cursor_index"])
    assert 0 <= cursor < 30


def test_legacy_uses_full_budget_when_no_v2_pending(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE", "5")
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_SEC", "30")
    old = int(time.time() * 1000) - 3_600_000
    persist_shadow_signals(tmp_path, [_v1_sig(f"sig_{i}", ts=old) for i in range(10)])
    out = refresh_mature_shadow_outcomes(_FakeClient(), campaign_root=tmp_path)
    assert out["v2_priority_pending_before"] == 0
    assert out["v2_priority_processed_this_cycle"] == 0
    assert out["legacy_processed_this_cycle"] == 5
    assert out["horizons_processed_this_cycle"] == 5
