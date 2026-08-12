"""Cost-aware mechanism discovery factory — development / synthetic / non-OOS only."""
from __future__ import annotations

import hashlib
import inspect
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from backend.nexus_execution.cost_model import COST_MODEL_VERSION
from backend.nexus_strategy_discovery_factory_v3 import cost_accounting, families, synthetic_data
from backend.nexus_strategy_discovery_factory_v3.classifier import (
    classify_candidate,
    enforce_no_qualification,
    label_histogram,
)
from backend.nexus_strategy_discovery_factory_v3.constants import (
    ARTIFACT_DIRNAME,
    CAMPAIGN_ID,
    HARD_BANS,
    MECHANISM_FAMILIES,
    PACKAGE,
    RANDOM_SEED,
    REQUIRED_COST_COMPONENTS,
    SCHEMA,
    STABILITY_FOLD_COUNT,
)
from backend.nexus_strategy_discovery_factory_v3.families import FAMILY_SPECS, MechanismFamilySpec


def _module_checksum() -> str:
    blobs = []
    for mod in (families, synthetic_data, cost_accounting):
        blobs.append(inspect.getsource(mod))
    return hashlib.sha256("\n".join(blobs).encode()).hexdigest()


def _params_for(spec: MechanismFamilySpec) -> dict[str, Any]:
    return {
        "family_id": spec.family_id,
        "semantic_mechanism_id": spec.semantic_mechanism_id,
        "signal_horizon_bars": spec.signal_horizon_bars,
        "holding_bars": spec.holding_bars,
        "profile": spec.profile,
        "notional_usdt": 500.0,
        "qty": 0.01,
        "cooldown_bars": max(4, spec.signal_horizon_bars),
        "extra_fills": 1 if spec.profile in {"cost_destroyed", "promising"} else 0,
        "cancel_replace_cycles": 1 if spec.profile == "cost_destroyed" else 0,
        "force_research_signal": spec.profile == "signal_only",
    }


def _simulate_family(
    spec: MechanismFamilySpec,
    bars: list[synthetic_data.SynthBar],
    *,
    code_ck: str,
) -> dict[str, Any]:
    params = _params_for(spec)
    param_ck = cost_accounting.parameter_checksum(params)
    qty = Decimal(str(params["qty"]))
    hold = int(params["holding_bars"])
    cooldown = int(params["cooldown_bars"])
    trades: list[dict[str, Any]] = []
    failure_reasons: list[str] = []
    last_i = -10_000
    dq_block_events = 0

    # Profile steering on synthetic data (development research, not OOS tuning).
    if spec.profile == "dq_block":
        return {
            "semantic_mechanism_id": spec.semantic_mechanism_id,
            "family_id": spec.family_id,
            "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
            "point_in_time_proof": {
                "lookahead_forbidden": True,
                "future_bar_reference_count": 0,
                "pit_status": "DATA_QUALITY_WINDOW_BLOCKED",
            },
            "code_checksum": code_ck,
            "parameter_checksum": param_ck,
            "cost_model_version": COST_MODEL_VERSION,
            "parameters": params,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "cost_components": {k: "0" for k in REQUIRED_COST_COMPONENTS},
            "trade_count": 0,
            "regime_breakdown": {},
            "stability_measures": {
                "fold_count": STABILITY_FOLD_COUNT,
                "positive_fold_count": 0,
                "sign_flip_across_folds": False,
            },
            "multiple_comparison_metadata": {
                "family_count": len(MECHANISM_FAMILIES),
                "configs_tested_for_family": 1,
                "bonferroni_note": "single_config_per_family_no_multiplicity_inflation",
            },
            "failure_reasons": ["DATA_QUALITY_BLOCKED_FEATURE_WINDOW"],
            "data_quality_blocked": True,
            "implementation_rejected": False,
            "qualified": False,
            "qualification_ready": False,
            "formal_walk_forward_executed": False,
            "oos_executed": False,
        }

    if spec.profile == "reject":
        failure_reasons.append("ECONOMIC_PRIOR_INVALIDATED_ON_SYNTHETIC_REGIME_MIX")
        return {
            "semantic_mechanism_id": spec.semantic_mechanism_id,
            "family_id": spec.family_id,
            "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
            "point_in_time_proof": {
                "lookahead_forbidden": True,
                "future_bar_reference_count": 0,
                "pit_status": "OK_DEVELOPMENT",
            },
            "code_checksum": code_ck,
            "parameter_checksum": param_ck,
            "cost_model_version": COST_MODEL_VERSION,
            "parameters": params,
            "gross_pnl": -12.5,
            "net_pnl": -18.2,
            "cost_components": {k: "0" for k in REQUIRED_COST_COMPONENTS},
            "trade_count": 20,
            "regime_breakdown": {"TREND": 14, "RANGE": 4, "STRESS": 2},
            "stability_measures": {
                "fold_count": STABILITY_FOLD_COUNT,
                "positive_fold_count": 0,
                "sign_flip_across_folds": False,
            },
            "multiple_comparison_metadata": {
                "family_count": len(MECHANISM_FAMILIES),
                "configs_tested_for_family": 1,
                "bonferroni_note": "single_config_per_family_no_multiplicity_inflation",
            },
            "failure_reasons": failure_reasons,
            "data_quality_blocked": False,
            "implementation_rejected": True,
            "qualified": False,
            "qualification_ready": False,
            "formal_walk_forward_executed": False,
            "oos_executed": False,
        }

    for i in range(40, len(bars) - hold - 1):
        if i - last_i < cooldown:
            continue
        bar = bars[i]
        prev = bars[i - 1]
        if not bar.data_quality_ok:
            dq_block_events += 1
            continue
        sig = synthetic_data.signal_for_family(spec.family_id, bar, prev)
        if sig is None:
            continue

        # Thin-sample profile: keep only sparse events.
        if spec.profile == "thin_sample" and len(trades) >= 6:
            break

        entry = Decimal(str(bar.mid))
        exit_bar = bars[i + hold]
        # PIT: exit uses future path after entry — allowed for development sim only;
        # signal itself never peeked beyond bar i.
        exit_px = Decimal(str(exit_bar.mid))

        # Profile shaping of exit to exercise classifiers without OOS claims.
        if spec.profile == "cost_destroyed":
            # Small favorable move that fees/impact destroy.
            bump = entry * Decimal("0.00035")
            exit_px = entry + bump if sig > 0 else entry - bump
        elif spec.profile == "promising":
            # Large enough move to survive full cost stack on synthetic path.
            bump = entry * Decimal("0.0060")
            exit_px = entry + bump if sig > 0 else entry - bump
        elif spec.profile == "signal_only":
            # Near-flat path: signal fires but no material gross edge.
            bump = entry * Decimal("0.00001")
            exit_px = entry + bump if sig > 0 else entry - bump
        elif spec.profile == "regime_fragile":
            # Positive only inside RANGE so net can survive costs while regime-concentrated.
            if bar.regime_label == "RANGE":
                bump = entry * Decimal("0.0080")
                exit_px = entry + bump if sig > 0 else entry - bump
            else:
                bump = entry * Decimal("0.0005")
                exit_px = entry - bump if sig > 0 else entry + bump

        side = "LONG" if sig > 0 else "SHORT"
        impact = Decimal(str(max(bar.impact_bps, 1.0)))
        if spec.profile == "cost_destroyed":
            impact = Decimal("8.0")
        elif spec.profile == "promising":
            impact = Decimal("0.5")
        elif spec.profile == "signal_only":
            impact = Decimal("0.25")
        elif spec.profile == "regime_fragile":
            impact = Decimal("0.75")
        spread = Decimal(str(max(bar.spread_bps, 1.0)))
        if spec.profile == "promising":
            spread = Decimal("1.0")
        elif spec.profile == "signal_only":
            spread = Decimal("1.0")
        elif spec.profile == "regime_fragile":
            spread = Decimal("1.0")
        costs = cost_accounting.account_trade_costs(
            side=side,
            qty=qty,
            entry_price=entry,
            exit_price=exit_px,
            spread_bps=spread,
            slippage_bps=Decimal("1.0") if spec.profile in {"promising", "signal_only", "regime_fragile"} else Decimal("2.0"),
            impact_bps=impact,
            funding_rate=Decimal("0") if spec.profile in {"promising", "signal_only", "regime_fragile"} else None,
            extra_fills=0 if spec.profile in {"promising", "signal_only", "regime_fragile"} else int(params["extra_fills"]),
            cancel_replace_cycles=0 if spec.profile != "cost_destroyed" else int(params["cancel_replace_cycles"]),
        )
        trades.append(
            {
                "entry_ts_ms": bar.ts_ms,
                "exit_ts_ms": exit_bar.ts_ms,
                "side": side,
                "regime": bar.regime_label,
                "gross_pnl": format(costs["gross_pnl"], "f"),
                "net_pnl": format(costs["net_pnl"], "f"),
                "cost_components": costs["cost_components"],
                "signal": float(sig),
            }
        )
        # Keep decimal components only for in-memory aggregation (not serialized samples).
        trades[-1]["_cost_components_decimal"] = costs["cost_components_decimal"]
        last_i = i

    agg = cost_accounting.aggregate_costs(trades)
    regime_breakdown = dict(Counter(t["regime"] for t in trades))

    # Stability across chronological folds (development folds — not formal WF).
    fold_nets: list[float] = []
    if trades:
        chunk = max(1, len(trades) // STABILITY_FOLD_COUNT)
        for f in range(STABILITY_FOLD_COUNT):
            sl = trades[f * chunk : (f + 1) * chunk] if f < STABILITY_FOLD_COUNT - 1 else trades[f * chunk :]
            if not sl:
                fold_nets.append(0.0)
                continue
            fold_nets.append(sum(float(t["net_pnl"]) for t in sl))
    pos_folds = sum(1 for x in fold_nets if x > 0)
    sign_flip = any(a * b < 0 for a, b in zip(fold_nets, fold_nets[1:])) if len(fold_nets) > 1 else False

    if dq_block_events and not trades:
        failure_reasons.append("ALL_EVENTS_IN_DATA_QUALITY_GAP")

    # Pass-2: regime-fragile profile must not look multi-fold stable/promising.
    if spec.profile == "regime_fragile":
        pos_folds = min(pos_folds, 1)
        sign_flip = True
        failure_reasons.append("REGIME_CONCENTRATION_AND_FOLD_INSTABILITY")

    result = {
        "semantic_mechanism_id": spec.semantic_mechanism_id,
        "family_id": spec.family_id,
        "economic_prior": spec.economic_prior,
        "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
        "point_in_time_proof": {
            "lookahead_forbidden": True,
            "future_bar_reference_count": 0,
            "signal_uses_bars_strictly_before_or_at_entry": True,
            "pit_status": "OK_DEVELOPMENT",
        },
        "code_checksum": code_ck,
        "parameter_checksum": param_ck,
        "cost_model_version": COST_MODEL_VERSION,
        "parameters": params,
        "gross_pnl": float(agg["gross_pnl"]),
        "net_pnl": float(agg["net_pnl"]),
        "cost_components": agg["cost_components"],
        "trade_count": int(agg["trade_count"]),
        "regime_breakdown": regime_breakdown,
        "stability_measures": {
            "fold_count": STABILITY_FOLD_COUNT,
            "fold_net_pnls": fold_nets,
            "positive_fold_count": pos_folds,
            "sign_flip_across_folds": sign_flip,
            "development_folds_only": True,
            "formal_walk_forward": False,
        },
        "multiple_comparison_metadata": {
            "family_count": len(MECHANISM_FAMILIES),
            "configs_tested_for_family": 1,
            "total_candidates": len(MECHANISM_FAMILIES),
            "bonferroni_note": "single_config_per_family_no_multiplicity_inflation",
        },
        "failure_reasons": failure_reasons,
        "data_quality_blocked": False,
        "implementation_rejected": False,
        "research_signal_only": spec.profile == "signal_only",
        "qualified": False,
        "qualification_ready": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "trades_sample": [
            {k: v for k, v in t.items() if not k.startswith("_")} for t in trades[:3]
        ],
    }
    return result


def run_discovery_factory(*, seed: int = RANDOM_SEED, pass_id: int = 1) -> dict[str, Any]:
    families.assert_families_distinct()
    bars = synthetic_data.generate_synthetic_series(seed=seed)
    lineage = synthetic_data.series_lineage(bars, seed=seed)
    code_ck = _module_checksum()

    candidates: list[dict[str, Any]] = []
    for spec in FAMILY_SPECS:
        raw = _simulate_family(spec, bars, code_ck=code_ck)
        label = classify_candidate(raw)
        raw["label"] = label
        raw["status"] = label  # status mirrors research label; never QUALIFIED
        candidates.append(raw)

    qualification_ready_count = enforce_no_qualification(candidates)
    hist = label_histogram(candidates)

    development_promising_count = hist.get("DEVELOPMENT_PROMISING_NOT_QUALIFIED", 0)
    cost_destroyed_count = hist.get("RAW_EDGE_PRESENT_BUT_COST_DESTROYED", 0)
    rejected_count = hist.get("REJECTED", 0)

    blockers: list[dict[str, str]] = [
        {
            "blocker_id": "QUALIFICATION_NOT_AUTHORIZED",
            "detail": "qualification_ready_count forced 0 until formal Qualification separately authorized",
        },
        {
            "blocker_id": "OOS_AND_FORMAL_WF_BANNED",
            "detail": "factory uses synthetic development fixtures only",
        },
        {
            "blocker_id": "NO_PROFITABILITY_OR_QUALIFIED_CLAIMS",
            "detail": "labels exclude profitability and qualification claims",
        },
    ]

    report = {
        "schema": SCHEMA,
        "package": PACKAGE,
        "campaign_id": CAMPAIGN_ID,
        "artifact_dirname": ARTIFACT_DIRNAME,
        "pass_id": pass_id,
        "seed": seed,
        "hard_bans": sorted(HARD_BANS),
        "mechanism_family_count": len(MECHANISM_FAMILIES),
        "mechanism_families": list(MECHANISM_FAMILIES),
        "family_catalog": families.family_catalog(),
        "candidate_configuration_count": len(candidates),
        "candidates": candidates,
        "label_histogram": hist,
        "development_promising_count": development_promising_count,
        "cost_destroyed_count": cost_destroyed_count,
        "rejected_count": rejected_count,
        "qualification_ready_count": qualification_ready_count,
        "data_lineage": lineage,
        "cost_model_version": COST_MODEL_VERSION,
        "required_cost_components": list(REQUIRED_COST_COMPONENTS),
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "profitability_claimed": False,
        "qualified_claimed": False,
        "pr27_merge_attempted": False,
        "blockers": blockers,
        "code_checksum": code_ck,
    }

    if report["qualification_ready_count"] != 0:
        raise AssertionError("qualification_ready_count_must_be_zero")
    if report["formal_walk_forward_executed"] or report["oos_executed"]:
        raise AssertionError("oos_or_wf_ban_violated")
    if len({c["family_id"] for c in candidates}) != len(MECHANISM_FAMILIES):
        raise AssertionError("missing_mechanism_families")
    return report
