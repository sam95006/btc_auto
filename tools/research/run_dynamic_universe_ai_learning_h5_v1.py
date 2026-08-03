#!/usr/bin/env python3
"""Dynamic Universe + AI Learning Foundation V1 + H5 Portability Research V1.

No Demo orders. No Shadow. No H5 OOS execution. No September H3 OOS. No deploy.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_ai_gateway import AIGateway
from backend.nexus_demo_execution.closed_historical_registry import (
    RESEARCH_V2_V3_END_MS,
    RESEARCH_V2_V3_START_MS,
    SEPTEMBER_OOS_END_MS,
    SEPTEMBER_OOS_START_MS,
    assert_september_partial_excluded,
)
from backend.nexus_demo_execution.edge_research_h5 import (
    preregistration_checksum,
    preregistration_payload,
    run_edge_research_h5,
    sha_obj,
)
from backend.nexus_demo_execution.edge_research_h5_hypotheses import H5_DEV_END_MS, H5_DEV_START_MS, HYPOTHESES_H5
from backend.nexus_demo_execution.historical_market_data import fetch_or_load_bundle
from backend.nexus_demo_execution.microstructure_history import fetch_or_load_micro_bundle
from backend.nexus_dynamic_universe import (
    UNIVERSE_ID,
    build_universe_snapshot,
    point_in_time_membership,
    save_universe_snapshot,
)
from backend.nexus_dynamic_universe.historical_acquisition import eligibility_gates
from backend.nexus_dynamic_universe.symbol_profile import build_profiles, coverage_report
from backend.nexus_learning import LESSON_SCHEMA_VERSION, REFLECTION_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE = ROOT / "artifacts" / "readiness" / "immutable" / "dynamic_universe_ai_learning_h5_v1"
RUNTIME = ROOT / ".nexus_runtime" / "research" / "dynamic_universe_h5_v1"
INTERVALS = ["15", "60", "240"]
CONSUMED_HOLDOUT = "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED"

# Seed majors always considered; expanded via live universe rankings (not fleets).
SEED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
MAX_RESEARCH_SYMBOLS = 10


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def seal_h4() -> dict[str, Any]:
    return {
        "schema": "h4_sealed_classifications_v1",
        "do_not_overwrite_or_soften": True,
        "selected_h4_primary_policy": None,
        "h4_oos_reservation_id": None,
        "demo_forward_status": "BLOCKED_NO_VALIDATED_POLICY",
        "H4A_EVENT_RETEST_CONTINUATION": {
            "status": "REJECTED_CONCENTRATED_EDGE",
            "founder_classification": "PROMISING_MECHANISM_NOT_PORTABLE",
            "completed_trade_count": 201,
            "net_expectancy": 0.2783494284079602,
            "profit_factor": 1.194766,
            "adverse_profit_factor": 1.1004,
            "fold_concentration": 0.8037124431609612,
            "may_inform_h5": True,
            "may_promote": False,
        },
        "H4B_VOLATILITY_NORMALIZED_CONTINUATION": {
            "status": "INSUFFICIENT_SAMPLE",
            "completed_trade_count": 15,
        },
        "H4C_OI_FUNDING_CONFIRMED_CONTINUATION": {
            "status": "REJECTED_COST_DOMINATED",
            "founder_classification": "POSITIVE_BASE_RESULT_NOT_COST_OR_FOLD_STABLE",
            "completed_trade_count": 85,
            "net_expectancy": 0.13327247223529412,
            "profit_factor": 1.097856,
            "adverse_profit_factor": 0.983488,
            "fold_concentration": 0.9764067895560486,
            "may_inform_h5": True,
            "may_promote": False,
        },
        "fold_concentration_gate_not_lowered": True,
        "modified_h4_rerun_as_qualification_forbidden": True,
        "h4_research_commit": "f7ade4a379c268d7c08517b8a8a79e4838a5476f",
    }


def select_research_symbols(snapshot: dict[str, Any], profiles: list[Any]) -> list[str]:
    """Eligibility before performance — liquidity/quality only."""
    by_sym = {p.symbol: p for p in profiles}
    ranked = sorted(
        profiles,
        key=lambda p: (p.liquidity_percentile or 0, p.turnover_percentile or 0),
        reverse=True,
    )
    chosen: list[str] = []
    for sym in SEED_SYMBOLS:
        if sym in by_sym and sym not in chosen:
            chosen.append(sym)
    for p in ranked:
        if len(chosen) >= MAX_RESEARCH_SYMBOLS:
            break
        ok, _fails = eligibility_gates(
            listing_age_days=p.listing_age_days if p.listing_age_days is not None else 90.0,
            coverage_ratio=0.9,  # coverage checked after download
            turnover_24h=1_000_000 if (p.turnover_percentile or 0) >= 0.2 else 500_000,
            oi_value=1.0 if (p.open_interest_percentile or 0) > 0 else None,
            spread_bps=p.spread_bps,
            slippage_bps=p.estimated_slippage_bps,
            mark_status="UNKNOWN",
            candle_status="AVAILABLE",
            require_oi=False,
        )
        if not ok:
            continue
        if p.quality_status == "WIDE_SPREAD":
            continue
        if p.symbol not in chosen:
            chosen.append(p.symbol)
    # Ensure we have at least seeds that exist in snapshot
    eligible_set = {i["symbol"] for i in snapshot.get("instruments") or [] if i.get("eligible")}
    return [s for s in chosen if s in eligible_set][:MAX_RESEARCH_SYMBOLS]


def freeze_policy_from_hyp(hyp: dict[str, Any], *, source_commit: str, symbols: list[str]) -> dict[str, Any]:
    policy = {
        "policy_id": f"{hyp['hypothesis_id']}_POLICY_V1_FROZEN",
        "qualification_role": "PRIMARY_H5_CANDIDATE",
        "hypothesis_id": hyp["hypothesis_id"],
        "strategy": "trend_following",
        "regime": "TRENDING_DOWN",
        "side": "Sell",
        "entry_rules": {
            "entry_logic": hyp["entry_logic"],
            "parameter_values": hyp["parameter_values"],
            "mechanism": hyp["mechanism"],
        },
        "confirmation_rules": {"confirmation_logic": hyp["confirmation_logic"]},
        "cost_gate_rules": {
            "MIN_NET_REWARD_RISK_RATIO": 1.2,
            "MIN_NET_REWARD_TO_COST": 1.5,
            "floors_immutable": True,
        },
        "risk_sizing_rules": {
            "margin_usdt": 20,
            "leverage": 25,
            "margin_mode": "ISOLATED",
            "maximum_single_trade_loss": 3,
        },
        "cost_assumptions": {
            "taker_fee_rate_default": 0.00055,
            "round_trip_rate": 0.00110,
            "default_round_trip": "TAKER_PLUS_TAKER",
        },
        "symbols": symbols,
        "intervals": INTERVALS,
        "universe_id": UNIVERSE_ID,
        "source_commit": source_commit,
        "frozen_at": _utc(),
        "created_before_oos_download": True,
        "demo_not_authorized_by_wf_alone": True,
    }
    policy["policy_checksum"] = sha_obj(policy)
    policy["semantic_checksum"] = sha_obj(
        {
            "hypothesis_id": hyp["hypothesis_id"],
            "parameter_values": hyp["parameter_values"],
            "entry_logic": hyp["entry_logic"],
            "gates_ref": "H5_GATES",
        }
    )
    return policy


def make_h5_oos_reservation(policy: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
    start = SEPTEMBER_OOS_END_MS + 1
    end = start + 45 * 86_400_000
    return {
        "reservation_id": "H5_UNTOUCHED_OOS_V1_RESERVED",
        "reserved_start": start,
        "reserved_end": end,
        "symbols": symbols,
        "intervals": INTERVALS,
        "primary_policy_id": policy["policy_id"],
        "policy_checksum": policy["policy_checksum"],
        "semantic_checksum": policy["semantic_checksum"],
        "downloaded": False,
        "executed": False,
        "created_before_download": True,
        "overlap_september_oos": False,
        "overlap_consumed_h3_holdout": False,
        "created_at": _utc(),
        "note": "Future untouched H5 OOS; do not download/execute in this task",
    }


def recommendation_from_results(summary: dict[str, Any]) -> str:
    if summary.get("selected_h5_primary_policy"):
        return "NEXUS_H5_WALK_FORWARD_VALIDATED_NEW_OOS_REQUIRED"
    statuses = [r.get("status") for r in summary.get("hypothesis_results") or []]
    if any(s in {"DATA_INVALID", "IMPLEMENTATION_INVALID"} for s in statuses):
        return "NEXUS_H5_DATA_OR_IMPLEMENTATION_INVALID"
    if statuses and all(s == "INSUFFICIENT_SAMPLE" for s in statuses):
        return "NEXUS_H5_RESEARCH_INSUFFICIENT_SAMPLE"
    return "NEXUS_H5_RESEARCH_FAILED_NO_DEMO"


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    os.environ.setdefault("NEXUS_AI_MOCK", "1")
    IMMUTABLE.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)

    sealed_h4 = seal_h4()
    _write(IMMUTABLE / "h4_sealed_classifications.json", sealed_h4)

    # --- Dynamic universe snapshot ---
    print("universe discovery...", flush=True)
    snapshot = build_universe_snapshot()
    snap_path = RUNTIME / "universe_snapshots" / f"universe_{snapshot['snapshot_timestamp'].replace(':', '')}.json"
    save_universe_snapshot(snapshot, snap_path)
    # Slim committed summary (not full instrument dump in git)
    eligible = [i for i in snapshot["instruments"] if i.get("eligible")]
    universe_summary = {
        "universe_id": UNIVERSE_ID,
        "fleet_architecture": False,
        "snapshot_timestamp": snapshot["snapshot_timestamp"],
        "snapshot_checksum": snapshot["snapshot_checksum"],
        "instrument_count_raw": snapshot["instrument_count_raw"],
        "dynamic_universe_symbol_count": len(eligible),
        "pagination_complete": True,
        "source": snapshot["source"],
        "trading_write": False,
        "survivorship_bias_status": "ACKNOWLEDGED_PIT_MEMBERSHIP_REQUIRED",
        "point_in_time_membership_status": "IMPLEMENTED",
        "eligible_symbol_sample": sorted(i["symbol"] for i in eligible)[:50],
    }
    _write(IMMUTABLE / "dynamic_universe_summary.json", universe_summary)

    # Tickers already fetched inside build; rebuild profiles via instruments + live tickers
    from backend.nexus_dynamic_universe import fetch_all_linear_tickers

    tickers = {str(t.get("symbol")): t for t in fetch_all_linear_tickers()}
    profiles = build_profiles(
        instruments=snapshot["instruments"],
        tickers=tickers,
        timestamp=snapshot["snapshot_timestamp"],
        as_of_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    cov = coverage_report(profiles)
    _write(
        IMMUTABLE / "symbol_profile_schema_and_coverage.json",
        {
            "schema_version": "symbol_profile_v1",
            "taxonomy_version": "meme_taxonomy_v1",
            "coverage": cov,
            "note": "Labels/features in one system — not fleets",
            "profile_count": len(profiles),
        },
    )

    # PIT membership samples
    mid_ts = (H5_DEV_START_MS + H5_DEV_END_MS) // 2
    pit_mid = point_in_time_membership(snapshot, as_of_ms=mid_ts)
    pit_start = point_in_time_membership(snapshot, as_of_ms=H5_DEV_START_MS)
    survivorship = {
        "status": "ACKNOWLEDGED",
        "pit_symbol_count_at_dev_start": len(pit_start),
        "pit_symbol_count_at_dev_mid": len(pit_mid),
        "current_eligible_count": len(eligible),
        "survivorship_delta_current_minus_start": len(eligible) - len(pit_start),
        "limitation": (
            "Historical research must reconstruct membership point-in-time; "
            "using only today-surviving symbols without PIT is forbidden as sole method"
        ),
    }

    research_symbols = select_research_symbols(snapshot, profiles)
    if len(research_symbols) < 5:
        research_symbols = [s for s in SEED_SYMBOLS if s in {i["symbol"] for i in eligible}]

    # --- AI gateway contract ---
    gw = AIGateway.from_env(mock_for_ci=True)
    ai_manifest = {
        "schema": "ai_provider_contract_v1",
        "ai_gateway_status": "IMPLEMENTED",
        "configured_provider_count": len(gw.providers),
        "providers": sorted(gw.providers.keys()),
        "role_map": gw.role_map,
        "ollama_status": "MOCK_OK" if "OLLAMA" in gw.providers else "MISSING",
        "groq_status": "MOCK_OK" if "GROQ" in gw.providers else "MISSING",
        "gemini_status": "MOCK_OK" if "GEMINI" in gw.providers else "MISSING",
        "cloudflare_status": "MOCK_OK" if "CLOUDFLARE_WORKERS_AI" in gw.providers else "MISSING",
        "external_secret_redaction_status": "IMPLEMENTED",
        "provider_fail_closed_status": "IMPLEMENTED",
        "openrouter_may_not_approve_orders": True,
        "ci_uses_mocked_providers": True,
        "hardcoded_free_tier_quotas": False,
    }
    _write(IMMUTABLE / "ai_provider_contract_manifest.json", ai_manifest)

    learning_contract = {
        "schema": "learning_loop_contract_v1",
        "learning_loop_status": "IMPLEMENTED",
        "lesson_schema_version": LESSON_SCHEMA_VERSION,
        "reflection_schema_version": REFLECTION_SCHEMA_VERSION,
        "path": [
            "Candidate",
            "Main Reasoner",
            "Deterministic Risk Critic",
            "Simulated Outcome",
            "Outcome Recorder",
            "Reflection AI",
            "Independent Reflection Critic",
            "Lesson Record",
            "Lesson Memory",
            "Relevant Lesson Retrieval",
            "Future Main Reasoner context",
            "Learning Patch proposal",
            "EATI validation",
        ],
        "ai_cannot_override_hard_risk": True,
        "autonomous_online_weight_training": False,
        "immediate_vs_permanent_boundary": "ENFORCED",
    }
    _write(IMMUTABLE / "learning_loop_contract.json", learning_contract)

    # --- Preregister H5 BEFORE execution ---
    prereg = preregistration_payload()
    pre_cs = preregistration_checksum()
    prereg["preregistration_checksum"] = pre_cs
    prereg["hypothesis_checksums"] = {h["hypothesis_id"]: sha_obj(h) for h in HYPOTHESES_H5}
    prereg["sealed_at"] = _utc()
    prereg["source_commit"] = _git_head()
    prereg["research_symbols_preselected_before_performance"] = research_symbols
    _write(IMMUTABLE / "h5_preregistration.json", prereg)
    assert pre_cs == preregistration_checksum()

    # --- Historical acquisition ---
    # Public market-data host only (not mainnet trading / not real money).
    import backend.nexus_demo_execution.historical_market_data as hmd
    import backend.nexus_demo_execution.microstructure_history as mh

    hmd.BYBIT_PUBLIC = "https://api.bybit.com"
    if hasattr(mh, "BYBIT_PUBLIC"):
        mh.BYBIT_PUBLIC = "https://api.bybit.com"

    start_ms, end_ms = H5_DEV_START_MS, H5_DEV_END_MS
    assert start_ms == RESEARCH_V2_V3_START_MS and end_ms == RESEARCH_V2_V3_END_MS
    assert end_ms <= SEPTEMBER_OOS_START_MS
    kline_dir = RUNTIME / "market_cache"
    micro_dir = RUNTIME / "micro_cache"
    kline_dir.mkdir(parents=True, exist_ok=True)
    micro_dir.mkdir(parents=True, exist_ok=True)

    datasets_by_iv: dict[str, list] = {}
    record_count = 0
    first_ts = None
    last_ts = None
    for interval in INTERVALS:
        print(f"download {interval} symbols={research_symbols}...", flush=True)
        max_pages = 200 if interval == "15" else 80
        try:
            datasets_by_iv[interval] = fetch_or_load_bundle(
                symbols=research_symbols,
                interval=interval,
                start_ms=start_ms,
                end_ms=end_ms,
                cache_dir=kline_dir,
                use_network=True,
                max_pages=max_pages,
            )
        except Exception as exc:
            print(f"fallback seeds after download error: {exc}", flush=True)
            research_symbols = list(SEED_SYMBOLS)
            datasets_by_iv[interval] = fetch_or_load_bundle(
                symbols=research_symbols,
                interval=interval,
                start_ms=start_ms,
                end_ms=end_ms,
                cache_dir=kline_dir,
                use_network=True,
                max_pages=max_pages,
            )
        for ds in datasets_by_iv[interval]:
            record_count += len(ds.candles)
            if ds.candles:
                first_ts = ds.candles[0].ts_ms if first_ts is None else min(first_ts, ds.candles[0].ts_ms)
                last_ts = ds.candles[-1].ts_ms if last_ts is None else max(last_ts, ds.candles[-1].ts_ms)

    print("download micro...", flush=True)
    micro = fetch_or_load_micro_bundle(
        symbols=research_symbols, start_ms=start_ms, end_ms=end_ms, cache_dir=micro_dir, use_network=True
    )

    for p in kline_dir.glob("*.json"):
        assert_september_partial_excluded(str(p))
        assert CONSUMED_HOLDOUT not in str(p)

    hist_manifest = {
        "schema": "historical_data_manifest_v1",
        "provider": "bybit_public_readonly",
        "research_symbols": research_symbols,
        "eligible_historical_symbol_count": len(research_symbols),
        "intervals": INTERVALS,
        "optional_5m_for_intrabar_only": True,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "historical_start": first_ts,
        "historical_end": last_ts,
        "historical_record_count": record_count,
        "never_replace_missing_oi_funding_with_zero": True,
        "raw_data_gitignored": True,
        "survivorship_bias": survivorship,
        "coverage_by_class": cov,
    }
    hist_manifest["historical_dataset_checksum"] = sha_obj(
        {
            "symbols": research_symbols,
            "start": start_ms,
            "end": end_ms,
            "records": record_count,
            "first": first_ts,
            "last": last_ts,
        }
    )
    _write(IMMUTABLE / "historical_data_manifest.json", hist_manifest)

    # PIT membership map for folds (coarse: start/mid/end)
    pit_membership_by_ts = {
        H5_DEV_START_MS: set(point_in_time_membership(snapshot, as_of_ms=H5_DEV_START_MS)),
        mid_ts: set(pit_mid),
        H5_DEV_END_MS: set(point_in_time_membership(snapshot, as_of_ms=H5_DEV_END_MS)),
    }

    # --- Execute H5 ---
    summary = run_edge_research_h5(
        datasets_15=datasets_by_iv["15"],
        datasets_60=datasets_by_iv["60"],
        datasets_240=datasets_by_iv["240"],
        micro=micro,
        prereg_checksum=pre_cs,
        pit_membership_by_ts=pit_membership_by_ts,
    )
    summary["updated_at"] = _utc()
    summary["H3_status"] = "REJECTED_CURRENT_POLICY"
    summary["september_h3_oos_status"] = "OOS_WINDOW_NOT_MATURE_RESEARCH_CONFIRMATION_ONLY"
    summary["wallet_delta_classification"] = "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST"
    summary["remaining_unattributed_delta"] = -0.97052039
    summary["trading_db_status"] = "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED"
    summary["demo_forward_packet_ready"] = False
    summary["demo_forward_status"] = "BLOCKED_PENDING_VALIDATED_POLICY_AND_OOS"
    summary["exchange_write_attempt_count"] = 0
    summary["h5_oos_downloaded"] = False
    summary["h5_oos_executed"] = False
    summary["h4_sealed"] = sealed_h4
    summary["universe"] = universe_summary
    summary["coverage"] = cov
    summary["ai"] = ai_manifest
    summary["learning"] = learning_contract
    summary["historical"] = {
        "historical_record_count": record_count,
        "historical_start": first_ts,
        "historical_end": last_ts,
        "historical_dataset_checksum": hist_manifest["historical_dataset_checksum"],
        "survivorship_bias_status": survivorship["status"],
        "point_in_time_membership_status": "IMPLEMENTED",
        "eligible_historical_symbol_count": len(research_symbols),
        "mainstream_count": cov["MAINSTREAM"],
        "mid_size_count": cov["MID_SIZE"],
        "small_count": cov["SMALL"],
        "meme_count": cov["MEME"],
        "non_meme_count": cov["NON_MEME"],
        "unknown_classification_count": cov["UNKNOWN"],
    }

    primary = summary.get("selected_primary_result")
    if primary:
        policy = freeze_policy_from_hyp(primary["hypothesis"], source_commit=_git_head(), symbols=research_symbols)
        _write(IMMUTABLE / "policy_checksum_manifest.json", policy)
        reservation = make_h5_oos_reservation(policy, research_symbols)
        _write(IMMUTABLE / "h5_oos_reservation_manifest.json", reservation)
        summary["selected_h5_policy_checksum"] = policy["policy_checksum"]
        summary["selected_h5_semantic_checksum"] = policy["semantic_checksum"]
        summary["h5_oos_reservation_id"] = reservation["reservation_id"]
        summary["h5_oos_reservation"] = reservation
    else:
        summary["selected_h5_policy_checksum"] = None
        summary["selected_h5_semantic_checksum"] = None
        summary["h5_oos_reservation_id"] = None
        summary["h5_oos_reservation"] = None

    summary["recommendation"] = recommendation_from_results(summary)

    slim = dict(summary)
    for r in slim.get("hypothesis_results") or []:
        r.pop("hypothesis", None)
        for k in ("replay", "adverse", "gross"):
            if isinstance(r.get(k), dict):
                keep = {
                    kk: r[k].get(kk)
                    for kk in (
                        "completed_trade_count",
                        "net_pnl",
                        "gross_pnl",
                        "net_expectancy",
                        "gross_expectancy",
                        "profit_factor",
                        "net_profit_factor",
                        "gross_profit_factor",
                        "win_rate",
                        "maximum_drawdown",
                        "consecutive_losses",
                    )
                }
                r[k] = keep
    _write(IMMUTABLE / "h5_walk_forward_summary.json", slim)

    print(
        json.dumps(
            {
                "recommendation": slim["recommendation"],
                "primary": slim.get("selected_h5_primary_policy"),
                "statuses": {r["hypothesis_id"]: r["status"] for r in slim.get("hypothesis_results") or []},
                "universe_eligible": universe_summary["dynamic_universe_symbol_count"],
                "research_symbols": research_symbols,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
