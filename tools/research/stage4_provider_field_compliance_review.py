#!/usr/bin/env python3
"""Stage 4.18-N — provider-specific structured field compliance review (offline, no orders)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_entry_failure_analyzer import (  # noqa: E402
    _bias_without_side,
    _field_contract_failures,
    _is_valid_watch_candidate,
    _missing_entry_trigger,
)
from tools.research.stage4_paper_readiness import (  # noqa: E402
    apply_schema_level_enforcement,
    detect_mae_scale_drift,
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


def _provider_label(raw: Dict[str, Any]) -> str:
    provider = str(raw.get("provider") or raw.get("llm_provider") or "unknown").strip().lower()
    if not provider or provider == "unknown":
        fb = str(raw.get("fallback_provider") or "").strip().lower()
        if fb:
            return fb
    return provider or "unknown"


def _rate(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round(num / den, 4)


def review_provider_field_compliance(
    *,
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    baseline_label: str = "",
) -> Dict[str, Any]:
    inp = Path(input_dir)
    decisions = _read_jsonl(inp / "ai_decisions.jsonl")
    enforced = [apply_schema_level_enforcement(d) for d in decisions if not d.get("parse_error")]

    by_provider: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in enforced:
        by_provider[_provider_label(row)].append(row)

    provider_stats: Dict[str, Any] = {}
    recommendations: List[str] = []

    for provider, rows in sorted(by_provider.items()):
        paper_rows = [
            r
            for r in rows
            if str(r.get("decision_intent") or "").lower() in {"watch", "enter_candidate"}
        ]
        side_missing = sum(1 for r in paper_rows if _bias_without_side(r))
        trigger_missing = sum(1 for r in paper_rows if _missing_entry_trigger(r))
        valid_watch = sum(1 for r in paper_rows if _is_valid_watch_candidate(r))
        drift = sum(1 for r in paper_rows if detect_mae_scale_drift(r))
        contract_totals = Counter()
        for r in paper_rows:
            for k, v in _field_contract_failures(r).items():
                contract_totals[k] += v

        den = len(paper_rows)
        provider_stats[provider] = {
            "decision_count": len(rows),
            "paper_intent_count": den,
            "side_missing_count": side_missing,
            "side_missing_rate": _rate(side_missing, den),
            "trigger_missing_count": trigger_missing,
            "trigger_missing_rate": _rate(trigger_missing, den),
            "valid_watch_candidate_count": valid_watch,
            "mae_scale_drift_suspected_count": drift,
            "field_contract_failure_totals": dict(contract_totals),
        }

    groq = provider_stats.get("groq", {})
    cerebras = provider_stats.get("cerebras", {})
    groq_side = float(groq.get("side_missing_rate") or 0)
    cerebras_side = float(cerebras.get("side_missing_rate") or 0)
    groq_trigger = float(groq.get("trigger_missing_rate") or 0)
    cerebras_trigger = float(cerebras.get("trigger_missing_rate") or 0)

    if groq_side > cerebras_side + 0.1:
        recommendations.append("groq_higher_side_missing → tighten Groq JSON schema / response_format")
    elif cerebras_side > groq_side + 0.1:
        recommendations.append("cerebras_higher_side_missing → tighten Cerebras json_schema payload")
    if groq_trigger > cerebras_trigger + 0.1:
        recommendations.append("groq_higher_trigger_missing → Groq-specific entry_trigger examples")
    elif cerebras_trigger > groq_trigger + 0.1:
        recommendations.append("cerebras_higher_trigger_missing → Cerebras-specific entry_trigger contract")
    if not recommendations:
        recommendations.append("providers_similar → apply unified schema repair with provider-specific probes")

    repair_policy = {
        "allowed_repairs": [
            "normalize_empty_object_containers",
            "coerce_string_trim",
            "fill_missing_nested_dict_shells",
        ],
        "forbidden_repairs": [
            "auto_set_candidate_side_from_bias",
            "deflate_mae_to_pass_cap",
            "synthesize_entry_trigger_to_pass",
            "promote_to_eligible_watchlist",
        ],
    }

    summary: Dict[str, Any] = {
        "record_type": "stage4_provider_field_compliance_review",
        "stage_marker": "4.18-N",
        "generated_at_utc": utc_now_iso(),
        "input_dir": str(inp),
        "baseline_label": baseline_label or inp.name,
        "decision_count": len(decisions),
        "provider_stats": provider_stats,
        "repair_policy": repair_policy,
        "recommendations": recommendations,
        "offline_only": True,
        "order_sent": False,
        "exchange_private_api_called": False,
    }

    out = Path(output_dir) if output_dir else inp / "stage4_provider_field_compliance_review"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage4_provider_field_compliance_summary.json", summary)
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-N provider field compliance review")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--baseline-label", default="")
    args = parser.parse_args()
    summary = review_provider_field_compliance(
        input_dir=args.input_dir,
        output_dir=args.output_dir or None,
        baseline_label=args.baseline_label,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
