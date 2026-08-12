#!/usr/bin/env python3
"""H3 failure postmortem + H4 Edge Research V1.

No Demo orders. No September OOS. No consumed holdout reuse as qualification.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.closed_historical_registry import (
    RESEARCH_V2_V3_END_MS,
    RESEARCH_V2_V3_START_MS,
    SEPTEMBER_OOS_END_MS,
    SEPTEMBER_OOS_START_MS,
    assert_september_partial_excluded,
)
from backend.nexus_demo_execution.edge_research_h4 import (
    preregistration_checksum,
    preregistration_payload,
    run_edge_research_h4,
    sha_obj,
)
from backend.nexus_demo_execution.edge_research_h4_hypotheses import H4_DEV_END_MS, H4_DEV_START_MS, HYPOTHESES_H4
from backend.nexus_demo_execution.h3_failure_postmortem import build_h3_failure_decomposition
from backend.nexus_demo_execution.historical_market_data import fetch_or_load_bundle
from backend.nexus_demo_execution.microstructure_history import fetch_or_load_micro_bundle

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE = ROOT / "artifacts" / "readiness" / "immutable" / "h4_edge_research_v1"
RUNTIME = ROOT / ".nexus_runtime" / "research" / "h4_edge_research_v1"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
INTERVALS = ["15", "60", "240"]
CONSUMED_HOLDOUT = "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED"
HOLDOUT_START = 1_720_863_000_000
HOLDOUT_END = 1_736_415_000_000


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


def assert_dev_window_clean(start_ms: int, end_ms: int) -> None:
    assert start_ms == H4_DEV_START_MS and end_ms == H4_DEV_END_MS
    assert not (start_ms <= HOLDOUT_START and end_ms >= HOLDOUT_END), "dev must not be holdout"
    # Dev equals prior research span; must not include September reservation interior
    assert end_ms <= SEPTEMBER_OOS_START_MS
    assert end_ms == RESEARCH_V2_V3_END_MS
    assert start_ms == RESEARCH_V2_V3_START_MS
    assert_september_partial_excluded("ok_path_without_september")


def freeze_policy_from_hyp(hyp: dict[str, Any], *, source_commit: str) -> dict[str, Any]:
    policy = {
        "policy_id": f"{hyp['hypothesis_id']}_POLICY_V1_FROZEN",
        "qualification_role": "PRIMARY_H4_CANDIDATE",
        "hypothesis_id": hyp["hypothesis_id"],
        "strategy": "trend_following",
        "regime": "TRENDING_DOWN",
        "side": "Sell",
        "entry_rules": {
            "entry_logic": hyp["entry_logic"],
            "parameter_values": hyp["parameter_values"],
            "churn_logic": hyp["churn_logic"],
        },
        "confirmation_rules": {"confirmation_logic": hyp["confirmation_logic"]},
        "cost_gate_rules": {
            "MIN_NET_REWARD_RISK_RATIO": 1.2,
            "MIN_NET_REWARD_TO_COST": 1.5,
            "floors_immutable": True,
            "maker_assumption_forbidden": True,
        },
        "risk_sizing_rules": {
            "margin_usdt": 20,
            "leverage": 25,
            "margin_mode": "ISOLATED",
            "maximum_notional": 500,
            "maximum_single_trade_loss": 3,
        },
        "cost_assumptions": {
            "taker_fee_rate_default": 0.00055,
            "maker_fee_rate": 0.00020,
            "default_round_trip": "TAKER_PLUS_TAKER",
            "round_trip_rate": 0.00110,
        },
        "symbols": SYMBOLS,
        "intervals": INTERVALS,
        "source_commit": source_commit,
        "frozen_at": _utc(),
        "created_before_oos_download": True,
        "mutation_forbidden_until_oos_terminal": True,
    }
    policy["policy_checksum"] = sha_obj(policy)
    policy["semantic_checksum"] = sha_obj(
        {
            "hypothesis_id": hyp["hypothesis_id"],
            "parameter_values": hyp["parameter_values"],
            "entry_logic": hyp["entry_logic"],
            "confirmation_logic": hyp["confirmation_logic"],
            "gates_ref": "H4_GATES",
        }
    )
    return policy


def make_h4_oos_reservation(policy: dict[str, Any]) -> dict[str, Any]:
    # Begin after September reserved end + 1ms gap; 45-day future window placeholder from freeze time.
    # Must not overlap September or consumed holdout or training.
    start = SEPTEMBER_OOS_END_MS + 1
    # 45 days
    end = start + 45 * 86_400_000
    return {
        "reservation_id": "H4_UNTOUCHED_OOS_V1_RESERVED",
        "reserved_start": start,
        "reserved_end": end,
        "symbols": SYMBOLS,
        "intervals": INTERVALS,
        "primary_policy_id": policy["policy_id"],
        "policy_checksum": policy["policy_checksum"],
        "semantic_checksum": policy["semantic_checksum"],
        "downloaded": False,
        "executed": False,
        "created_before_download": True,
        "overlap_september_oos": False,
        "overlap_consumed_h3_holdout": False,
        "overlap_training": False,
        "created_at": _utc(),
        "note": "Future untouched H4 OOS; do not download/execute in this research task",
    }


def recommendation_from_results(summary: dict[str, Any], *, block_defect: bool) -> str:
    if block_defect:
        return "NEXUS_H4_RESEARCH_DATA_OR_SIMULATION_DEFECT"
    if summary.get("selected_h4_primary_policy"):
        return "NEXUS_H4_WALK_FORWARD_VALIDATED_NEW_OOS_REQUIRED"
    statuses = [r.get("status") for r in summary.get("hypothesis_results") or []]
    if all(s == "INSUFFICIENT_SAMPLE" for s in statuses) and statuses:
        return "NEXUS_H4_RESEARCH_INSUFFICIENT_SAMPLE"
    if any(s == "DATA_INVALID" for s in statuses):
        return "NEXUS_H4_RESEARCH_DATA_OR_SIMULATION_DEFECT"
    return "NEXUS_H4_RESEARCH_FAILED_NO_DEMO"


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    IMMUTABLE.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)

    # 1) Postmortem (diagnostic only)
    decomp = build_h3_failure_decomposition(root=ROOT)
    _write(IMMUTABLE / "h3_failure_decomposition.json", decomp)
    if decomp.get("block_h4_for_defect"):
        out = {
            "recommendation": "NEXUS_H4_RESEARCH_DATA_OR_SIMULATION_DEFECT",
            "H3_status": "REJECTED_CURRENT_POLICY",
            "decomposition": decomp,
            "exchange_write_attempt_count": 0,
        }
        _write(IMMUTABLE / "h4_research_summary.json", out)
        print(json.dumps(out, indent=2))
        return 0

    # 2) Preregister BEFORE any H4 execution
    prereg = preregistration_payload()
    pre_cs = preregistration_checksum()
    prereg["preregistration_checksum"] = pre_cs
    prereg["hypothesis_checksums"] = {
        h["hypothesis_id"]: sha_obj(h) for h in HYPOTHESES_H4
    }
    prereg["sealed_at"] = _utc()
    prereg["source_commit"] = _git_head()
    _write(IMMUTABLE / "h4_preregistration.json", prereg)
    assert pre_cs == preregistration_checksum()

    # 3) Development data — prior research span only
    start_ms, end_ms = H4_DEV_START_MS, H4_DEV_END_MS
    assert_dev_window_clean(start_ms, end_ms)
    kline_dir = RUNTIME / "market_cache"
    micro_dir = RUNTIME / "micro_cache"
    kline_dir.mkdir(parents=True, exist_ok=True)
    micro_dir.mkdir(parents=True, exist_ok=True)

    datasets_by_iv: dict[str, list] = {}
    for interval in INTERVALS:
        print(f"download {interval}...", flush=True)
        max_pages = 200 if interval == "15" else 80
        datasets_by_iv[interval] = fetch_or_load_bundle(
            symbols=SYMBOLS,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
            cache_dir=kline_dir,
            use_network=True,
            max_pages=max_pages,
        )
    print("download micro...", flush=True)
    micro = fetch_or_load_micro_bundle(
        symbols=SYMBOLS, start_ms=start_ms, end_ms=end_ms, cache_dir=micro_dir, use_network=True
    )

    # Guard: caches must not be September partial
    for p in kline_dir.glob("*.json"):
        assert_september_partial_excluded(str(p))
        assert CONSUMED_HOLDOUT not in str(p)

    # 4) Execute research
    summary = run_edge_research_h4(
        datasets_15=datasets_by_iv["15"],
        datasets_60=datasets_by_iv["60"],
        datasets_240=datasets_by_iv["240"],
        micro=micro,
        prereg_checksum=pre_cs,
    )
    summary["updated_at"] = _utc()
    summary["development_window"] = {"start_ms": start_ms, "end_ms": end_ms}
    summary["excluded"] = {
        "consumed_holdout": CONSUMED_HOLDOUT,
        "september_oos": "OOS_H3_UNTOUCHED_V1_RESERVED",
        "september_partial_cache": True,
    }
    summary["H3_status"] = "REJECTED_CURRENT_POLICY"
    summary["september_h3_oos_status"] = "OOS_WINDOW_NOT_MATURE_RESEARCH_CONFIRMATION_ONLY"
    summary["demo_forward_packet_ready"] = False
    summary["demo_forward_status"] = "BLOCKED_NO_VALIDATED_POLICY"
    summary["exchange_write_attempt_count"] = 0
    summary["wallet_delta_classification"] = "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST"
    summary["remaining_unattributed_delta"] = -0.97052039
    summary["trading_db_status"] = "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED"
    summary["primary_root_cause"] = decomp["primary_root_cause"]
    summary["secondary_root_causes"] = decomp["secondary_root_causes"]

    primary = summary.get("selected_primary_result")
    if primary:
        policy = freeze_policy_from_hyp(primary["hypothesis"], source_commit=_git_head())
        _write(IMMUTABLE / "policy_checksum_manifest.json", policy)
        # Also store under readiness/policies for freeze evidence
        pol_path = ROOT / "artifacts" / "readiness" / "policies" / f"{policy['policy_id']}.json"
        _write(pol_path, policy)
        reservation = make_h4_oos_reservation(policy)
        _write(IMMUTABLE / "h4_oos_reservation_manifest.json", reservation)
        _write(ROOT / "artifacts" / "readiness" / "H4_UNTOUCHED_OOS_V1_RESERVATION.json", reservation)
        summary["selected_h4_policy_checksum"] = policy["policy_checksum"]
        summary["selected_h4_semantic_checksum"] = policy["semantic_checksum"]
        summary["h4_oos_reservation"] = reservation
    else:
        summary["selected_h4_policy_checksum"] = None
        summary["selected_h4_semantic_checksum"] = None
        summary["h4_oos_reservation"] = None

    summary["recommendation"] = recommendation_from_results(summary, block_defect=False)
    # Strip bulky nested hypothesis copies for committed summary size
    slim = dict(summary)
    for r in slim.get("hypothesis_results") or []:
        r.pop("hypothesis", None)
        # keep replay/adverse/gross compact — drop huge if needed
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
                        "fees",
                        "spread",
                        "slippage",
                        "funding",
                        "symbols",
                    )
                }
                r[k] = keep
    _write(IMMUTABLE / "h4_research_summary.json", slim)
    print(
        json.dumps(
            {
                "recommendation": slim["recommendation"],
                "primary": slim.get("selected_h4_primary_policy"),
                "statuses": {r["hypothesis_id"]: r["status"] for r in slim.get("hypothesis_results") or []},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
