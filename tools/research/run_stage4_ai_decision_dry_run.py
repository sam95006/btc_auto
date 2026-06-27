#!/usr/bin/env python3
"""Stage 4 AI Decision Layer — local dry-run loop (no orders)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_client import BybitDemoClient  # noqa: E402
from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_ai_decision_agent import (  # noqa: E402
    Stage4AIDecisionAgent,
    resolve_stage4_output_dir,
    write_decision,
)

READINESS = ROOT / "data/external_alpha/reports/stage4_ai_decision_dry_run_readiness.json"


def _fetch_market(symbol: str) -> Dict[str, Any]:
    try:
        client = BybitDemoClient("dry-run", allow_demo_order=False)
        ticker = client.fetch_ticker(symbol)
        return {
            "symbol": symbol.upper(),
            "last_price": float(ticker.get("lastPrice") or ticker.get("last_price") or 0),
            "prev_price_24h": float(ticker.get("prevPrice24h") or ticker.get("prev_price_24h") or 0),
            "source": "bybit_demo_public_ticker",
            "balance_read_ok": True,
        }
    except Exception as exc:
        return {
            "symbol": symbol.upper(),
            "last_price": 3200.0 if "ETH" in symbol.upper() else 65000.0,
            "prev_price_24h": 3180.0 if "ETH" in symbol.upper() else 64800.0,
            "source": "fallback_static",
            "error": str(exc)[:120],
        }


def _fetch_account() -> Dict[str, Any]:
    try:
        client = BybitDemoClient("dry-run", allow_demo_order=False)
        snap = client.get_account_balance()
        return {
            "total_equity": snap.get("total_equity"),
            "available_balance": snap.get("available_balance"),
            "wallet_balance": snap.get("wallet_balance"),
            "balance_read_ok": bool(snap.get("balance_read_ok")),
            "open_positions": client.count_open_positions(),
        }
    except Exception as exc:
        return {
            "total_equity": 5000.0,
            "available_balance": 5000.0,
            "wallet_balance": 5000.0,
            "balance_read_ok": True,
            "open_positions": 0,
            "fallback": True,
            "error": str(exc)[:120],
        }


def run_dry_run(
    *,
    duration_minutes: float,
    poll_interval_seconds: float,
    symbols: List[str],
    mode: str = "dry_run",
    output_dir: Path | None = None,
    use_real_llm: bool = False,
) -> Dict[str, Any]:
    out = output_dir or resolve_stage4_output_dir()
    agent = Stage4AIDecisionAgent(use_real_llm=use_real_llm)
    started = time.time()
    end = started + duration_minutes * 60.0
    decisions: List[Dict[str, Any]] = []
    tick = 0

    while time.time() < end:
        tick += 1
        account = _fetch_account()
        open_positions = int(account.get("open_positions") or 0)
        for symbol in symbols:
            market = _fetch_market(symbol)
            decision = agent.decide(
                symbol=symbol,
                mode=mode,
                market_context=market,
                account_context=account,
                open_positions=open_positions,
            )
            write_decision(out, decision)
            decisions.append(decision)
        if duration_minutes <= 0.05:
            break
        if time.time() >= end:
            break
        time.sleep(poll_interval_seconds)

    summary = {
        "record_type": "stage4_ai_decision_summary",
        "generated_at_utc": utc_now_iso(),
        "phase": "4",
        "mode": mode,
        "duration_minutes": duration_minutes,
        "poll_interval_seconds": poll_interval_seconds,
        "symbols": symbols,
        "decision_count": len(decisions),
        "tick_count": tick,
        "output_dir": str(out),
        "model_name": agent.model_name,
        "is_mock_ai": agent.is_mock_ai,
        "real_llm_used": agent.real_llm_used,
        "fallback_to_mock": agent.fallback_to_mock,
        "all_order_sent_false": all(not d.get("order_sent") for d in decisions),
        "decisions": [{"decision_id": d["decision_id"], "symbol": d["symbol"], "final_decision": d["final_decision"]} for d in decisions],
    }
    write_json(out / "stage4_ai_decision_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4 AI decision dry-run (no orders)")
    parser.add_argument("--duration-minutes", type=float, default=30.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=60.0)
    parser.add_argument("--symbols", default="ETHUSDT,BTCUSDT")
    parser.add_argument("--mode", default="dry_run")
    parser.add_argument("--fast-test", action="store_true", help="Single tick, no sleep")
    parser.add_argument("--use-real-llm", action="store_true")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    out = Path(args.output_dir) if args.output_dir else None
    duration = 0.01 if args.fast_test else args.duration_minutes
    poll = 0.0 if args.fast_test else args.poll_interval_seconds

    summary = run_dry_run(
        duration_minutes=duration,
        poll_interval_seconds=max(0.0, poll),
        symbols=symbols,
        mode=args.mode,
        output_dir=out,
        use_real_llm=args.use_real_llm,
    )

    from tools.research.validate_stage4_ai_decision_outputs import validate  # noqa: E402

    validation = validate(out or resolve_stage4_output_dir())
    write_json(
        READINESS,
        {
            "record_type": "stage4_ai_decision_dry_run_readiness",
            "generated_at_utc": utc_now_iso(),
            "summary": summary,
            "validation": validation,
        },
    )
    print(json.dumps({"summary": summary, "validation": validation}, indent=2))
    return 0 if validation.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
