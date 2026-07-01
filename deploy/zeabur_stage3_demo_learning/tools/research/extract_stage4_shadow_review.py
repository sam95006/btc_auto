#!/usr/bin/env python3
"""Generate Stage 4.12c shadow quality review sections from shadow_compare.jsonl."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_shadow_review_rows(rows: List[Dict[str, Any]], *, labels: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("shadow_label") or "") not in labels:
            continue
        out.append(
            {
                "timestamp": row.get("timestamp_utc"),
                "tick_index": row.get("tick_index"),
                "decision_id": row.get("decision_id"),
                "symbol": row.get("symbol"),
                "decision_intent": row.get("decision_intent"),
                "confidence": row.get("confidence"),
                "regime": row.get("regime"),
                "shadow_reason": row.get("shadow_reason"),
                "future_return_15m": row.get("return_15m_pct"),
                "future_return_30m": row.get("return_30m_pct"),
                "future_return_60m": row.get("return_60m_pct"),
                "MFE_60m": row.get("mfe_60m_pct"),
                "MAE_60m": row.get("mae_60m_pct"),
                "patch_awareness_detected": row.get("patch_awareness_detected"),
                "reflection_awareness_detected": row.get("reflection_awareness_detected"),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shadow-jsonl", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = _read_jsonl(Path(args.shadow_jsonl))
    report = {
        "bad_watch": build_shadow_review_rows(rows, labels=["bad_watch"]),
        "missed_opportunity": build_shadow_review_rows(rows, labels=["missed_opportunity"]),
        "good_skip": build_shadow_review_rows(rows, labels=["good_skip"]),
        "reasonable_watch": build_shadow_review_rows(rows, labels=["reasonable_watch"]),
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"bad_watch_count": len(report["bad_watch"]), "missed_opportunity_count": len(report["missed_opportunity"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
