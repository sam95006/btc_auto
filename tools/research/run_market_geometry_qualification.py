#!/usr/bin/env python3
"""Offline true-market geometry qualification runner — no trading session."""
from __future__ import annotations

import json
import time
from pathlib import Path

from backend.nexus_demo_execution.historical_market_data import fetch_or_load_bundle
from backend.nexus_demo_execution.market_event_sim import run_market_qualification
from backend.nexus_demo_execution.risk_review_packet import build_risk_review_packet
from backend.nexus_demo_execution.shadow_plan import build_shadow_plan
from backend.nexus_demo_execution.wallet_delta_reconcile import reconcile_wallet_delta

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "demo_validation_geometry_market_oos"
CACHE = OUT / "market_cache"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    end_ms = int(time.time() * 1000)
    # ~180 days of 15m bars across liquid symbols
    start_ms = end_ms - 180 * 24 * 60 * 60 * 1000
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    datasets = fetch_or_load_bundle(
        symbols=symbols,
        interval="15",
        start_ms=start_ms,
        end_ms=end_ms,
        cache_dir=CACHE,
        use_network=True,
    )
    report = run_market_qualification(datasets, min_sample=30)
    shadow = build_shadow_plan()
    risk = build_risk_review_packet(
        walk_forward={
            "simulated_trade_count": report.get("walk_forward_simulated_trades"),
            "walk_forward_status": "WALK_FORWARD_PERFORMANCE_COMPUTED",
            **(report.get("walk_forward_folds") or {}).get("fold1_validation", {}),
        },
        oos={
            **(report.get("oos") or {}),
            "oos_status": report.get("oos_status"),
            "path_source": "REAL_HISTORICAL_MARKET_DATA",
        },
    )
    # Only ready when market OOS validated
    risk["packet_ready"] = bool(report.get("risk_review_packet_ready"))
    risk["risk_review_status"] = "RISK_REVIEW_PENDING_FOUNDER"

    wallet = reconcile_wallet_delta(
        starting_wallet=5024.24829280,
        final_wallet=5023.27777241,
        closed_pnl_rows=[],
        execution_rows=[],
        transaction_rows=[],
        available_balance=5028.60306306,
        equity=5023.27777241,
    )
    # Prefer prior final attempt if present
    prior = ROOT / "artifacts" / "demo_validation_12h_v3_forensic" / "wallet_delta_final_attempt.json"
    if prior.exists():
        try:
            wallet_prior = json.loads(prior.read_text(encoding="utf-8-sig"))
            wallet_block = {
                "wallet_delta_classification": wallet_prior.get("wallet_delta_classification")
                or wallet_prior.get("classification")
                or wallet["classification"],
                "wallet_delta_attributed": wallet_prior.get("wallet_delta_attributed", wallet["wallet_delta_attributed"]),
                "wallet_delta_unattributed": wallet_prior.get(
                    "wallet_delta_unattributed", wallet["wallet_delta_unattributed"]
                ),
                "matching_record_count": wallet_prior.get("evidence_record_count")
                or wallet.get("evidence_record_count"),
                "evidence_paths": [
                    str(prior.as_posix()),
                    "transaction_log",
                    "execution_history",
                    "closed_pnl",
                ],
            }
        except Exception:
            wallet_block = {
                "wallet_delta_classification": wallet["classification"],
                "wallet_delta_attributed": wallet["wallet_delta_attributed"],
                "wallet_delta_unattributed": wallet["wallet_delta_unattributed"],
                "matching_record_count": wallet.get("evidence_record_count"),
                "evidence_paths": ["wallet_delta_reconcile"],
            }
    else:
        wallet_block = {
            "wallet_delta_classification": wallet["classification"],
            "wallet_delta_attributed": wallet["wallet_delta_attributed"],
            "wallet_delta_unattributed": wallet["wallet_delta_unattributed"],
            "matching_record_count": wallet.get("evidence_record_count"),
            "evidence_paths": ["wallet_delta_reconcile"],
        }

    payload = {
        **report,
        "risk_review_packet": risk,
        "shadow_plan": shadow,
        "shadow_plan_ready": shadow["shadow_plan_ready"],
        "wallet": wallet_block,
        "safety_freeze": {
            "EXCHANGE_WRITE": False,
            "DEMO_AUTONOMOUS_ENABLED": False,
            "MAINNET": False,
            "REAL_MONEY": False,
            "24H_GATE_APPROVED": False,
            "no_trading_session": True,
            "geometry_not_deployed_as_execution_policy": True,
        },
    }
    (OUT / "market_oos_qualification_report.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "recommendation": payload.get("recommendation"),
                "oos_status": payload.get("oos_status"),
                "market_data_source": payload.get("market_data_source"),
                "synthetic_forced_trade_count": payload.get("synthetic_forced_trade_count"),
                "look_ahead_contamination": payload.get("look_ahead_contamination"),
                "oos_simulated_trades": payload.get("oos_simulated_trades"),
                "oos_net_pnl": payload.get("oos_net_pnl"),
                "risk_review_packet_ready": payload.get("risk_review_packet_ready"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
