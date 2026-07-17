#!/usr/bin/env python3
"""MVP-22D Anomaly Outcome Research safety checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"

REQUIRED_FILES = [
    "market/anomalyOutcomeTypes.ts",
    "market/anomalyOutcomeConfig.ts",
    "market/anomalyOutcomeMath.ts",
    "market/anomalyOutcomeStore.ts",
    "market/anomalyOutcomeAggregation.ts",
    "market/useAnomalyOutcomes.tsx",
    "components/AnomalyOutcomesPanel.tsx",
    "pages/AnomalyOutcomesPage.tsx",
]

REQUIRED_STRINGS = [
    "NEXUS_UI_MVP22D_ANOMALY_OUTCOME_RESEARCH",
    "NEXUS_UI_MVP22C_MARKET_ANOMALY_RADAR",
    "Observed research outcomes",
    "Insufficient sample",
    "researchOnly: true",
    "OUTCOME_TIMESTAMP_TOLERANCE_MS",
    'path="/anomaly-outcomes"',
    "View outcome tracking",
    "NOT a trade instruction",
    "not feed Recommendation",
]

FORBIDDEN = [
    (r"\bStart Stage 4\.?19\b", "start_419"),
    (r"\bQuick Order\b", "quick_order"),
    (r'path:\s*["\']/trade', "trade_route"),
    (r"outcome.*confidence", "outcome_confidence_merge"),
    (r"win rate", "win_rate_claim"),
]

FORBIDDEN_IN_OUTCOME = [
    (r"\bPlace Order\b", "place_order"),
    (r"\bARM\b", "arm_in_outcome"),
    (r"expected profit", "expected_profit"),
    (r"trade probability", "trade_probability"),
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

    outcome_blob = "\n".join(
        (SRC / "market" / f).read_text(encoding="utf-8", errors="replace")
        for f in (
            "anomalyOutcomeStore.ts",
            "anomalyOutcomeAggregation.ts",
            "anomalyOutcomeConfig.ts",
            "useAnomalyOutcomes.tsx",
        )
        if (SRC / "market" / f).is_file()
    )
    outcome_blob += (SRC / "components" / "AnomalyOutcomesPanel.tsx").read_text(
        encoding="utf-8", errors="replace"
    )

    rec = (SRC / "components" / "RecommendationBoard.tsx").read_text(
        encoding="utf-8", errors="replace"
    )
    if "useAnomalyOutcomes" in rec or "anomalyOutcome" in rec:
        issues.append("recommendation_outcome_coupling")

    for pat, name in FORBIDDEN:
        if re.search(pat, blob, re.I) and not re.search(
            rf"(no|never|forbidden|not|NOT).{{0,60}}{pat}", blob, re.I
        ):
            if name == "win_rate_claim" and "never" in blob.lower() and "win rate" in blob.lower():
                # allow negation phrases like "never \"win rate\""
                if re.search(r'never.*"win rate"|NOT.*win rate|not.*win rate', blob, re.I):
                    continue
            issues.append(f"forbidden:{name}")

    for pat, name in FORBIDDEN_IN_OUTCOME:
        if re.search(pat, outcome_blob, re.I) and not re.search(
            rf"(no|never|NOT|not).{{0,40}}{pat}", outcome_blob, re.I
        ):
            issues.append(f"forbidden_outcome:{name}")

    print("NEXUS UI MVP-22D Anomaly Outcome Research safety check")
    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("PASS: outcome tracking research-only; no trade/ARM/recommendation coupling")
    return 0


if __name__ == "__main__":
    sys.exit(main())
