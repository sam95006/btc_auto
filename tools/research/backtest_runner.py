"""CLI: Binance kline research + walk-forward gate (single exchange)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="NEXUS Binance kline research CLI")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"])
    parser.add_argument("--interval", default=None)
    parser.add_argument("--full", action="store_true", help="Include walk-forward from trading.db")
    args = parser.parse_args()

    from backend.analytics.kline_backtest_engine import KlineBacktestEngine
    from backend.analytics.research_gate_service import ResearchGateService
    from backend.services.runtime_store import runtime_store
    from backend.trading.binance_futures_testnet_client import BinanceFuturesTestnetClient

    client = BinanceFuturesTestnetClient()
    kline = KlineBacktestEngine(futures_client=client)
    payload = {
        "symbol": args.symbol.upper(),
        "kline_research": kline.evaluate(
            args.symbol.upper(),
            args.side.upper(),
            interval=args.interval,
        ),
    }
    if args.full:
        gate = ResearchGateService(futures_client=client)
        payload["research_gate"] = gate.build_status(
            runtime_store.recent_trade_results(limit=160),
            symbol=args.symbol.upper(),
            side=args.side.upper(),
        )
        from backend.analytics.performance_report import build_performance_report

        payload["performance"] = build_performance_report(
            runtime_store,
            research_gate=payload.get("research_gate"),
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
