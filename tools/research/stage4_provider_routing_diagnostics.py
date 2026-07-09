#!/usr/bin/env python3
"""Stage 4.18-O2 — offline provider routing / BTC-vs-ETH decision probe (no LLM, no soak)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_entry_failure_analyzer import _is_valid_watch_candidate  # noqa: E402
from tools.research.stage4_paper_readiness import apply_schema_level_enforcement  # noqa: E402

BTC_SYMBOL = "BTCUSDT"
ETH_SYMBOL = "ETHUSDT"
CONCENTRATION_THRESHOLD = 0.85


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


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _provider(raw: Dict[str, Any]) -> str:
    p = str(raw.get("provider") or raw.get("llm_provider") or "unknown").strip().lower()
    if p == "unknown" and raw.get("fallback_provider"):
        return str(raw.get("fallback_provider")).strip().lower()
    return p or "unknown"


def _intent_bucket(intent: str) -> str:
    i = intent.lower()
    if i == "watch":
        return "watch"
    if i == "enter_candidate":
        return "enter_candidate"
    if i in {"soft_skip", "soft-skip"}:
        return "soft_skip"
    if i in {"hard_skip", "hard-skip"}:
        return "hard_skip"
    return i or "unknown"


def _tick_key(raw: Dict[str, Any]) -> str:
    tick = raw.get("tick_index")
    if tick is not None:
        return str(tick)
    ts = raw.get("tick_timestamp_utc") or raw.get("generated_at_utc") or raw.get("timestamp_utc")
    if ts:
        return str(ts)[:16]
    return "unknown"


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _distribution(values: List[Any]) -> Dict[str, int]:
    return dict(Counter(str(v) for v in values))


def _provider_concentration(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "decision_count": 0,
            "dominant_provider": None,
            "dominant_share": 0.0,
            "provider_distribution": {},
        }
    dist = Counter(_provider(r) for r in rows)
    total = len(rows)
    dominant, count = dist.most_common(1)[0]
    return {
        "decision_count": total,
        "dominant_provider": dominant,
        "dominant_share": round(count / total, 4),
        "provider_distribution": dict(dist),
    }


def _confidence_by_provider(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_prov: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        by_prov[_provider(r)].append(_safe_float(r.get("confidence")))
    out: Dict[str, Any] = {}
    for prov, vals in sorted(by_prov.items()):
        out[prov] = {
            "count": len(vals),
            "avg": _avg(vals),
            "distribution": _distribution(f"{v:.2f}" for v in vals),
        }
    return out


def _mae_by_provider(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_prov: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        mae = _safe_float(r.get("mae_risk_estimate_pct"))
        if mae > 0:
            by_prov[_provider(r)].append(mae)
    return {
        prov: {"count": len(vals), "avg": _avg(vals)}
        for prov, vals in sorted(by_prov.items())
    }


def _directional_bias_by_provider(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    by_prov: Dict[str, List[str]] = defaultdict(list)
    for r in rows:
        by_prov[_provider(r)].append(str(r.get("directional_bias") or "NONE"))
    return {prov: _distribution(vals) for prov, vals in sorted(by_prov.items())}


def _infer_routing_asymmetry(
    *,
    provider_by_symbol: Dict[str, Dict[str, int]],
    valid_watch_by_provider: Dict[str, int],
    soft_skip_by_provider: Dict[str, int],
    fallback_reason_counts: Dict[str, int],
    btc_conc: Dict[str, Any],
    eth_conc: Dict[str, Any],
    btc_rows: List[Dict[str, Any]],
    eth_rows: List[Dict[str, Any]],
    all_rows: List[Dict[str, Any]],
) -> Tuple[bool, str, bool]:
    groq_vw = valid_watch_by_provider.get("groq", 0)
    cerebras_vw = valid_watch_by_provider.get("cerebras", 0)
    groq_skip = soft_skip_by_provider.get("groq", 0)
    groq_total = sum(1 for r in all_rows if _provider(r) == "groq")
    cerebras_total = sum(1 for r in all_rows if _provider(r) == "cerebras")

    btc_dom = btc_conc.get("dominant_provider")
    btc_share = float(btc_conc.get("dominant_share") or 0)
    eth_dom = eth_conc.get("dominant_provider")
    eth_vw_rows = [r for r in eth_rows if _is_valid_watch_candidate(r)]
    eth_vw_prov = Counter(_provider(r) for r in eth_vw_rows)

    asymmetry_parts: List[str] = []
    likely_affected_btc = False

    if btc_share >= CONCENTRATION_THRESHOLD and btc_dom == "groq":
        asymmetry_parts.append(f"BTC {btc_share:.0%} Groq concentration")
        likely_affected_btc = True

    if eth_vw_prov and eth_vw_prov.get("cerebras", 0) == len(eth_vw_rows) and len(eth_vw_rows) > 0:
        asymmetry_parts.append("ETH valid_watch exclusively Cerebras")

    if groq_vw == 0 and cerebras_vw > 0 and groq_total > 0:
        asymmetry_parts.append("all valid_watch from Cerebras; Groq produced zero valid_watch")
        likely_affected_btc = True

    if fallback_reason_counts:
        asymmetry_parts.append(
            f"fallback events present ({sum(fallback_reason_counts.values())} decisions)"
        )

    btc_groq_only = btc_dom == "groq" and btc_share >= 0.99
    eth_cerebras_any = provider_by_symbol.get(ETH_SYMBOL, {}).get("cerebras", 0) > 0
    if btc_groq_only and eth_cerebras_any and cerebras_vw > 0:
        asymmetry_parts.append("BTC never reached Cerebras while ETH did")
        likely_affected_btc = True

    groq_skip_rate = groq_skip / groq_total if groq_total else 0.0
    if groq_skip_rate >= 0.9 and groq_vw == 0:
        asymmetry_parts.append(f"Groq soft_skip rate {groq_skip_rate:.0%} with zero valid_watch")

    detected = len(asymmetry_parts) >= 2 or (
        btc_groq_only and cerebras_vw > 0 and groq_vw == 0
    )
    summary = "; ".join(asymmetry_parts) if asymmetry_parts else "no significant routing asymmetry"
    return detected, summary, likely_affected_btc


def _recommendation(
    *,
    routing_asymmetry_detected: bool,
    likely_affected_btc: bool,
    btc_rows: List[Dict[str, Any]],
    valid_watch_by_provider: Dict[str, int],
    soft_skip_by_provider: Dict[str, int],
) -> str:
    if not btc_rows:
        return "do_not_force_btc_watch"

    btc_all_skip = all(
        _intent_bucket(str(r.get("decision_intent") or "")) in {"soft_skip", "hard_skip"}
        for r in btc_rows
    )
    groq_vw = valid_watch_by_provider.get("groq", 0)
    cerebras_vw = valid_watch_by_provider.get("cerebras", 0)

    if routing_asymmetry_detected and likely_affected_btc:
        if groq_vw == 0 and cerebras_vw > 0:
            return "provider_routing_probe_recommended"
        return "cerebras_btc_probe_recommended"

    if btc_all_skip and groq_vw == 0 and not routing_asymmetry_detected:
        return "no_action_market_skip_correct"

    if routing_asymmetry_detected:
        return "provider_routing_probe_recommended"

    groq_skip = soft_skip_by_provider.get("groq", 0)
    if groq_skip > 0 and groq_vw == 0:
        return "groq_btc_prompt_probe_recommended"

    return "do_not_force_btc_watch"


def _o3_probe_design(recommended: bool) -> Optional[Dict[str, Any]]:
    if not recommended:
        return None
    return {
        "stage": "4.18-O3",
        "title": "Controlled provider A/B probe (design only — not executed)",
        "operator_approval_required": True,
        "constraints": [
            "same BTC market context snapshot",
            "offline one-shot read-only LLM probe",
            "compare Groq vs Cerebras BTC output side-by-side",
            "no orders",
            "no paper execution",
            "no automatic watch promotion",
            "output diagnostic JSON only",
        ],
        "inputs": ["frozen BTC context from N-R2 tick", "418-N prompt + schema"],
        "outputs": ["/data/stage4_18o3_btc_provider_probe"],
        "success_criteria": [
            "document intent distribution Groq vs Cerebras on identical context",
            "do not change trading logic or thresholds",
        ],
    }


def analyze_provider_routing_diagnostics(
    *,
    input_dir: str | Path,
    output_dir: str | Path | None = None,
) -> Dict[str, Any]:
    inp = Path(input_dir)
    decisions = _read_jsonl(inp / "ai_decisions.jsonl")
    enforced = [apply_schema_level_enforcement(d) for d in decisions if not d.get("parse_error")]

    provider_by_symbol: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    provider_by_tick: Dict[str, Dict[str, str]] = defaultdict(dict)
    provider_by_intent: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    valid_watch_by_provider: Counter[str] = Counter()
    soft_skip_by_provider: Counter[str] = Counter()
    fallback_reason_counts: Counter[str] = Counter()

    for raw in enforced:
        sym = str(raw.get("symbol") or "UNKNOWN").upper()
        prov = _provider(raw)
        intent = _intent_bucket(str(raw.get("decision_intent") or ""))
        tick = _tick_key(raw)

        provider_by_symbol[sym][prov] += 1
        provider_by_tick[tick][sym] = prov
        provider_by_intent[intent][prov] += 1

        if _is_valid_watch_candidate(raw):
            valid_watch_by_provider[prov] += 1
        if intent == "soft_skip":
            soft_skip_by_provider[prov] += 1

        if raw.get("fallback_used"):
            reason = str(raw.get("fallback_reason") or "unknown")
            fallback_reason_counts[reason] += 1

    btc_rows = [r for r in enforced if str(r.get("symbol") or "").upper() == BTC_SYMBOL]
    eth_rows = [r for r in enforced if str(r.get("symbol") or "").upper() == ETH_SYMBOL]

    btc_conc = _provider_concentration(btc_rows)
    eth_conc = _provider_concentration(eth_rows)

    asymmetry_detected, asymmetry_summary, likely_affected_btc = _infer_routing_asymmetry(
        provider_by_symbol={k: dict(v) for k, v in provider_by_symbol.items()},
        valid_watch_by_provider=dict(valid_watch_by_provider),
        soft_skip_by_provider=dict(soft_skip_by_provider),
        fallback_reason_counts=dict(fallback_reason_counts),
        btc_conc=btc_conc,
        eth_conc=eth_conc,
        btc_rows=btc_rows,
        eth_rows=eth_rows,
        all_rows=enforced,
    )

    rec = _recommendation(
        routing_asymmetry_detected=asymmetry_detected,
        likely_affected_btc=likely_affected_btc,
        btc_rows=btc_rows,
        valid_watch_by_provider=dict(valid_watch_by_provider),
        soft_skip_by_provider=dict(soft_skip_by_provider),
    )

    o3_recommended = rec in {
        "provider_routing_probe_recommended",
        "cerebras_btc_probe_recommended",
        "groq_btc_prompt_probe_recommended",
    }

    summary: Dict[str, Any] = {
        "record_type": "stage4_provider_routing_diagnostics",
        "stage_marker": "4.18-O2",
        "generated_at_utc": utc_now_iso(),
        "input_dir": str(inp),
        "decision_count": len(enforced),
        "provider_by_symbol": {k: dict(v) for k, v in sorted(provider_by_symbol.items())},
        "provider_by_tick": {k: dict(v) for k, v in sorted(provider_by_tick.items())},
        "provider_by_intent": {k: dict(v) for k, v in sorted(provider_by_intent.items())},
        "valid_watch_by_provider": dict(valid_watch_by_provider),
        "soft_skip_by_provider": dict(soft_skip_by_provider),
        "confidence_by_provider": _confidence_by_provider(enforced),
        "directional_bias_by_provider": _directional_bias_by_provider(enforced),
        "mae_by_provider": _mae_by_provider(enforced),
        "fallback_reason_counts": dict(fallback_reason_counts),
        "btc_provider_concentration": btc_conc,
        "eth_provider_concentration": eth_conc,
        "groq_cross_symbol_soft_skip_rate": round(
            soft_skip_by_provider.get("groq", 0)
            / max(1, sum(1 for r in enforced if _provider(r) == "groq")),
            4,
        ),
        "cerebras_cross_symbol_valid_watch_rate": round(
            valid_watch_by_provider.get("cerebras", 0)
            / max(1, sum(1 for r in enforced if _provider(r) == "cerebras")),
            4,
        ),
        "routing_asymmetry_detected": asymmetry_detected,
        "routing_asymmetry_summary": asymmetry_summary,
        "routing_asymmetry_likely_affected_btc": likely_affected_btc,
        "recommendation": rec,
        "o3_controlled_probe_design": _o3_probe_design(o3_recommended),
        "counterfactual_notes": {
            "btc_all_groq_eth_valid_watch_cerebras": (
                btc_conc.get("dominant_provider") == "groq"
                and valid_watch_by_provider.get("groq", 0) == 0
                and valid_watch_by_provider.get("cerebras", 0) > 0
            ),
            "groq_soft_skip_all_symbols": soft_skip_by_provider.get("groq", 0) > 0
            and valid_watch_by_provider.get("groq", 0) == 0,
            "cerebras_only_valid_watch_source": valid_watch_by_provider.get("cerebras", 0) > 0
            and valid_watch_by_provider.get("groq", 0) == 0,
            "btc_never_reached_cerebras": "cerebras" not in provider_by_symbol.get(BTC_SYMBOL, {}),
        },
        "offline_only": True,
        "llm_providers_called": False,
        "order_sent": False,
        "exchange_private_api_called": False,
        "production_touched": False,
        "btc_auto_touched": False,
    }

    out = Path(output_dir) if output_dir else inp / "stage4_18o2_provider_routing_diagnostics"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage4_provider_routing_diagnostics_summary.json", summary)
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-O2 provider routing diagnostics (offline)")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    summary = analyze_provider_routing_diagnostics(
        input_dir=args.input_dir,
        output_dir=args.output_dir or None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
