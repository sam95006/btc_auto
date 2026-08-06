#!/usr/bin/env python3
"""Optional small live smoke against official public endpoints (read-only).

Usage:
  python tools/official_market_adapters/optional_live_smoke.py

Classifies results as LIVE_READ_ONLY when network succeeds; never labels fixture as live.
On-Demand spend: $0. No API keys. No account/write endpoints.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_official_market_adapters.binance.adapter import BinanceUsdmPublicAdapter
from backend.nexus_official_market_adapters.bybit.adapter import BybitPublicV5Adapter
from backend.nexus_official_market_adapters.constants import DATA_MODE_LIVE_READ_ONLY
from backend.nexus_official_market_adapters.transport import default_urllib_transport


def _smoke_adapter(adapter, symbol: str) -> dict:
    adapter.set_data_mode(DATA_MODE_LIVE_READ_ONLY)
    # Inject real urllib transport for live smoke only.
    assert adapter.http is not None
    adapter.http.transport = default_urllib_transport
    results = {}
    try:
        obs = adapter.fetch_ticker(symbol=symbol)
        results["ticker"] = {
            "ok": obs.payload is not None,
            "data_mode": obs.data_mode,
            "quality": obs.quality,
            "access_method": obs.source_lineage.access_method,
            "symbol": symbol,
        }
    except Exception as exc:  # noqa: BLE001
        results["ticker"] = {
            "ok": False,
            "data_mode": "LIVE_READ_ONLY_ATTEMPTED",
            "error": type(exc).__name__,
            "detail": str(exc)[:200],
        }
    return {
        "adapter_id": adapter.manifest.adapter_id,
        "classified_as": DATA_MODE_LIVE_READ_ONLY if results.get("ticker", {}).get("ok") else "LIVE_ATTEMPT_FAILED",
        "results": results,
        "stats": adapter.stats(),
    }


def main() -> int:
    bybit = BybitPublicV5Adapter(use_fixtures=False)
    binance = BinanceUsdmPublicAdapter(use_fixtures=False)
    report = {
        "schema": "v18_a_optional_live_smoke_v1",
        "note": "Optional public endpoint smoke — no secrets, no writes",
        "bybit": _smoke_adapter(bybit, "BTCUSDT"),
        "binance": _smoke_adapter(binance, "BTCUSDT"),
    }
    print(json.dumps(report, indent=2))
    # Non-zero only on unexpected crash; network failure is honest FAIL of live attempt.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
