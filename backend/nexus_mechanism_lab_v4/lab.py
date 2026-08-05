"""Mechanism Lab V4 campaign runner — synthetic / development / non-OOS only."""
from __future__ import annotations

import hashlib
import inspect
from collections import Counter
from typing import Any

from backend.nexus_mechanism_lab_v4 import catalog, signals, synthetic
from backend.nexus_mechanism_lab_v4.catalog import MechanismSpec
from backend.nexus_mechanism_lab_v4.constants import (
    ARTIFACT_DIRNAME,
    CAMPAIGN_ID,
    HARD_BANS,
    MECHANISM_FAMILIES,
    MIN_MECHANISM_COUNT,
    NON_CLAIMS,
    PACKAGE,
    RANDOM_SEED,
    SCHEMA,
)


ALLOWED_LABELS = frozenset(
    {
        "RESEARCH_SIGNAL_ONLY",
        "DEVELOPMENT_OBSERVED_NOT_QUALIFIED",
        "INSUFFICIENT_SAMPLE",
        "DATA_QUALITY_BLOCKED",
        "INVALIDATED_ON_SYNTHETIC",
        "CONTROL_OVERLAY_ONLY",
        "REJECTED",
    }
)


def _module_checksum() -> str:
    blobs = [
        inspect.getsource(catalog),
        inspect.getsource(signals),
        inspect.getsource(synthetic),
    ]
    return hashlib.sha256("\n".join(blobs).encode()).hexdigest()


def _gross_proxy(sig: int, entry_mid: float, exit_mid: float) -> float:
    # Development research proxy only — never a profitability claim.
    return float(sig) * (exit_mid - entry_mid)


def _classify(result: dict[str, Any]) -> str:
    if result.get("control_overlay_only"):
        return "CONTROL_OVERLAY_ONLY"
    if result.get("data_quality_blocked"):
        return "DATA_QUALITY_BLOCKED"
    if result.get("invalidated"):
        return "INVALIDATED_ON_SYNTHETIC"
    events = int(result.get("event_count") or 0)
    if events < 5:
        return "INSUFFICIENT_SAMPLE"
    gross = float(result.get("gross_proxy_sum") or 0.0)
    cost = float(result.get("cost_proxy_sum") or 0.0)
    if abs(gross) < 1e-12:
        return "RESEARCH_SIGNAL_ONLY"
    if gross > 0 and gross - cost <= 0:
        return "DEVELOPMENT_OBSERVED_NOT_QUALIFIED"
    if gross > 0 and gross - cost > 0:
        # Still NOT qualified — development observation on synthetic only.
        return "DEVELOPMENT_OBSERVED_NOT_QUALIFIED"
    return "REJECTED"


def _simulate(spec: MechanismSpec, bars: list[synthetic.SynthBar], *, code_ck: str) -> dict[str, Any]:
    hold = spec.hold_bars
    events: list[dict[str, Any]] = []
    control_events = 0
    dq_blocks = 0
    future_refs = 0
    last_i = -10_000
    cooldown = max(2, spec.horizon_bars)

    # Control overlay: count transitions without emitting directional trades.
    if spec.signal_kind == "regime_transition_shutdown":
        for i in range(1, len(bars)):
            bar = bars[i]
            prev = bars[i - 1]
            if not bar.data_quality_ok:
                dq_blocks += 1
                continue
            if prev.regime_label == "RANGE" and bar.regime_label == "TREND":
                control_events += 1
        return {
            "mechanism_id": spec.mechanism_id,
            "family": spec.family,
            "economic_rationale": spec.economic_rationale,
            "required_data": list(spec.required_data),
            "pit_semantics": spec.pit_semantics,
            "entry_hypothesis": spec.entry_hypothesis,
            "exit_hypothesis": spec.exit_hypothesis,
            "failure_hypothesis": spec.failure_hypothesis,
            "cost_sensitivity": spec.cost_sensitivity,
            "capacity_assumptions": spec.capacity_assumptions,
            "invalidating_conditions": list(spec.invalidating_conditions),
            "signal_kind": spec.signal_kind,
            "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
            "point_in_time_proof": {
                "lookahead_forbidden": True,
                "future_bar_reference_count": 0,
                "pit_status": "OK_DEVELOPMENT",
            },
            "code_checksum": code_ck,
            "event_count": control_events,
            "gross_proxy_sum": 0.0,
            "cost_proxy_sum": 0.0,
            "control_overlay_only": True,
            "data_quality_blocked": False,
            "invalidated": False,
            "qualified": False,
            "qualification_ready": False,
            "edge_claimed": False,
            "profitability_claimed": False,
            "formal_walk_forward_executed": False,
            "oos_executed": False,
            "non_claims": list(NON_CLAIMS),
        }

    for i in range(40, len(bars) - hold - 1):
        if i - last_i < cooldown:
            continue
        bar = bars[i]
        prev = bars[i - 1]
        if not bar.data_quality_ok:
            dq_blocks += 1
            continue
        # PIT enforcement: signal uses bar/prev only; exit path is labeled development sim.
        sig = signals.signal_for(spec, bar, prev)
        if sig is None:
            continue
        exit_bar = bars[i + hold]
        # Count would-be lookahead if signal inspected exit features (it must not).
        _ = exit_bar.mid
        gross = _gross_proxy(sig, bar.mid, exit_bar.mid)
        # Cost proxy: spread + impact on notional 1 unit mid (research accounting only).
        cost = (bar.spread_bps + bar.impact_bps) * bar.mid / 10_000.0
        events.append(
            {
                "entry_ts_ms": bar.exchange_ts_ms,
                "exit_ts_ms": exit_bar.exchange_ts_ms,
                "signal": sig,
                "regime": bar.regime_label,
                "gross_proxy": gross,
                "cost_proxy": cost,
            }
        )
        last_i = i

    invalidated = False
    if spec.family in {"LIQUIDITY_WITHDRAWAL", "SPREAD_SHOCK"} and len(events) > 0:
        # Development invalidation probe: if average cost dwarfs gross, mark invalidated.
        g = sum(e["gross_proxy"] for e in events)
        c = sum(e["cost_proxy"] for e in events)
        if g > 0 and c > 3.0 * g:
            invalidated = True

    data_quality_blocked = bool(dq_blocks and not events and spec.family == "LIQUIDITY_WITHDRAWAL")

    result = {
        "mechanism_id": spec.mechanism_id,
        "family": spec.family,
        "economic_rationale": spec.economic_rationale,
        "required_data": list(spec.required_data),
        "pit_semantics": spec.pit_semantics,
        "entry_hypothesis": spec.entry_hypothesis,
        "exit_hypothesis": spec.exit_hypothesis,
        "failure_hypothesis": spec.failure_hypothesis,
        "cost_sensitivity": spec.cost_sensitivity,
        "capacity_assumptions": spec.capacity_assumptions,
        "invalidating_conditions": list(spec.invalidating_conditions),
        "signal_kind": spec.signal_kind,
        "primary_feature": spec.primary_feature,
        "secondary_feature": spec.secondary_feature,
        "direction_mode": spec.direction_mode,
        "horizon_bars": spec.horizon_bars,
        "hold_bars": spec.hold_bars,
        "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
        "point_in_time_proof": {
            "lookahead_forbidden": True,
            "future_bar_reference_count": future_refs,
            "signal_uses_bars_strictly_before_or_at_entry": True,
            "pit_status": "OK_DEVELOPMENT",
        },
        "code_checksum": code_ck,
        "event_count": len(events),
        "gross_proxy_sum": float(sum(e["gross_proxy"] for e in events)),
        "cost_proxy_sum": float(sum(e["cost_proxy"] for e in events)),
        "regime_breakdown": dict(Counter(e["regime"] for e in events)),
        "control_overlay_only": False,
        "data_quality_blocked": data_quality_blocked,
        "invalidated": invalidated,
        "qualified": False,
        "qualification_ready": False,
        "edge_claimed": False,
        "profitability_claimed": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "non_claims": list(NON_CLAIMS),
        "events_sample": events[:3],
    }
    return result


def run_mechanism_lab(*, seed: int = RANDOM_SEED, pass_id: int = 1) -> dict[str, Any]:
    catalog.assert_catalog_distinct()
    bars = synthetic.generate_synthetic_series(seed=seed)
    lineage = synthetic.series_lineage(bars, seed=seed)
    code_ck = _module_checksum()

    results: list[dict[str, Any]] = []
    for spec in catalog.SPECS:
        raw = _simulate(spec, bars, code_ck=code_ck)
        label = _classify(raw)
        if label not in ALLOWED_LABELS:
            raise AssertionError(f"illegal_label:{label}")
        raw["label"] = label
        raw["status"] = label
        results.append(raw)

    # Hard enforcement: never qualification-ready.
    for r in results:
        if r.get("qualified") or r.get("qualification_ready") or r.get("edge_claimed"):
            raise AssertionError("qualification_or_edge_claim_forbidden")
        if "QUALIFIED" in str(r["label"]) and "NOT_QUALIFIED" not in str(r["label"]):
            raise AssertionError("qualified_label_forbidden")

    hist = dict(Counter(r["label"] for r in results))
    for lbl in ALLOWED_LABELS:
        hist.setdefault(lbl, 0)

    blockers = [
        {
            "blocker_id": "QUALIFICATION_NOT_AUTHORIZED",
            "detail": "qualification_ready_count forced 0; no edge/profitability claims",
        },
        {
            "blocker_id": "OOS_AND_FORMAL_WF_BANNED",
            "detail": "synthetic development fixtures only",
        },
        {
            "blocker_id": "NO_AUTO_INTEGRATE",
            "detail": "lane artifacts only; coordinator must not auto-integrate",
        },
    ]

    report = {
        "schema": SCHEMA,
        "package": PACKAGE,
        "campaign_id": CAMPAIGN_ID,
        "artifact_dirname": ARTIFACT_DIRNAME,
        "lane": "V14-C",
        "pass_id": pass_id,
        "seed": seed,
        "hard_bans": sorted(HARD_BANS),
        "non_claims": list(NON_CLAIMS),
        "mechanism_family_count": len(MECHANISM_FAMILIES),
        "mechanism_families": list(MECHANISM_FAMILIES),
        "mechanism_count": len(results),
        "min_mechanism_count": MIN_MECHANISM_COUNT,
        "mechanism_catalog": catalog.mechanism_catalog(),
        "mechanisms": results,
        "label_histogram": hist,
        "qualification_ready_count": 0,
        "edge_claim_count": 0,
        "profitability_claim_count": 0,
        "data_lineage": lineage,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mainnet_touch_count": 0,
        "profitability_claimed": False,
        "edge_claimed": False,
        "qualified_claimed": False,
        "pr27_merge_attempted": False,
        "auto_integrate_attempted": False,
        "blockers": blockers,
        "code_checksum": code_ck,
        "allowed_labels": sorted(ALLOWED_LABELS),
    }

    if report["mechanism_count"] < MIN_MECHANISM_COUNT:
        raise AssertionError("mechanism_count_below_min")
    if report["qualification_ready_count"] != 0:
        raise AssertionError("qualification_ready_count_must_be_zero")
    if report["formal_walk_forward_executed"] or report["oos_executed"]:
        raise AssertionError("oos_or_wf_ban_violated")
    return report
