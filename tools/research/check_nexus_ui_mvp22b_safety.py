#!/usr/bin/env python3
"""MVP-22B Derivatives Market Context Layer safety checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"

REQUIRED_FILES = [
    "market/fundingConfig.ts",
    "market/oiHistory.ts",
    "market/derivativesContext.ts",
    "components/MarketContextPanel.tsx",
]

REQUIRED_STRINGS = [
    "openInterest",
    "fundingRate",
    "volume24h",
    "turnover24h",
    "DerivativesMarketContext",
    "Market Context",
    "not yet included in recommendation scoring",
    "Collecting",
    "FUNDING_CONFIG",
    "BYBIT_MAINNET_LINEAR",
]

FORBIDDEN = [
    (r"\bStart Stage 4\.?19\b", "start_419"),
    (r"\bQuick Order\b", "quick_order"),
    (r'path:\s*["\']/trade', "trade_route"),
]


def main() -> int:
    issues: list[str] = []
    for rel in REQUIRED_FILES:
        if not (SRC / rel).is_file():
            issues.append(f"missing:{rel}")

    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in SRC.rglob("*")
        if p.suffix in {".ts", ".tsx", ".css"} and p.is_file()
    )
    for s in REQUIRED_STRINGS:
        if s not in blob:
            issues.append(f"missing_string:{s}")

    # recommendation algorithm must not be rewritten by 22B
    if "recommendation scoring" not in blob.lower() and "not yet included" not in blob:
        issues.append("missing_scoring_disclaimer")

    proxy = (ROOT / "backend" / "api" / "market_public_routes.py").read_text(encoding="utf-8")
    for field in ("openInterest", "fundingRate", "volume24h", "turnover24h", "nextFundingTime"):
        if field not in proxy:
            issues.append(f"proxy_missing:{field}")

    for pat, name in FORBIDDEN:
        if re.search(pat, blob, re.I) and not re.search(
            rf"(no|never|forbidden).{{0,40}}{pat}", blob, re.I
        ):
            issues.append(f"forbidden:{name}")

    print("NEXUS UI MVP-22B Derivatives Market Context safety check")
    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("PASS: OI/Funding/Volume context + units/disclaimer present; no trade routes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
