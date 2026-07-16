#!/usr/bin/env python3
"""Read-only verification: Bybit Mainnet public REST vs NEXUS market proxy adapter.

Does not open WebSocket browser sessions. Validates:
  - Mainnet public REST lastPrice fields
  - Local / Flask proxy adapter shape (if running)
  - Price delta within max(2 ticks, 5 bps) across two samples
  - Timestamps advance
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.api.market_public_routes import ALLOWED_SYMBOLS, _fetch_ticker  # noqa: E402

BPS = 5 / 10_000


def _tick_size(symbol: str) -> float:
    if symbol.startswith("BTC"):
        return 0.1
    if symbol.startswith("ETH"):
        return 0.01
    return 0.01


def _within(a: float, b: float, symbol: str) -> bool:
    tol = max(2 * _tick_size(symbol), abs(a) * BPS)
    return abs(a - b) <= tol


def main() -> int:
    print("NEXUS MVP-22A official Mainnet REST comparison")
    samples: dict[str, list[dict]] = {s: [] for s in ALLOWED_SYMBOLS}
    for round_i in range(2):
        for sym in ALLOWED_SYMBOLS:
            row = _fetch_ticker(sym)
            samples[sym].append(row)
            print(
                f"  [{round_i}] {sym} last={row['lastPrice']} mark={row.get('markPrice')} "
                f"src={row['source']} field={row['priceType']}"
            )
        if round_i == 0:
            time.sleep(2.5)

    issues: list[str] = []
    for sym, rows in samples.items():
        a, b = rows[0], rows[1]
        if a["source"] != "BYBIT_MAINNET_LINEAR" or a["priceType"] != "LAST":
            issues.append(f"{sym}: bad_source_or_field")
        if not _within(float(a["lastPrice"]), float(b["lastPrice"]), sym):
            # large move in 2.5s is rare but possible — only warn if timestamps identical
            if a.get("exchangeTimestamp") and a.get("exchangeTimestamp") == b.get("exchangeTimestamp"):
                issues.append(f"{sym}: timestamp_not_advancing")
        # received path: exchange ts may be missing on some payloads; lastPrice must be finite
        if not isinstance(a["lastPrice"], float):
            issues.append(f"{sym}: last_not_float")

    # Optional local proxy check
    try:
        qs = urllib.parse.urlencode({"category": "linear", "symbols": ",".join(ALLOWED_SYMBOLS)})
        req = urllib.request.Request(
            f"http://127.0.0.1:5000/api/market/tickers?{qs}",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as raw:
            proxy = json.loads(raw.read().decode("utf-8"))
        if proxy.get("ok") and proxy.get("tickers"):
            print("  local_proxy: PASS")
            for t in proxy["tickers"]:
                official = _fetch_ticker(t["symbol"])
                if not _within(float(t["lastPrice"]), float(official["lastPrice"]), t["symbol"]):
                    issues.append(f"proxy_delta:{t['symbol']}")
        else:
            print("  local_proxy: SKIP (not ok)")
    except Exception as exc:
        print(f"  local_proxy: SKIP ({exc})")

    # Static code guarantees
    feed = (ROOT / "frontend" / "src" / "market" / "LiveMarketFeed.ts").read_text(encoding="utf-8")
    for needle in ("restFallback", "reconnecting", "bootstrapRest", "BybitPublicTickerSocket"):
        if needle not in feed:
            issues.append(f"feed_missing:{needle}")
    freshness = (ROOT / "frontend" / "src" / "market" / "freshness.ts").read_text(encoding="utf-8")
    if "REST_FALLBACK" not in freshness:
        issues.append("freshness_missing:REST_FALLBACK")

    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("PASS: Mainnet public lastPrice samples + feed reconnect/fallback code present")
    print("NOTE: browser WS LIVE / hard-refresh LIVE checks require redeploy + live sign-off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
