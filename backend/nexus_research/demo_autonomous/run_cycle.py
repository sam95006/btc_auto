"""CLI: run one autonomous Demo scan cycle (dry-run by default).

Usage:
  python -m backend.nexus_research.demo_autonomous.run_cycle --live --equity 4994.18989642
  python -m backend.nexus_research.demo_autonomous.run_cycle --live --send --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Autonomous Bybit Demo scan/send cycle")
    p.add_argument("--equity", type=float, default=4994.18989642)
    p.add_argument("--live", action="store_true", help="Fetch live instruments+tickers from api-demo")
    p.add_argument("--send", action="store_true", help="Attempt send (requires session + adapter)")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--live-write", action="store_true", help="Disable dry-run writes (Demo only)")
    p.add_argument("--issue-session", action="store_true")
    p.add_argument("--ttl-ms", type=int, default=6 * 60 * 60 * 1000)
    args = p.parse_args(argv)

    from backend.nexus_research.demo_autonomous.orchestrator import AutonomousDemoOrchestrator
    from backend.nexus_research.demo_autonomous.session_authorization import AuthorizationValidator
    from backend.nexus_research.demo_autonomous.write_adapter import AutonomousDemoOrderAdapter
    from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport
    from backend.nexus_research.demo_exchange.signer import DemoRequestSigner
    import os

    auth = AuthorizationValidator()
    if args.issue_session:
        sess = auth.issue(ttl_ms=args.ttl_ms, max_risk_per_trade_pct=0.5)
        print(json.dumps({"sessionIssued": sess.to_public_dict()}, ensure_ascii=False))

    dry_run = not args.live_write
    adapter = None
    if args.send:
        key = os.environ.get("BYBIT_DEMO_API_KEY", "").strip()
        secret = os.environ.get("BYBIT_DEMO_API_SECRET", "").strip()
        if key and secret and auth.session and auth.session.is_active():
            transport = DemoWriteTransport(
                signer=DemoRequestSigner(key, secret),
                auth=auth,
                dry_run=dry_run,
            )
            adapter = AutonomousDemoOrderAdapter(transport, auth=auth)

    instruments = None
    quality = None
    if args.live:
        from backend.nexus_research.demo_autonomous.instruments_fetch import (
            fetch_linear_perpetual_instruments,
        )
        from backend.nexus_research.demo_autonomous.market_quality_fetch import (
            fetch_ticker_quality,
        )
        instruments = fetch_linear_perpetual_instruments()
        quality = fetch_ticker_quality()

    orch = AutonomousDemoOrchestrator(auth=auth, write_adapter=adapter, dry_run=dry_run)
    result = orch.run_cycle(
        equity=args.equity,
        instruments=instruments,
        quality=quality,
        send=bool(args.send),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.blocker is None or not args.send else 2


if __name__ == "__main__":
    sys.exit(main())
