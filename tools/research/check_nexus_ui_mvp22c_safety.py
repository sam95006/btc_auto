#!/usr/bin/env python3
"""MVP-22C Read-only Market Anomaly Radar safety checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"

REQUIRED_FILES = [
    "market/anomalyTypes.ts",
    "market/anomalyConfig.ts",
    "market/anomalyEngine.ts",
    "market/anomalyStore.ts",
    "market/priceHistory.ts",
    "market/volumeHistory.ts",
    "market/useMarketAnomalies.tsx",
    "components/MarketAnomaliesPanel.tsx",
    "components/MarketAnomalyAlertSummary.tsx",
    "pages/AnomaliesPage.tsx",
]

REQUIRED_STRINGS = [
    "NEXUS_UI_MVP22C_MARKET_ANOMALY_RADAR",
    "NEXUS_UI_MVP22B_DERIVATIVES_CONTEXT",
    "NEXUS_UI_MVP22A_LIVE_MARKET_DATA",
    "Research threshold",
    "not a trade trigger",
    "Anomaly score ranks attention priority",
    "not trade probability",
    "not yet included in recommendation scoring",
    "Market anomaly",
    "not a trade instruction",
    "ANOMALY_CONFIG",
    "PRICE_ACCELERATION",
    "MULTI_FACTOR_ANOMALY",
    'path="/anomalies"',
    "BYBIT_MAINNET_LINEAR",
]

FORBIDDEN = [
    (r"\bStart Stage 4\.?19\b", "start_419"),
    (r"\bQuick Order\b", "quick_order"),
    (r'path:\s*["\']/trade', "trade_route"),
    (r"anomaly.*confidence", "anomaly_confidence_merge"),
]

FORBIDDEN_IN_ANOMALY = [
    (r"\bPlace Order\b", "place_order"),
    (r"\bARM\b", "arm_in_anomaly"),
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

    anomaly_blob = "\n".join(
        (SRC / "market" / f).read_text(encoding="utf-8", errors="replace")
        for f in (
            "anomalyEngine.ts",
            "anomalyStore.ts",
            "anomalyConfig.ts",
            "anomalyScoring.ts",
            "useMarketAnomalies.tsx",
        )
        if (SRC / "market" / f).is_file()
    )
    anomaly_blob += (SRC / "components" / "MarketAnomaliesPanel.tsx").read_text(
        encoding="utf-8", errors="replace"
    )

    rec = (SRC / "components" / "RecommendationBoard.tsx").read_text(encoding="utf-8", errors="replace")
    if "anomaly" in rec.lower() and "useMarketAnomalies" in rec:
        issues.append("recommendation_anomaly_coupling")

    for pat, name in FORBIDDEN:
        if re.search(pat, blob, re.I) and not re.search(
            rf"(no|never|forbidden|not).{{0,50}}{pat}", blob, re.I
        ):
            if name == "anomaly_confidence_merge" and "not trade probability" in blob:
                continue
            issues.append(f"forbidden:{name}")

    for pat, name in FORBIDDEN_IN_ANOMALY:
        if re.search(pat, anomaly_blob, re.I):
            issues.append(f"forbidden_anomaly:{name}")

    print("NEXUS UI MVP-22C Market Anomaly Radar safety check")
    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("PASS: anomaly radar read-only; no trade/ARM/scoring coupling")
    return 0


if __name__ == "__main__":
    sys.exit(main())
