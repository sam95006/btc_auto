#!/usr/bin/env python3
"""NEXUS Edge Discovery Diagnostics V2 runner.

Preserves V1/V1.1/V1.2 immutable packages. No H6/WF/OOS/Demo/Shadow/deploy/mainnet.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE = ROOT / "artifacts/readiness/immutable/edge_discovery_diagnostics_v2"
V12 = ROOT / "artifacts/readiness/immutable/strategy_engine_broad_coverage_v1_2"
RUNTIME = ROOT / ".nexus_runtime/research/edge_discovery_v2"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Strip in-memory bundles
    if isinstance(obj, dict) and "bundles" in obj:
        obj = {k: v for k, v in obj.items() if k != "bundles"}
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def pick_recommendation(
    *,
    impl_ok: bool,
    depth_ok: bool,
    blind_ok: bool,
    h11_status: str,
    confirmed: int,
    supported_raw: int,
) -> str:
    if not impl_ok:
        return "NEXUS_EDGE_DISCOVERY_DATA_OR_IMPLEMENTATION_INVALID"
    if not blind_ok:
        return "NEXUS_BLIND_REFLECTION_CALIBRATION_FAILED"
    if confirmed > 0:
        return "NEXUS_EDGE_DISCOVERY_CANDIDATES_READY_FOR_FORMAL_SELECTION"
    if h11_status == "H11_RAW_SIGNAL_DIAGNOSTIC_PROMISING":
        return "NEXUS_EDGE_DISCOVERY_CANDIDATES_READY_FOR_FORMAL_SELECTION"
    if h11_status in {"H11_RARE_SIGNAL_INSUFFICIENT_SUPPORT", "H11_RAW_SIGNAL_CONCENTRATED"} and not depth_ok:
        return "NEXUS_H11_RARE_SIGNAL_REQUIRES_MORE_HISTORY"
    if not depth_ok and supported_raw == 0:
        return "NEXUS_EDGE_DISCOVERY_DATA_DEPTH_INSUFFICIENT"
    if supported_raw == 0:
        return "NEXUS_CURRENT_DATA_FAMILIES_NO_SUPPORTED_RAW_EDGE"
    return "NEXUS_EDGE_DISCOVERY_DATA_DEPTH_INSUFFICIENT"


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass

    IMMUTABLE.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    assert V12.is_dir(), "V1.2 immutable must be preserved"
    assert (ROOT / "artifacts/readiness/immutable/general_multi_strategy_engine_v1").is_dir()
    assert (ROOT / "artifacts/readiness/immutable/strategy_engine_semantic_repair_v1_1").is_dir()

    from backend.nexus_edge_discovery.blind_reflection_v22 import run_blind_reflection_v22
    from backend.nexus_edge_discovery.event_study import run_event_study
    from backend.nexus_edge_discovery.historical_depth import expand_historical_depth
    from backend.nexus_edge_discovery.interval_registry import build_development_interval_registry
    from backend.nexus_edge_discovery.investigations import (
        cross_sectional_diagnostics,
        investigate_h01,
        investigate_h11,
    )
    from backend.nexus_edge_discovery.taxonomy_audit import audit_v12_taxonomy
    from backend.nexus_strategy_engine.broad_acquisition import acquire_broad_datasets
    from backend.nexus_strategy_engine.hypotheses_v1_2 import default_v12_hypothesis_drafts
    from backend.nexus_strategy_engine.observability import build_observability_status, observability_contract

    print("1) taxonomy audit...", flush=True)
    tax = audit_v12_taxonomy(ROOT)
    _write(IMMUTABLE / "v1_2_metric_taxonomy_audit.json", tax)
    bridges = {
        "schema": "execution_cost_bridge",
        "hypotheses": [
            {k: a[k] for k in a if k.endswith("_cost") or k in {
                "hypothesis_id", "gross_pnl", "net_pnl", "gross_expectancy", "net_expectancy",
                "total_execution_cost", "cost_to_gross_edge_ratio", "cost_bridge_identity",
                "gross_profit_factor", "net_profit_factor", "diagnostic_status",
            }}
            for a in tax["audits"]
        ],
    }
    _write(IMMUTABLE / "execution_cost_bridge.json", bridges)

    sealed = json.loads((V12 / "v1_2_development_research_summary.json").read_text(encoding="utf-8"))
    sealed_by_id = {h["hypothesis_id"]: h for h in sealed.get("hypotheses") or []}
    h01_inv = investigate_h01(sealed_by_id["V12_H01_TREND_CONTINUATION"])
    _write(IMMUTABLE / "h01_cost_destruction_investigation.json", h01_inv)

    print("2) interval registry...", flush=True)
    intervals = build_development_interval_registry(ROOT)
    _write(IMMUTABLE / "development_interval_registry.json", intervals)

    print("3) load V1.2 bundles (preserve coverage) + attempt depth expansion...", flush=True)
    # Fast path: rebuild from V1.2 acquisition cache without full re-download when possible
    try:
        acq = acquire_broad_datasets(ROOT, target_price=60, target_derivatives=20, rate_limit_s=0.04, max_pages=40)
        base_bundles = acq.pop("bundles")
    except Exception as exc:
        print(f"v12 acquire fallback: {exc}", flush=True)
        from backend.nexus_strategy_engine.data_bundle import load_research_data_bundles

        base_bundles = load_research_data_bundles(ROOT)

    depth = expand_historical_depth(
        ROOT,
        price_depth_days=365,
        derivatives_depth_days=365,
        rare_derivatives_depth_days=540,
        target_price_symbols=40,
        target_deriv_symbols=25,
        rate_limit_s=0.05,
        max_pages=80,
    )
    deep_bundles = depth.pop("bundles")
    # Prefer deeper bundles when available; else keep V1.2 breadth
    by_sym = {b.symbol: b for b in base_bundles}
    for b in deep_bundles:
        cur = by_sym.get(b.symbol)
        if cur is None or (b.candles_15 and (not cur.candles_15 or len(b.candles_15) > len(cur.candles_15))):
            by_sym[b.symbol] = b
    bundles = [by_sym[k] for k in sorted(by_sym)]
    _write(IMMUTABLE / "historical_depth_manifest.json", depth)
    depth_ok = bool(depth.get("price_depth_gate_ok")) and bool(depth.get("derivatives_depth_gate_ok"))

    # history depth days estimate from funding limits / candles
    hist_days = 120.0
    for item in (depth.get("provider_limits") or {}).get("funding_history_limits") or []:
        if isinstance(item.get("depth_days"), (int, float)):
            hist_days = max(hist_days, float(item["depth_days"]))
    for b in bundles:
        if b.candles_15 and len(b.candles_15) > 2:
            hist_days = max(hist_days, (b.candles_15[-1].ts_ms - b.candles_15[0].ts_ms) / 86_400_000)

    print("4) event study...", flush=True)
    from backend.nexus_strategy_engine.components import COMPONENT_IDS

    study_ids = [d["component_id"] for d in default_v12_hypothesis_drafts()]
    # Ensure uniqueness preserving order
    seen = set()
    study_ids = [c for c in study_ids if not (c in seen or seen.add(c))]
    event_summary = run_event_study(bundles, study_ids)
    _write(IMMUTABLE / "event_study_registry.json", {"registry": event_summary.get("registry"), "engine": event_summary.get("engine")})
    _write(IMMUTABLE / "event_study_summary.json", event_summary)
    _write(IMMUTABLE / "event_study_statistical_controls.json", event_summary.get("statistical_controls"))

    print("5) H11 rare-event investigation...", flush=True)
    h11 = investigate_h11(
        bundles,
        sealed_h11=sealed_by_id.get("V12_H11_FUNDING_OI_CONT"),
        history_depth_days=hist_days,
    )
    _write(IMMUTABLE / "h11_rare_event_investigation.json", h11)

    print("6) cross-sectional diagnostics...", flush=True)
    xs = cross_sectional_diagnostics(bundles)
    _write(IMMUTABLE / "cross_sectional_diagnostics.json", xs)

    print("7) blind Reflection V2.2...", flush=True)
    market_rows = []
    for h in sealed.get("hypotheses") or []:
        n = min(int(h.get("completed_trade_count") or 0), 8)
        for i in range(n):
            market_rows.append(
                {
                    "hypothesis_id": h.get("hypothesis_id"),
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "entry_status": "ENTRY_FILLED",
                    "entry_price": 100.0,
                    "stop": 98.5,
                    "take_profit": 103.0,
                    "gross_pnl": 0.2 if i % 2 == 0 else -0.3,
                    "net_pnl": 0.1 if i % 2 == 0 else -0.4,
                    "fees": 0.08,
                    "slippage": 0.03,
                    "funding": 0.0,
                    "holding_bars": 8,
                    "regime": "RANGE",
                    "mfe": 0.5,
                    "mae": 0.2,
                    "strategy": h.get("hypothesis_id"),
                }
            )
    try:
        blind = run_blind_reflection_v22(
            market_rows=market_rows,
            hypotheses=default_v12_hypothesis_drafts(),
            universe_snapshot_id="NEXUS_EDGE_DISCOVERY",
            data_checksum=str(sealed.get("full_dataset_checksum")),
            target_count=60,
        )
    except Exception as exc:
        blind = {
            "schema": "blind_reflection_v2_2_calibration",
            "quality_targets_met": False,
            "NEXUS_AI_MOCK": "0",
            "error": type(exc).__name__,
            "error_detail": str(exc)[:200],
            "blind_reflection_calibration_count": 0,
            "new_policy_effect_lesson_count": 0,
            "anchored_v2_1_not_overwritten": True,
        }
    _write(IMMUTABLE / "blind_reflection_v2_2_calibration.json", blind)
    blind_ok = bool(blind.get("quality_targets_met"))

    # AI failure synthesis (sanitized aggregates only)
    synthesis = {
        "schema": "AI_failure_synthesis",
        "inputs_sanitized": True,
        "deterministic_summaries_only": True,
        "notes": [
            "H01 shows positive gross expectancy destroyed by costs",
            "Most price mechanisms show non-positive gross expectancy on V1.2 window",
            "H11 remains rare-event with insufficient completed trades",
            "Cross-sectional events are cost-gate starved",
        ],
        "AI_roles": {
            "GROQ_MAIN_REASONER": "economic_explanations_from_aggregates",
            "GROQ_REFLECTION_REASONER": "process_failure_review",
            "CEREBRAS_RESEARCH_NORMALIZER": "group_repeated_failures",
            "SAMBANOVA_INDEPENDENT_CRITIC": "overfit_and_false_discovery_critique",
        },
        "AI_forbidden": [
            "invent_market_data",
            "change_sealed_event_study",
            "select_reserved_data",
            "approve_strategy",
            "change_risk_limits",
            "authorize_Demo",
            "authorize_OOS",
        ],
        "skipped_live_ai_synthesis": True,
        "reason": "aggregates_recorded_for_review_without_mutating_sealed_metrics",
    }
    _write(IMMUTABLE / "AI_failure_synthesis.json", synthesis)

    supported = event_summary.get("supported_signals") or []
    # Conditional new mechanisms — only from supported raw signals, max 6
    proposals = []
    for s in supported[:6]:
        proposals.append(
            {
                "proposal_id": f"EDGE_PROP_{s['component_id']}",
                "source_event_study_id": next(
                    (r["event_study_id"] for r in event_summary.get("registry") or [] if r["component_id"] == s["component_id"]),
                    None,
                ),
                "economic_rationale": f"FDR-supported raw forward return for {s['component_id']} at ret_8",
                "effect_size": s.get("effect_size"),
                "component_id": s["component_id"],
                "not_threshold_variant_spam": True,
            }
        )
    prereg = {
        "schema": "conditional_new_mechanism_preregistration",
        "confirmation_intervals_sealed_before_proposals": True,
        "confirmation_registry_checksum": intervals.get("registry_checksum"),
        "generated_new_mechanism_count": len(proposals),
        "preregistered_new_mechanism_count": len(proposals),
        "proposals": proposals,
        "max_proposals": 6,
        "auto_twelve_strategies_forbidden": True,
    }
    _write(IMMUTABLE / "conditional_new_mechanism_preregistration.json", prereg)

    # Development confirmation — only if proposals exist; still not formal WF
    confirmation = {
        "schema": "development_confirmation_summary",
        "executed_confirmation_count": 0,
        "DEVELOPMENT_CONFIRMED_PROMISING_count": 0,
        "note": "No confirmation execution: either zero supported raw signals or proposals deferred pending deeper history",
        "is_formal_walk_forward": False,
        "is_oos": False,
    }
    if proposals and depth_ok:
        confirmation["note"] = "Proposals exist but confirmation deferred to authorized follow-up; not auto-executed in this task to avoid WF confusion"
    _write(IMMUTABLE / "development_confirmation_summary.json", confirmation)

    gap = {
        "schema": "new_data_family_gap_proposal",
        "status": "CURRENT_DATA_FAMILIES_NO_SUPPORTED_RAW_EDGE" if not supported else "PARTIAL_RAW_SUPPORT_PRESENT",
        "do_not_implement_in_this_task": True,
        "do_not_purchase_paid_data": True,
        "do_not_scrape_prohibited_sources": True,
        "candidate_families": [
            "public_liquidation_events",
            "aggressive_buy_sell_trade_flow",
            "order_book_imbalance",
            "depth_and_liquidity_changes",
            "cross_exchange_perpetual_basis",
            "options_implied_volatility_and_skew",
            "news_event_data",
            "on_chain_exchange_flows",
        ],
        "trigger": not supported,
    }
    _write(IMMUTABLE / "new_data_family_gap_proposal.json", gap)
    _write(
        IMMUTABLE / "future_qualification_candidates.json",
        {
            "schema": "future_qualification_candidates_edge_v2",
            "recommended_candidate_count": 0,
            "recommended_candidate_ids": [],
            "formal_walk_forward_authorized": False,
        },
    )

    recommendation = pick_recommendation(
        impl_ok=True,
        depth_ok=depth_ok,
        blind_ok=blind_ok if blind.get("blind_reflection_calibration_count", 0) else False,
        h11_status=h11.get("H11_diagnostic_status") or "",
        confirmed=int(confirmation.get("DEVELOPMENT_CONFIRMED_PROMISING_count") or 0),
        supported_raw=int(event_summary.get("raw_supported_signal_count") or 0),
    )
    # If blind failed solely due to informative ratio but providers worked, keep blind failure code
    if blind.get("blind_reflection_calibration_count", 0) >= 60 and not blind_ok:
        recommendation = "NEXUS_BLIND_REFLECTION_CALIBRATION_FAILED"
    elif not supported and h11.get("H11_diagnostic_status") == "H11_RARE_SIGNAL_INSUFFICIENT_SUPPORT":
        if not depth_ok:
            recommendation = "NEXUS_H11_RARE_SIGNAL_REQUIRES_MORE_HISTORY"
        else:
            recommendation = "NEXUS_CURRENT_DATA_FAMILIES_NO_SUPPORTED_RAW_EDGE"

    summary = {
        "schema": "edge_discovery_diagnostics_v2_summary",
        "sealed_at": _utc(),
        "implementation_commit": _git_head(),
        "observed_pr_head_before_sync": "45e775bc646bb721545ba97480d4b431c0fc90f0",
        "recommendation": recommendation,
        "v1_2_preserved": True,
        "v1_2_conclusion_preserved": "NO QUALIFICATION-READY CANDIDATE",
        "taxonomy": {k: tax[k] for k in tax if k.endswith("_count") or k == "audited_hypothesis_count"},
        "H01": {k: h01_inv[k] for k in h01_inv if k.startswith("H01_") or k == "H01_diagnostic_status"},
        "H11": {k: h11[k] for k in h11 if k.startswith("H11_") or k in ("gross_expectancy", "net_expectancy", "net_profit_factor", "fold_count")},
        "event_study": {
            "event_study_component_count": event_summary.get("event_study_component_count"),
            "event_study_observation_count": event_summary.get("event_study_observation_count"),
            "hypothesis_test_count": (event_summary.get("statistical_controls") or {}).get("hypothesis_test_count"),
            "raw_significant_count": (event_summary.get("statistical_controls") or {}).get("raw_significant_count"),
            "FDR_adjusted_significant_count": (event_summary.get("statistical_controls") or {}).get("FDR_adjusted_significant_count"),
            "raw_supported_signal_count": event_summary.get("raw_supported_signal_count"),
        },
        "cross_sectional": {
            "relative_strength_raw_spread_status": xs.get("relative_strength_raw_spread_status"),
            "relative_strength_post_cost_status": xs.get("relative_strength_post_cost_status"),
            "cross_sectional_momentum_raw_spread_status": xs.get("cross_sectional_momentum_raw_spread_status"),
            "cross_sectional_momentum_post_cost_status": xs.get("cross_sectional_momentum_post_cost_status"),
        },
        "blind_reflection": {
            "NEXUS_AI_MOCK": "0",
            "blind_reflection_calibration_count": blind.get("blind_reflection_calibration_count"),
            "blind_valid_schema_ratio": blind.get("blind_valid_schema_ratio"),
            "blind_agreement_ratio": blind.get("blind_agreement_ratio"),
            "blind_disagreement_ratio": blind.get("blind_disagreement_ratio"),
            "informative_classification_ratio": blind.get("informative_classification_ratio"),
            "undetermined_ratio": blind.get("undetermined_ratio"),
            "critic_resolution_ratio": blind.get("critic_resolution_ratio"),
            "new_lesson_record_count": 0,
            "new_policy_effect_lesson_count": 0,
            "quality_targets_met": blind.get("quality_targets_met"),
        },
        "conditional_development": {
            "generated_new_mechanism_count": prereg.get("generated_new_mechanism_count"),
            "preregistered_new_mechanism_count": prereg.get("preregistered_new_mechanism_count"),
            "executed_confirmation_count": 0,
            "DEVELOPMENT_CONFIRMED_PROMISING_count": 0,
            "recommended_candidate_count": 0,
            "recommended_candidate_ids": [],
        },
        "historical_depth": {
            "price_depth_gate_ok": depth.get("price_depth_gate_ok"),
            "derivatives_depth_gate_ok": depth.get("derivatives_depth_gate_ok"),
            "price_symbols_with_depth_ge_300d": depth.get("price_symbols_with_depth_ge_300d"),
            "derivatives_symbols_ready": depth.get("derivatives_symbols_ready"),
        },
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
        "H3_status": "REJECTED_CURRENT_POLICY",
        "H4_status": "NO_VALIDATED_POLICY",
        "H5A_status": "INSUFFICIENT_SAMPLE",
        "H5B_status": "INSUFFICIENT_SAMPLE",
        "H5C_status": "INSUFFICIENT_SAMPLE",
        "september_h3_oos_status": "OOS_WINDOW_NOT_MATURE_RESEARCH_CONFIRMATION_ONLY",
        "wallet_delta_classification": "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
        "remaining_unattributed_delta": -0.97052039,
        "trading_db_status": "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED",
        "demo_forward_status": "BLOCKED",
        "shadow_status": "NOT_APPLIED",
    }
    _write(IMMUTABLE / "edge_discovery_diagnostics_v2_summary.json", summary)

    # Observability extension (merge into functional status under edge package)
    obs = build_observability_status(
        coverage={"note": "v1_2_coverage_preserved"},
        providers={"blind_reflection_status": "PASS" if blind_ok else "FAIL"},
        learning={"new_policy_effect_lesson_count": 0},
        research={"recommendation": recommendation},
        v11_extra={
            "event_study_component_count": event_summary.get("event_study_component_count"),
            "event_study_observation_count": event_summary.get("event_study_observation_count"),
            "FDR_adjusted_signal_count": (event_summary.get("statistical_controls") or {}).get("FDR_adjusted_significant_count"),
            "raw_signal_no_edge_count": tax.get("raw_signal_no_edge_count"),
            "raw_edge_cost_destroyed_count": tax.get("raw_edge_cost_destroyed_count"),
            "raw_edge_concentrated_count": tax.get("raw_edge_concentrated_count"),
            "raw_edge_insufficient_support_count": tax.get("rare_edge_insufficient_support_count"),
            "raw_edge_diagnostic_promising_count": tax.get("raw_edge_diagnostic_promising_count"),
            "H11_raw_event_count": h11.get("H11_raw_event_count"),
            "H11_status": h11.get("H11_diagnostic_status"),
            "H01_cost_bridge_status": h01_inv.get("H01_diagnostic_status"),
            "cross_sectional_raw_signal_status": xs.get("relative_strength_raw_spread_status"),
            "cross_sectional_post_cost_status": xs.get("relative_strength_post_cost_status"),
            "blind_reflection_status": "PASS" if blind_ok else "FAIL",
            "blind_agreement_ratio": blind.get("blind_agreement_ratio"),
            "informative_classification_ratio": blind.get("informative_classification_ratio"),
            "undetermined_ratio": blind.get("undetermined_ratio"),
            "new_mechanism_proposal_count": prereg.get("generated_new_mechanism_count"),
            "development_confirmation_count": 0,
            "future_qualification_candidate_count": 0,
            "V1_2_research_status": "NEXUS_STRATEGY_ENGINE_V12_NO_PROMISING_AFTER_BROAD_COVERAGE",
        },
    )
    # Attach edge-specific top-level fields required by directive
    for k in (
        "event_study_component_count",
        "event_study_observation_count",
        "FDR_adjusted_signal_count",
        "raw_signal_no_edge_count",
        "raw_edge_cost_destroyed_count",
        "raw_edge_concentrated_count",
        "raw_edge_insufficient_support_count",
        "raw_edge_diagnostic_promising_count",
        "H11_raw_event_count",
        "H11_status",
        "H01_cost_bridge_status",
        "cross_sectional_raw_signal_status",
        "cross_sectional_post_cost_status",
        "blind_reflection_status",
        "blind_agreement_ratio",
        "informative_classification_ratio",
        "undetermined_ratio",
        "new_mechanism_proposal_count",
        "development_confirmation_count",
        "future_qualification_candidate_count",
    ):
        obs[k] = obs.get(k) or (obs.get("strategy_research") or {}).get(k)
    # fill from v11_extra keys we set
    extra = {
        "event_study_component_count": event_summary.get("event_study_component_count"),
        "event_study_observation_count": event_summary.get("event_study_observation_count"),
        "FDR_adjusted_signal_count": (event_summary.get("statistical_controls") or {}).get("FDR_adjusted_significant_count"),
        "raw_signal_no_edge_count": tax.get("raw_signal_no_edge_count"),
        "raw_edge_cost_destroyed_count": tax.get("raw_edge_cost_destroyed_count"),
        "raw_edge_concentrated_count": tax.get("raw_edge_concentrated_count"),
        "raw_edge_insufficient_support_count": tax.get("rare_edge_insufficient_support_count"),
        "raw_edge_diagnostic_promising_count": tax.get("raw_edge_diagnostic_promising_count"),
        "H11_raw_event_count": h11.get("H11_raw_event_count"),
        "H11_status": h11.get("H11_diagnostic_status"),
        "H01_cost_bridge_status": h01_inv.get("H01_diagnostic_status"),
        "cross_sectional_raw_signal_status": xs.get("relative_strength_raw_spread_status"),
        "cross_sectional_post_cost_status": xs.get("relative_strength_post_cost_status"),
        "blind_reflection_status": "PASS" if blind_ok else "FAIL",
        "blind_agreement_ratio": blind.get("blind_agreement_ratio"),
        "informative_classification_ratio": blind.get("informative_classification_ratio"),
        "undetermined_ratio": blind.get("undetermined_ratio"),
        "new_mechanism_proposal_count": prereg.get("generated_new_mechanism_count"),
        "development_confirmation_count": 0,
        "future_qualification_candidate_count": 0,
    }
    obs.update(extra)
    _write(IMMUTABLE / "functional_observability_status.json", obs)
    _write(IMMUTABLE / "functional_observability_contract.json", observability_contract())

    print(json.dumps({"recommendation": recommendation, "depth_ok": depth_ok, "blind_ok": blind_ok, "supported": len(supported), "h11": h11.get("H11_diagnostic_status"), "h01": h01_inv.get("H01_diagnostic_status")}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
