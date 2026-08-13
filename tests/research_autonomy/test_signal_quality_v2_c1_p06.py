"""P0.6 focused tests — Champion/Challenger thesis state isolation."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from backend.nexus_research_ai_autonomy.anti_churn_thesis_v1 import (
    evaluate_thesis_novelty,
    record_thesis,
    thesis_state_path,
)
from backend.nexus_research_ai_autonomy.shadow_v2_challenger_v1 import (
    build_shadow_v2_challenger_report,
    load_v2_c1_shadow_signals,
    run_v2_c1_shadow_challenger,
)
from backend.nexus_research_ai_autonomy.signal_quality_cycle_v1 import run_signal_quality_shadow_cycle
from backend.nexus_research_ai_autonomy.v2_c1_thesis_v1 import (
    ACTION_EVIDENCE_POST_ISOLATION,
    ACTION_EVIDENCE_PRE_ISOLATION,
    V2_THESIS_NAMESPACE,
    action_evidence_epoch,
    evaluate_v2_c1_thesis_novelty,
    record_v2_c1_thesis,
    resolve_abstention_diagnostic,
    v2_c1_thesis_state_path,
)


def _enrichment(*, sym: str = "APRUSDT", ts: int | None = None) -> dict[str, Any]:
    return {
        "symbol": sym,
        "timestamp_ms": ts or int(time.time() * 1000),
        "price": 1.0,
        "turnover": 20_000_000,
        "spread_bps": 3.0,
        "estimated_slippage": 0.0003,
        "activity_score": 0.72,
        "momentum_1m": {"return": 0.05},
        "momentum_5m": {"return": 0.12},
        "momentum_15m": {"return": 0.08},
        "volatility": 0.35,
        "open_interest": 1000.0,
        "oi_delta_short": 0.02,
        "funding_rate": 0.0001,
        "data_freshness_ms": 50,
    }


def _regime() -> dict[str, Any]:
    return {"market_structure": "TREND_UP", "regime": "TREND_UP", "regime_confidence": 0.7}


def _snapshot(sym: str = "APRUSDT", ts: int | None = None) -> dict[str, Any]:
    e = _enrichment(sym=sym, ts=ts)
    r = _regime()
    return {**e, **r, "side": "LONG", "expected_net_edge": 1.0}


def test_v1_select_records_v1_thesis(tmp_path: Path) -> None:
    snap = _snapshot()
    snap["final_action"] = "SELECT"
    record_thesis(tmp_path, snap)
    assert thesis_state_path(tmp_path).exists()
    state = json.loads(thesis_state_path(tmp_path).read_text(encoding="utf-8"))
    assert "APRUSDT|LONG" in state


def test_v1_thesis_write_does_not_affect_v2_evaluation(tmp_path: Path) -> None:
    snap = _snapshot()
    record_thesis(tmp_path, snap)
    v2 = evaluate_v2_c1_thesis_novelty(
        campaign_root=tmp_path, symbol="APRUSDT", side="LONG", current_snapshot=snap
    )
    assert v2["pass"] is True
    assert v2["reason"] == "no_prior_thesis"
    assert not v2_c1_thesis_state_path(tmp_path).exists()


def test_first_v2_thesis_passes_without_prior_v2(tmp_path: Path) -> None:
    snap = _snapshot()
    result = evaluate_v2_c1_thesis_novelty(
        campaign_root=tmp_path, symbol="APRUSDT", side="LONG", current_snapshot=snap
    )
    assert result["pass"] is True
    assert result["thesis_namespace"] == V2_THESIS_NAMESPACE


def test_v2_ready_records_v2_thesis_only(tmp_path: Path) -> None:
    from backend.nexus_research_ai_autonomy.signal_quality_v2_c1 import (
        materialize_v2_evidence,
        select_v2_c1_for_episode,
    )
    from backend.nexus_research_ai_autonomy.signal_quality_v1 import (
        compute_entry_quality,
        compute_expected_net_edge,
    )
    from unittest.mock import patch

    ts = int(time.time() * 1000)
    enrichment = _enrichment(ts=ts)
    regime_info = _regime()
    edge = compute_expected_net_edge(enrichment=enrichment, side="LONG", notional=350.0)
    eq = compute_entry_quality(
        enrichment, side="LONG", structure="TREND_UP", regime="TREND_UP", edge=edge
    )
    row = {
        "symbol": "APRUSDT",
        "enrichment": enrichment,
        "regime_info": regime_info,
        "gate_pass": True,
        "timestamp_ms": ts,
        "snapshot": {"final_action": "SELECT", "rank": 1, "entry_quality_score": eq.get("entry_quality_score")},
    }
    with patch(
        "backend.nexus_research_ai_autonomy.signal_quality_v2_c1.evaluate_v2_c1_thesis_novelty",
        return_value={"pass": True, "reason": "no_prior_thesis"},
    ), patch(
        "backend.nexus_research_ai_autonomy.signal_quality_v2_c1._v2_abstention_action",
        return_value=("READY", "V2_C1_LONG_TOP1_READY"),
    ):
        sel = select_v2_c1_for_episode([row], campaign_root=tmp_path, now_ms=ts)
        sel["long_top1"]["thesis_snapshot"] = _snapshot(ts=ts)
        evidence = materialize_v2_evidence(sel, cycle_id="cyc", now_ms=ts)
        from backend.nexus_research_ai_autonomy.shadow_v2_challenger_v1 import persist_v2_evidence

        persist_v2_evidence(tmp_path, evidence)
        record_v2_c1_thesis(tmp_path, sel["long_top1"]["thesis_snapshot"])
    assert v2_c1_thesis_state_path(tmp_path).exists()
    v2_state = json.loads(v2_c1_thesis_state_path(tmp_path).read_text(encoding="utf-8"))
    assert v2_state["APRUSDT|LONG"]["thesis_namespace"] == V2_THESIS_NAMESPACE


def test_second_unchanged_v2_ready_blocked_by_v2_prior(tmp_path: Path) -> None:
    snap = _snapshot()
    record_v2_c1_thesis(tmp_path, snap)
    blocked = evaluate_v2_c1_thesis_novelty(
        campaign_root=tmp_path, symbol="APRUSDT", side="LONG", current_snapshot=snap
    )
    assert blocked["pass"] is False
    assert blocked["reason"] == "REPEATED_THESIS_NO_NEW_EDGE"


def test_material_evidence_change_allows_v2_novelty(tmp_path: Path) -> None:
    snap = _snapshot()
    record_v2_c1_thesis(tmp_path, snap)
    changed = {**snap, "regime": "TREND_DOWN", "market_structure": "TREND_DOWN"}
    ok = evaluate_v2_c1_thesis_novelty(
        campaign_root=tmp_path, symbol="APRUSDT", side="LONG", current_snapshot=changed
    )
    assert ok["pass"] is True
    assert "regime_changed" in ok["material_changes"]


def test_v2_never_mutates_v1_thesis_state(tmp_path: Path) -> None:
    snap = _snapshot()
    record_thesis(tmp_path, snap)
    before = thesis_state_path(tmp_path).read_text(encoding="utf-8")
    record_v2_c1_thesis(tmp_path, {**snap, "expected_net_edge": 2.0})
    after = thesis_state_path(tmp_path).read_text(encoding="utf-8")
    assert before == after


def test_v1_never_reads_v2_thesis_state(tmp_path: Path) -> None:
    snap = _snapshot()
    record_v2_c1_thesis(tmp_path, snap)
    v1 = evaluate_thesis_novelty(
        campaign_root=tmp_path, symbol="APRUSDT", side="LONG", current_snapshot=snap
    )
    assert v1["pass"] is True
    assert v1["reason"] == "no_prior_thesis"


def test_selection_top1_cohort_unchanged(tmp_path: Path) -> None:
    from backend.nexus_research_ai_autonomy.signal_quality_v2_c1 import (
        EPISODE_WINDOW_SEC,
        SELECTED_COHORT_NAME,
    )

    ts = int(time.time() * 1000)
    from backend.nexus_research_ai_autonomy.signal_quality_v2_c1 import select_v2_c1_for_episode

    row = {
        "symbol": "APRUSDT",
        "enrichment": _enrichment(ts=ts),
        "regime_info": _regime(),
        "gate_pass": False,
        "timestamp_ms": ts,
        "snapshot": {},
    }
    sel = select_v2_c1_for_episode([row], campaign_root=tmp_path, now_ms=ts)
    assert sel["episode_window_sec"] == EPISODE_WINDOW_SEC
    assert sel["long_top1"] is not None


def test_existing_selected_post_v2_freeze_preserved(tmp_path: Path) -> None:
    ledger = tmp_path / "autonomy" / "shadow_signals" / "v2_c1_shadow_signals.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    legacy = {
        "signal_id": "v2sig_legacy01",
        "evidence_generation": "POST_V2_FREEZE",
        "lane": "LONG_TOP1",
        "selected_cohort": "V2_C1_SELECTED_TOP1_LONG",
        "action": "BLOCK",
        "episode_id": 1,
    }
    ledger.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    loaded = load_v2_c1_shadow_signals(tmp_path)
    assert len(loaded) == 1
    assert loaded[0]["signal_id"] == "v2sig_legacy01"


def test_action_pre_post_isolation_epochs_separated() -> None:
    pre = {"action_evidence_generation": ACTION_EVIDENCE_PRE_ISOLATION}
    post = {"action_evidence_generation": ACTION_EVIDENCE_POST_ISOLATION}
    legacy = {}
    assert action_evidence_epoch(pre) == ACTION_EVIDENCE_PRE_ISOLATION
    assert action_evidence_epoch(post) == ACTION_EVIDENCE_POST_ISOLATION
    assert action_evidence_epoch(legacy) == ACTION_EVIDENCE_PRE_ISOLATION


def test_legacy_missing_diagnostic_not_other() -> None:
    assert resolve_abstention_diagnostic({}) == "legacy_missing"
    assert resolve_abstention_diagnostic({"abstention_diagnostic": "repeated_thesis"}) == "repeated_thesis"


def test_demo_write_false() -> None:
    report = build_shadow_v2_challenger_report(Path("/nonexistent"))
    assert report["ready_for_demo_reenable"] is False
    assert report["champion_challenger_thesis_isolated"] is True
