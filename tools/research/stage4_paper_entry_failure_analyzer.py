#!/usr/bin/env python3
"""Stage 4.18-K — offline paper entry failure analyzer (no orders, no LLM)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_readiness import (  # noqa: E402
    apply_schema_level_enforcement,
    assess_decision_quality,
    build_enforcement_metrics,
)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def analyze_paper_entry_failures(
    *,
    input_dir: str | Path,
    output_dir: str | Path | None = None,
) -> Dict[str, Any]:
    inp = Path(input_dir)
    decisions = _read_jsonl(inp / "ai_decisions.jsonl")
    enforced = [apply_schema_level_enforcement(d) for d in decisions if not d.get("parse_error")]
    enforcement = build_enforcement_metrics(enforced)

    by_symbol: Counter[str] = Counter()
    by_block: Counter[str] = Counter()
    by_intent: Counter[str] = Counter()
    rows_out: List[Dict[str, Any]] = []

    for raw in enforced:
        intent = str(raw.get("decision_intent") or "").lower()
        if intent not in {"watch", "enter_candidate"}:
            continue
        symbol = str(raw.get("symbol") or "").upper()
        incomplete, paper_readiness, reasons = assess_decision_quality(raw)
        block = str(paper_readiness.get("block_reason") or "ok")
        by_symbol[symbol] += 1
        by_intent[intent] += 1
        if block != "ok":
            by_block[block] += 1
        rows_out.append(
            {
                "decision_id": raw.get("decision_id"),
                "tick_index": raw.get("tick_index"),
                "symbol": symbol,
                "decision_intent": intent,
                "candidate_side": raw.get("candidate_side"),
                "directional_bias": raw.get("directional_bias"),
                "mae_risk_estimate_pct": raw.get("mae_risk_estimate_pct"),
                "block_reason": block,
                "decision_quality_incomplete": incomplete,
                "directional_bias_without_candidate_side": raw.get(
                    "directional_bias_without_candidate_side"
                ),
                "paper_enforcement_reasons": reasons,
            }
        )

    summary: Dict[str, Any] = {
        "record_type": "stage4_paper_entry_failure_analysis",
        "generated_at_utc": utc_now_iso(),
        "input_dir": str(inp),
        "decision_count": len(decisions),
        "paper_intent_count": len(rows_out),
        "failure_by_block_reason": dict(by_block),
        "failure_by_symbol": dict(by_symbol),
        "failure_by_intent": dict(by_intent),
        **enforcement,
        "offline_only": True,
        "order_sent": False,
        "exchange_private_api_called": False,
    }

    out = Path(output_dir) if output_dir else inp / "stage4_paper_entry_failure_analysis"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage4_paper_entry_failure_summary.json", summary)
    with (out / "stage4_paper_entry_failure_rows.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows_out:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-K paper entry failure analyzer")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    summary = analyze_paper_entry_failures(
        input_dir=args.input_dir,
        output_dir=args.output_dir or None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
