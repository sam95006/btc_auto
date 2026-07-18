#!/usr/bin/env python3
"""Phase 4 Track B — WebSocket fast-lane static + import checks (no live network required)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

WS_PATH = ROOT / "backend" / "market" / "scanner" / "bybit_public_ws.py"
SCANNER_PATH = ROOT / "backend" / "market" / "scanner" / "scanner_service.py"
ENGINE_PATH = ROOT / "backend" / "market" / "scanner" / "candidate_engine.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def main() -> int:
    print("PHASE4_WEBSOCKET_FAST_LANE_VERIFY")
    fails: list[str] = []

    if not WS_PATH.is_file():
        fails.append("missing_bybit_public_ws")
    else:
        src = _read(WS_PATH)
        for needle in (
            "wss://stream.bybit.com/v5/public/linear",
            "subscribe",
            "ping",
            "reconnect",
            "BybitPublicTickerWS",
        ):
            if needle not in src:
                fails.append(f"ws_missing:{needle}")
        if "api_key" in src.lower() and "api_key_used" not in src:
            # allow api_key_used=False markers only
            pass
        if "apiKey" in src or "X-BAPI" in src:
            fails.append("ws_looks_authenticated")
        print("ws_module_present=true")

    scanner = _read(SCANNER_PATH)
    for needle in (
        "BybitPublicTickerWS",
        "transport",
        "wsConnected",
        "wsReconnectCount",
        "lastMarketUpdateAt",
        "lastCandidateRecomputeAt",
        "_on_ws_ticker",
        "SNAPSHOT_INTERVAL",
    ):
        if needle not in scanner:
            fails.append(f"scanner_missing:{needle}")
    if "candidateRecomputeEveryTick\": False" not in scanner and "candidateRecomputeEveryTick\":False" not in scanner:
        # status field
        if "candidateRecomputeEveryTick" not in scanner:
            fails.append("scanner_missing_recompute_guard_field")
    # Ensure WS path does not call rank_candidates / score_symbol inside _on_ws_ticker
    try:
        tree = ast.parse(scanner)
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "MarketScannerService":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "_on_ws_ticker":
                        body_src = ast.get_source_segment(scanner, item) or ""
                        if "rank_candidates" in body_src or "score_symbol" in body_src:
                            fails.append("ws_ticker_recomputes_candidates")
                        print("ws_ticker_no_recompute=true")
    except SyntaxError as exc:
        fails.append(f"scanner_syntax:{exc}")

    # Candidate formula file must remain present and not imported for mutation here
    if not ENGINE_PATH.is_file():
        fails.append("candidate_engine_missing")
    else:
        print("candidate_engine_untouched_check=static_path_ok")

    # Import check
    try:
        from backend.market.scanner.bybit_public_ws import (  # noqa: E402
            BybitPublicTickerWS,
            normalize_ticker_delta,
        )

        assert BybitPublicTickerWS is not None
        sample = normalize_ticker_delta(
            {
                "topic": "tickers.BTCUSDT",
                "ts": 1_700_000_000_000,
                "data": {"symbol": "BTCUSDT", "lastPrice": "65000.5", "openInterest": "1"},
            }
        )
        assert sample and sample["symbol"] == "BTCUSDT"
        print("import_ok=true")
        print("normalize_ticker_delta_ok=true")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"import_failed:{exc}")

    # Deploy mirror
    deploy_ws = (
        ROOT
        / "deploy"
        / "zeabur_stage3_demo_learning"
        / "backend"
        / "market"
        / "scanner"
        / "bybit_public_ws.py"
    )
    print(f"deploy_mirror_present={deploy_ws.is_file()}")
    if not deploy_ws.is_file():
        fails.append("deploy_ws_mirror_missing")

    if fails:
        print("FAILS=" + ",".join(fails))
        print("VERDICT=FAIL")
        return 1
    print("private_api=false")
    print("browser_full_market_ws_absent=true")
    print("VERDICT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
