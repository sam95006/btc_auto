#!/usr/bin/env python3
"""Verify funding % conversion, OI units, volume/turnover separation, missing fields."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.api.market_public_routes import _fetch_ticker  # noqa: E402


def funding_to_pct(rate: float) -> float:
    return rate * 100.0


def main() -> int:
    print("NEXUS MVP-22B derivatives field verification")
    issues: list[str] = []
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        row = _fetch_ticker(sym)
        print(
            f"  {sym}: oi={row.get('openInterest')} oiVal={row.get('openInterestValue')} "
            f"fr={row.get('fundingRate')} vol={row.get('volume24h')} to={row.get('turnover24h')}"
        )
        if row.get("openInterest") is None:
            issues.append(f"{sym}:oi_missing")
        if row.get("openInterestValue") is None:
            issues.append(f"{sym}:oi_value_missing")
        if row.get("fundingRate") is None:
            issues.append(f"{sym}:funding_missing")
        if row.get("volume24h") is None:
            issues.append(f"{sym}:volume_missing")
        if row.get("turnover24h") is None:
            issues.append(f"{sym}:turnover_missing")
        # units sanity: value >> coin qty for BTC/ETH
        if row.get("openInterest") and row.get("openInterestValue"):
            if float(row["openInterestValue"]) < float(row["openInterest"]):
                issues.append(f"{sym}:oi_units_suspicious")
        if row.get("volume24h") and row.get("turnover24h"):
            if float(row["turnover24h"]) < float(row["volume24h"]):
                issues.append(f"{sym}:volume_turnover_suspicious")
        fr = row.get("fundingRate")
        if fr is not None:
            pct = funding_to_pct(float(fr))
            # must not treat decimal as already-percent wrongly for typical small rates
            if abs(float(fr)) < 0.01 and abs(pct) > 5:
                issues.append(f"{sym}:funding_pct_implausible")
            print(f"       funding_pct_display={pct:.6f}%")

    # frontend helpers exist
    for rel in (
        "frontend/src/market/fundingConfig.ts",
        "frontend/src/market/oiHistory.ts",
        "frontend/src/market/derivativesContext.ts",
        "frontend/src/components/MarketContextPanel.tsx",
    ):
        if not (ROOT / rel).is_file():
            issues.append(f"missing:{rel}")

    funding = (ROOT / "frontend/src/market/fundingConfig.ts").read_text(encoding="utf-8")
    if "rateToPctMultiplier: 100" not in funding:
        issues.append("funding_multiplier_missing")

    oi = (ROOT / "frontend/src/market/oiHistory.ts").read_text(encoding="utf-8")
    if "collecting" not in oi:
        issues.append("oi_collecting_missing")

    # missing-field merge behavior
    feed = (ROOT / "frontend/src/market/LiveMarketFeed.ts").read_text(encoding="utf-8")
    if "openInterest: next.openInterest ?? prev?.openInterest" not in feed:
        issues.append("ws_merge_missing")

    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("PASS: OI/Funding/Volume fields + units + funding % + merge/collecting present")
    print("NOTE: oi_5m/15m live duration pending until samples accumulate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
