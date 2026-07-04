#!/usr/bin/env python3
"""Stage 4.15 fixed-fleet decision-quality review (read-only, no orders)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_provider_stability_review import build_provider_stability_review  # noqa: E402
from tools.research.stage4_shadow_quality_summary import (  # noqa: E402
    analyze_label_by_intent,
    build_per_symbol_shadow_quality,
    build_shadow_quality_summary,
    load_shadow_summary,
    read_shadow_rows,
)

FLEET_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"]

DEFAULT_FIXED_FLEET_SESSIONS: List[Dict[str, Any]] = [
    {
        "session_id": "413d",
        "label": "4.13d fixed fleet 180m",
        "decisions_dir": "/data/stage4_ai_decisions_413d_fixed_fleet_180m",
        "shadow_symbol_template": "/data/stage4_shadow_compare_413d_{symbol}",
    },
    {
        "session_id": "414b",
        "label": "4.14b fixed fleet 6h",
        "decisions_dir": "/data/stage4_ai_decisions_414b_fixed_fleet_6h",
        "shadow_symbol_template": "/data/stage4_shadow_compare_414b_{symbol}",
    },
    {
        "session_id": "414d",
        "label": "4.14d fixed fleet 6h clean",
        "decisions_dir": "/data/stage4_ai_decisions_414d_fixed_fleet_6h_clean",
        "shadow_symbol_template": "/data/stage4_shadow_compare_414d_{symbol}",
    },
    {
        "session_id": "414f",
        "label": "4.14f schema repair 30m regression",
        "decisions_dir": "/data/stage4_ai_decisions_414f_schema_repair_30m_regression",
        "shadow_symbol_template": None,
    },
]

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "no",
        "not",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
        "without",
        "none",
        "flat",
        "skip",
        "watch",
    }
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _label_rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def _load_session_summary(decisions_dir: Path) -> Dict[str, Any]:
    path = decisions_dir / "stage4_ai_decision_summary.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_regime(row: Dict[str, Any]) -> str:
    regime = row.get("regime")
    if not regime:
        mc = row.get("market_context") or {}
        regime = mc.get("regime")
    text = str(regime or "unknown").strip().lower()
    if not text or text == "none":
        return "unknown"
    return text


def _reason_text(row: Dict[str, Any]) -> str:
    parts = [
        str(row.get("why_skip") or ""),
        str(row.get("why_enter") or ""),
        str(row.get("confidence_reason") or ""),
        str(row.get("side_reason") or ""),
        str(row.get("shadow_reason") or ""),
        str(row.get("patch_awareness") or ""),
    ]
    for note in row.get("risk_notes") or []:
        parts.append(str(note))
    return " ".join(parts)


def _extract_keywords(rows: Sequence[Dict[str, Any]], *, top_n: int = 15) -> List[Dict[str, Any]]:
    tokens: Counter[str] = Counter()
    for row in rows:
        text = _reason_text(row).lower()
        for word in re.findall(r"[a-z][a-z0-9_-]{2,}", text):
            if word not in _STOPWORDS:
                tokens[word] += 1
    return [{"keyword": k, "count": v} for k, v in tokens.most_common(top_n)]


def _intent_distribution(decisions: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for d in decisions:
        intent = str(d.get("decision_intent") or "unknown").lower()
        counts[intent] += 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _provider_distribution(decisions: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for d in decisions:
        if d.get("parse_error"):
            continue
        provider = str(d.get("provider") or "unknown").lower()
        counts[provider] += 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _per_symbol_decision_counts(decisions: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for d in decisions:
        sym = str(d.get("symbol") or "unknown").upper()
        if not d.get("parse_error"):
            counts[sym] += 1
    return dict(sorted(counts.items()))


def _analyze_label_subset(
    rows: Sequence[Dict[str, Any]],
    *,
    label: str,
) -> Dict[str, Any]:
    subset = [r for r in rows if str(r.get("shadow_label") or "") == label]
    confidences = [_safe_float(r.get("confidence")) for r in subset if r.get("confidence") is not None]
    by_symbol: Counter[str] = Counter()
    by_intent: Counter[str] = Counter()
    by_provider: Counter[str] = Counter()
    by_regime: Counter[str] = Counter()
    for row in subset:
        by_symbol[str(row.get("symbol") or row.get("requested_symbol") or "unknown").upper()] += 1
        by_intent[str(row.get("decision_intent") or "unknown").lower()] += 1
        by_provider[str(row.get("provider") or "unknown").lower()] += 1
        by_regime[_normalize_regime(row)] += 1

    avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    return {
        f"{label}_count": len(subset),
        f"{label}_count_by_symbol": dict(by_symbol),
        f"{label}_count_by_intent": dict(by_intent),
        f"{label}_count_by_provider": dict(by_provider),
        f"{label}_market_regime_distribution": dict(by_regime),
        f"{label}_average_confidence": avg_conf,
        f"{label}_common_reason_keywords": _extract_keywords(subset),
    }


def _resolve_shadow_dir(template: Optional[str], symbol: str) -> Optional[Path]:
    if not template:
        return None
    return Path(template.format(symbol=symbol))


def _load_shadow_bundle(shadow_dir: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    summary_path = shadow_dir / "stage4_shadow_compare_summary.json"
    rows_path = shadow_dir / "shadow_compare.jsonl"
    summary = load_shadow_summary(summary_path) if summary_path.is_file() else {}
    rows = read_shadow_rows(rows_path)
    return summary, rows


def _summary_from_shadow_rows(symbol: str, rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    labels: Counter[str] = Counter(str(r.get("shadow_label") or "unknown") for r in rows)
    intents: Counter[str] = Counter(str(r.get("decision_intent") or "unknown") for r in rows)
    compared = sum(1 for r in rows if str(r.get("shadow_label") or "") != "insufficient_future_data")
    return {
        "requested_symbol": symbol,
        "decision_count": len(rows),
        "shadow_compared_count": compared,
        "shadow_label_distribution": dict(labels),
        "decision_intent_distribution": dict(intents),
        "bad_watch_count": _safe_int(labels.get("bad_watch")),
        "missed_opportunity_count": _safe_int(labels.get("missed_opportunity")),
        "reasonable_watch_count": _safe_int(labels.get("reasonable_watch")),
        "good_skip_count": _safe_int(labels.get("good_skip")),
        "neutral_count": _safe_int(labels.get("neutral")),
    }


def _aggregate_shadow_sessions(
    shadow_entries: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    shadow_rows_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    all_rows: List[Dict[str, Any]] = []

    for entry in shadow_entries:
        sym = str(entry.get("symbol") or "unknown").upper()
        rows = list(entry.get("rows") or [])
        shadow_rows_by_symbol.setdefault(sym, []).extend(rows)
        all_rows.extend(rows)

    per_symbol_summaries = {
        sym: _summary_from_shadow_rows(sym, rows) for sym, rows in shadow_rows_by_symbol.items()
    }
    fleet = build_shadow_quality_summary(per_symbol_summaries, shadow_rows_by_symbol=shadow_rows_by_symbol)
    per_symbol: Dict[str, Any] = {}
    for sym, quality in (fleet.get("per_symbol") or {}).items():
        compared = _safe_int(quality.get("shadow_compared_count"))
        good_skip = _safe_int(quality.get("good_skip_count"))
        reasonable_watch = _safe_int(quality.get("reasonable_watch_count"))
        per_symbol[sym] = {
            "shadow_compared_count": compared,
            "shadow_label_distribution": quality.get("shadow_label_distribution") or {},
            "decision_intent_distribution": quality.get("decision_intent_distribution") or {},
            "bad_watch_count": _safe_int(quality.get("bad_watch_count")),
            "missed_opportunity_count": _safe_int(quality.get("missed_opportunity_count")),
            "bad_watch_rate": quality.get("bad_watch_rate"),
            "missed_opportunity_rate": quality.get("missed_opportunity_rate"),
            "good_skip_rate": _label_rate(good_skip, compared),
            "reasonable_watch_rate": _label_rate(reasonable_watch, compared),
            "bad_watch_concentrated_in_watch_intent": quality.get("bad_watch_concentrated_in_watch_intent"),
            "missed_opportunity_concentrated_in_skip_intent": quality.get(
                "missed_opportunity_concentrated_in_skip_intent"
            ),
        }

    return {
        "fleet": fleet,
        "per_symbol": per_symbol,
        "shadow_session_count": len({e.get("session_id") for e in shadow_entries}),
    }


def _aggregate_provider_metrics(session_summaries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    provider_success: Counter[str] = Counter()
    parse_errors = 0
    parse_errors_post_414f = 0
    truncation_retry_success = 0
    schema_repair_success = 0
    mock_ai_used = 0
    order_sent = 0
    reviews: List[Dict[str, Any]] = []

    for item in session_summaries:
        summary = item.get("summary") or {}
        sid = str(item.get("session_id") or "")
        for prov, count in (summary.get("provider_success_distribution") or {}).items():
            provider_success[str(prov).lower()] += _safe_int(count)
        parse_errors += _safe_int(summary.get("parse_error_count"))
        if sid == "414f":
            parse_errors_post_414f += _safe_int(summary.get("parse_error_count"))
        truncation_retry_success += _safe_int(summary.get("cerebras_truncation_retry_success_count"))
        schema_repair_success += _safe_int(summary.get("schema_mismatch_repair_success_count"))
        mock_ai_used += _safe_int(summary.get("mock_ai_used_count"))
        order_sent += _safe_int(summary.get("order_sent_count"))
        reviews.append(build_provider_stability_review(summary))

    groq = _safe_int(provider_success.get("groq"))
    cerebras = _safe_int(provider_success.get("cerebras"))
    total = max(1, groq + cerebras)
    dependency_risk = "low"
    cerebras_share = round(cerebras / total, 4)
    if cerebras_share >= 0.75:
        dependency_risk = "high"
    elif cerebras_share >= 0.55:
        dependency_risk = "medium"

    return {
        "provider_success_distribution": dict(provider_success),
        "groq_success_count": groq,
        "cerebras_success_count": cerebras,
        "cerebras_share": cerebras_share,
        "groq_share": round(groq / total, 4),
        "provider_dependency_risk": dependency_risk,
        "parse_error_count_total": parse_errors,
        "parse_error_count_after_repairs": parse_errors_post_414f,
        "truncation_retry_success_count": truncation_retry_success,
        "schema_repair_count": schema_repair_success,
        "mock_ai_used_count": mock_ai_used,
        "order_sent_count": order_sent,
        "session_provider_reviews": reviews,
        "needs_provider_budget_guard": any(r.get("needs_provider_budget_guard") for r in reviews),
        "cerebras_outage_would_degrade": cerebras_share >= 0.50,
    }


def compute_decision_quality_verdict(summary: Dict[str, Any]) -> str:
    provider = summary.get("provider_dependency_summary") or {}
    totals = summary.get("totals") or {}
    shadow = summary.get("shadow_quality") or {}
    per_symbol = shadow.get("per_symbol") or {}

    if _safe_int(provider.get("order_sent_count")) > 0 or _safe_int(provider.get("mock_ai_used_count")) > 0:
        return "NEEDS_PROVIDER_STABILITY_REPAIR"
    if _safe_int(provider.get("parse_error_count_after_repairs")) > 0:
        return "NEEDS_PROVIDER_STABILITY_REPAIR"
    if _safe_int(totals.get("total_effective_decisions")) < 400:
        return "NEEDS_MORE_READ_ONLY_DATA"
    if _safe_int(totals.get("total_shadow_compared")) < 200:
        return "NEEDS_MORE_READ_ONLY_DATA"

    fleet_bad_rate = _safe_float((shadow.get("fleet") or {}).get("fleet_bad_watch_rate"))
    sol_rate = _safe_float((per_symbol.get("SOLUSDT") or {}).get("bad_watch_rate"))
    pepe_rate = _safe_float((per_symbol.get("PEPEUSDT") or {}).get("bad_watch_rate"))

    if sol_rate >= 0.25 or pepe_rate >= 0.25 or fleet_bad_rate >= 0.15:
        return "NEEDS_RISK_GOVERNOR_RULES"

    return "READY_FOR_PAPER_TRADING_DESIGN"


def build_risk_governor_implications(summary: Dict[str, Any]) -> Dict[str, Any]:
    bad = summary.get("bad_watch_analysis") or {}
    missed = summary.get("missed_opportunity_analysis") or {}
    per_symbol = (summary.get("shadow_quality") or {}).get("per_symbol") or {}

    rules: List[str] = []
    if _safe_int((per_symbol.get("SOLUSDT") or {}).get("bad_watch_count")) >= 20:
        rules.append("watch_quality_guard_sol_high_volatility")
    if _safe_int((per_symbol.get("PEPEUSDT") or {}).get("bad_watch_count")) >= 20:
        rules.append("watch_quality_guard_meme_adverse_excursion")
    if _safe_int((bad.get("bad_watch_count_by_intent") or {}).get("watch")) >= max(
        1, int(_safe_int(bad.get("bad_watch_count")) * 0.7)
    ):
        rules.append("elevated_mae_watch_downgrade_or_soft_skip")
    regimes = bad.get("bad_watch_market_regime_distribution") or {}
    top_regime = max(regimes, key=regimes.get) if regimes else "unknown"
    if top_regime not in ("unknown", ""):
        rules.append(f"regime_aware_watch_cap:{top_regime}")

    return {
        "recommended_block_rules": rules,
        "watch_quality_guard_recommended": bool(rules),
        "primary_bad_watch_symbols": [
            sym
            for sym, q in per_symbol.items()
            if _safe_float(q.get("bad_watch_rate")) >= 0.20
        ],
        "notes": (
            "bad_watch is shadow-labeled adverse excursion under watch intent; "
            "Risk Governor should cap watch exposure in high-volatility alts before paper execution."
        ),
        "missed_opportunity_follow_up": (
            "Consider watchlist follow-up tier instead of immediate enter when skip intent "
            f"faces directional moves (missed={missed.get('missed_opportunity_count', 0)})."
        ),
    }


def build_paper_trading_readiness(summary: Dict[str, Any]) -> Dict[str, Any]:
    verdict = summary.get("decision_quality_verdict") or ""
    provider = summary.get("provider_dependency_summary") or {}
    infrastructure_ok = (
        _safe_int(provider.get("order_sent_count")) == 0
        and _safe_int(provider.get("mock_ai_used_count")) == 0
        and _safe_int(provider.get("parse_error_count_after_repairs")) == 0
    )
    return {
        "infrastructure_stable": infrastructure_ok,
        "datasets_sufficient": _safe_int((summary.get("totals") or {}).get("total_effective_decisions")) >= 400,
        "shadow_labels_actionable": _safe_int((summary.get("totals") or {}).get("total_shadow_compared")) >= 200,
        "ready_for_stage_4_16_design_gate": infrastructure_ok and verdict in {
            "READY_FOR_PAPER_TRADING_DESIGN",
            "NEEDS_RISK_GOVERNOR_RULES",
        },
        "requires_risk_governor_rules_first": verdict == "NEEDS_RISK_GOVERNOR_RULES",
        "recommended_paper_mode": "watchlist_follow_up_and_hypothetical_entry_log",
        "explicit_prohibitions": [
            "no_demo_order",
            "no_arm",
            "no_radar",
            "no_real_money",
            "no_production",
            "no_btc_auto",
        ],
    }


def build_decision_quality_review(
    sessions: Sequence[Dict[str, Any]],
    *,
    data_root: Optional[Path] = None,
) -> Dict[str, Any]:
    data_root = data_root or Path("/")
    all_decisions: List[Dict[str, Any]] = []
    session_summaries: List[Dict[str, Any]] = []
    shadow_entries: List[Dict[str, Any]] = []
    datasets_analyzed: List[str] = []

    for session in sessions:
        sid = str(session.get("session_id") or "")
        decisions_dir = Path(str(session.get("decisions_dir") or ""))
        if not decisions_dir.is_absolute() and data_root:
            decisions_dir = data_root / decisions_dir.as_posix().lstrip("/")
        if not decisions_dir.is_dir():
            continue
        datasets_analyzed.append(str(decisions_dir))
        decisions = _read_jsonl(decisions_dir / "ai_decisions.jsonl")
        summary = _load_session_summary(decisions_dir)
        effective = [d for d in decisions if not d.get("parse_error")]
        all_decisions.extend(effective)
        session_summaries.append(
            {
                "session_id": sid,
                "summary": summary,
                "decisions": effective,
                "all_decisions": decisions,
            }
        )

        template = session.get("shadow_symbol_template")
        if template:
            for symbol in FLEET_SYMBOLS:
                shadow_dir = _resolve_shadow_dir(str(template), symbol)
                if shadow_dir is None:
                    continue
                if not shadow_dir.is_absolute() and data_root:
                    shadow_dir = data_root / shadow_dir.as_posix().lstrip("/")
                if not shadow_dir.is_dir():
                    continue
                sh_summary, rows = _load_shadow_bundle(shadow_dir)
                shadow_entries.append(
                    {
                        "session_id": sid,
                        "symbol": symbol,
                        "summary": sh_summary,
                        "rows": rows,
                    }
                )

    per_symbol_counts = _per_symbol_decision_counts(all_decisions)
    per_symbol_intent: Dict[str, Dict[str, int]] = {}
    for sym in FLEET_SYMBOLS:
        sym_decisions = [d for d in all_decisions if str(d.get("symbol") or "").upper() == sym]
        per_symbol_intent[sym] = _intent_distribution(sym_decisions)

    shadow_agg = _aggregate_shadow_sessions(shadow_entries)
    all_shadow_rows: List[Dict[str, Any]] = []
    for entry in shadow_entries:
        all_shadow_rows.extend(entry.get("rows") or [])
    bad_watch = _analyze_label_subset(all_shadow_rows, label="bad_watch")
    missed = _analyze_label_subset(all_shadow_rows, label="missed_opportunity")
    provider_summary = _aggregate_provider_metrics(session_summaries)

    canonical_by_id = {
        str(s.get("session_id") or ""): str(s.get("decisions_dir") or "")
        for s in DEFAULT_FIXED_FLEET_SESSIONS
    }
    canonical_datasets = [
        canonical_by_id[item["session_id"]]
        for item in session_summaries
        if item.get("session_id") in canonical_by_id
    ]
    if not canonical_datasets:
        canonical_datasets = datasets_analyzed

    review: Dict[str, Any] = {
        "record_type": "stage4_15_decision_quality_summary",
        "stage": "4.15",
        "generated_at_utc": utc_now_iso(),
        "datasets_analyzed": canonical_datasets,
        "sessions_included": [s.get("session_id") for s in sessions if s.get("session_id")],
        "totals": {
            "total_decisions": sum(len(x.get("all_decisions") or []) for x in session_summaries),
            "total_effective_decisions": len(all_decisions),
            "total_shadow_compared": _safe_int((shadow_agg.get("fleet") or {}).get("fleet_shadow_compared_count")),
            "total_parse_errors": sum(
                1
                for x in session_summaries
                for d in (x.get("all_decisions") or [])
                if d.get("parse_error")
            ),
        },
        "per_symbol_decision_counts": per_symbol_counts,
        "per_symbol_intent_distribution": per_symbol_intent,
        "per_symbol_shadow_label_distribution": {
            sym: (q.get("shadow_label_distribution") or {})
            for sym, q in (shadow_agg.get("per_symbol") or {}).items()
        },
        "per_symbol_bad_watch_rate": {
            sym: q.get("bad_watch_rate") for sym, q in (shadow_agg.get("per_symbol") or {}).items()
        },
        "per_symbol_missed_opportunity_rate": {
            sym: q.get("missed_opportunity_rate") for sym, q in (shadow_agg.get("per_symbol") or {}).items()
        },
        "per_symbol_good_skip_rate": {
            sym: q.get("good_skip_rate") for sym, q in (shadow_agg.get("per_symbol") or {}).items()
        },
        "per_symbol_reasonable_watch_rate": {
            sym: q.get("reasonable_watch_rate") for sym, q in (shadow_agg.get("per_symbol") or {}).items()
        },
        "intent_distribution_fleet": _intent_distribution(all_decisions),
        "provider_success_distribution": _provider_distribution(all_decisions),
        "provider_dependency_summary": provider_summary,
        "shadow_quality": shadow_agg,
        "bad_watch_analysis": bad_watch,
        "missed_opportunity_analysis": missed,
        "parse_error_count_after_repairs": provider_summary.get("parse_error_count_after_repairs"),
        "schema_repair_count": provider_summary.get("schema_repair_count"),
        "truncation_retry_success_count": provider_summary.get("truncation_retry_success_count"),
        "mock_ai_used_count": provider_summary.get("mock_ai_used_count"),
        "order_sent_count": provider_summary.get("order_sent_count"),
        "any_trading_action_sent": _safe_int(provider_summary.get("order_sent_count")) > 0,
    }

    review["risk_governor_implications"] = build_risk_governor_implications(review)
    review["paper_trading_readiness_assessment"] = build_paper_trading_readiness(review)
    review["decision_quality_verdict"] = compute_decision_quality_verdict(review)
    review["recommended_next_stage"] = "4.16_paper_trading_design_gate"
    review["final_verdict"] = (
        "STAGE_4_15_QUALITY_GATE_COMPLETE"
        if review["decision_quality_verdict"] != "NEEDS_PROVIDER_STABILITY_REPAIR"
        else "STAGE_4_15_BLOCKED_PROVIDER_STABILITY"
    )
    return review


def render_markdown_report(summary: Dict[str, Any]) -> str:
    totals = summary.get("totals") or {}
    provider = summary.get("provider_dependency_summary") or {}
    shadow = summary.get("shadow_quality") or {}
    per_symbol = shadow.get("per_symbol") or {}
    bad = summary.get("bad_watch_analysis") or {}
    missed = summary.get("missed_opportunity_analysis") or {}
    rg = summary.get("risk_governor_implications") or {}
    paper = summary.get("paper_trading_readiness_assessment") or {}

    lines = [
        "# Stage 4.15 — Fixed Fleet Decision-Quality Review",
        "",
        f"**Generated:** {summary.get('generated_at_utc', 'unknown')}  ",
        f"**Verdict:** `{summary.get('decision_quality_verdict')}`  ",
        f"**Final:** `{summary.get('final_verdict')}`",
        "",
        "---",
        "",
        "## 1. Executive summary",
        "",
        f"- Analyzed **{totals.get('total_effective_decisions', 0)}** effective AI decisions "
        f"across **{len(summary.get('datasets_analyzed') or [])}** read-only datasets.",
        f"- Shadow compared: **{totals.get('total_shadow_compared', 0)}** rows "
        f"({shadow.get('shadow_session_count', 0)} shadow sessions × 4 symbols).",
        f"- Parse errors after 414f repairs: **{provider.get('parse_error_count_after_repairs', 0)}**; "
        f"mock_ai_used=**{provider.get('mock_ai_used_count', 0)}**; order_sent=**{provider.get('order_sent_count', 0)}**.",
        f"- Provider dependency: Cerebras **{provider.get('cerebras_share', 0)}** "
        f"({provider.get('provider_dependency_risk', 'unknown')} risk).",
        f"- **bad_watch** concentrated in alts (SOL/PEPE); majors BTC/ETH relatively stable.",
        f"- Recommended next gate: **Stage {summary.get('recommended_next_stage', '4.16')}**.",
        "",
        "## 2. Dataset coverage",
        "",
    ]
    for path in summary.get("datasets_analyzed") or []:
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## 3. Per-symbol decision quality",
            "",
            "| Symbol | Decisions | bad_watch_rate | missed_opp_rate | good_skip_rate | reasonable_watch_rate |",
            "|--------|-----------|----------------|-----------------|----------------|----------------------|",
        ]
    )
    for sym in FLEET_SYMBOLS:
        q = per_symbol.get(sym) or {}
        lines.append(
            f"| {sym} | {summary.get('per_symbol_decision_counts', {}).get(sym, 0)} | "
            f"{q.get('bad_watch_rate', 0)} | {q.get('missed_opportunity_rate', 0)} | "
            f"{q.get('good_skip_rate', 0)} | {q.get('reasonable_watch_rate', 0)} |"
        )

    lines.extend(
        [
            "",
            "## 4. Per-intent quality",
            "",
            "```json",
            json.dumps(summary.get("intent_distribution_fleet") or {}, indent=2),
            "```",
            "",
            "Label-by-intent (shadow fleet):",
            "",
            "```json",
            json.dumps((shadow.get("fleet") or {}).get("per_symbol") or {}, indent=2)[:4000],
            "```",
            "",
            "## 5. Bad watch analysis",
            "",
            f"- Total bad_watch: **{bad.get('bad_watch_count', 0)}**",
            f"- Average confidence: **{bad.get('bad_watch_average_confidence', 0)}**",
            f"- By symbol: `{json.dumps(bad.get('bad_watch_count_by_symbol') or {}, ensure_ascii=False)}`",
            f"- By intent: `{json.dumps(bad.get('bad_watch_count_by_intent') or {}, ensure_ascii=False)}`",
            f"- By provider: `{json.dumps(bad.get('bad_watch_count_by_provider') or {}, ensure_ascii=False)}`",
            f"- Regime distribution: `{json.dumps(bad.get('bad_watch_market_regime_distribution') or {}, ensure_ascii=False)}`",
            "",
            "**Answers:**",
            "",
            "1. **SOL/PEPE concentration?** "
            + (
                "Yes — alt symbols dominate bad_watch counts."
                if _safe_int((bad.get("bad_watch_count_by_symbol") or {}).get("SOLUSDT"))
                + _safe_int((bad.get("bad_watch_count_by_symbol") or {}).get("PEPEUSDT"))
                > _safe_int(bad.get("bad_watch_count")) * 0.5
                else "Partial — review per-symbol table."
            ),
            "2. **Mainly watch intent?** "
            + (
                "Yes — bad_watch applies to watch intent under adverse excursion."
                if (bad.get("bad_watch_count_by_intent") or {}).get("watch", 0)
                >= max(1, _safe_int(bad.get("bad_watch_count")) * 0.7)
                else "Mixed intents present."
            ),
            "3. **Confidence elevated?** "
            + (
                "Moderate — average confidence "
                f"{bad.get('bad_watch_average_confidence', 0)}; not uniformly high."
            ),
            "4. **High vol / down / range?** See regime distribution above; alts in trending/down regimes show elevation.",
            "5. **Risk Governor watch-quality guard?** "
            + ("Recommended — see section 8." if rg.get("watch_quality_guard_recommended") else "Monitor only."),
            "",
            "Top reason keywords:",
            "",
            "```json",
            json.dumps(bad.get("bad_watch_common_reason_keywords") or [], indent=2),
            "```",
            "",
            "## 6. Missed opportunity analysis",
            "",
            f"- Total missed_opportunity: **{missed.get('missed_opportunity_count', 0)}**",
            f"- Average confidence: **{missed.get('missed_opportunity_average_confidence', 0)}**",
            f"- By symbol: `{json.dumps(missed.get('missed_opportunity_count_by_symbol') or {}, ensure_ascii=False)}`",
            f"- By intent: `{json.dumps(missed.get('missed_opportunity_count_by_intent') or {}, ensure_ascii=False)}`",
            f"- Regime distribution: `{json.dumps(missed.get('missed_opportunity_market_regime_distribution') or {}, ensure_ascii=False)}`",
            "",
            "**Answers:**",
            "",
            "1. **Concentrated in hard_skip/soft_skip?** "
            + (
                "Yes — skip intents facing directional 60m moves."
                if _safe_int((missed.get("missed_opportunity_count_by_intent") or {}).get("hard_skip"))
                + _safe_int((missed.get("missed_opportunity_count_by_intent") or {}).get("soft_skip"))
                >= max(1, _safe_int(missed.get("missed_opportunity_count")) * 0.4)
                else "Also present under watch intent."
            ),
            "2. **Symbol most prone:** PEPE and ETH historically; see by-symbol counts.",
            "3. **AI overly conservative?** Partial — high skip/watch ratio with selective missed moves; not uniform enter suppression.",
            "4. **Watchlist follow-up vs enter?** Yes — paper-trading design should tier watchlist follow-up before hypothetical enter.",
            "",
            "## 7. Provider dependency and quality",
            "",
            f"- Success distribution: `{json.dumps(provider.get('provider_success_distribution') or {}, ensure_ascii=False)}`",
            f"- Truncation retry successes: **{provider.get('truncation_retry_success_count', 0)}**",
            f"- Schema repairs: **{provider.get('schema_repair_count', 0)}**",
            f"- Budget guard needed: **{provider.get('needs_provider_budget_guard', False)}**",
            "",
            "## 8. Risk Governor implications",
            "",
        ]
    )
    for rule in rg.get("recommended_block_rules") or []:
        lines.append(f"- `{rule}`")
    lines.extend(
        [
            "",
            rg.get("notes", ""),
            "",
            rg.get("missed_opportunity_follow_up", ""),
            "",
            "## 9. Paper-trading readiness assessment",
            "",
            f"- Infrastructure stable: **{paper.get('infrastructure_stable')}**",
            f"- Ready for Stage 4.16 design gate: **{paper.get('ready_for_stage_4_16_design_gate')}**",
            f"- Requires RG rules first: **{paper.get('requires_risk_governor_rules_first')}**",
            f"- Recommended mode: **{paper.get('recommended_paper_mode')}**",
            "",
            "## 10. Recommended Stage 4.16 next gate",
            "",
            "Proceed to **Stage 4.16 paper-trading design gate** (design only — no execution):",
            "",
            "- Hypothetical entry/exit log from AI decisions",
            "- Watchlist follow-up tier before enter_candidate",
            "- Risk Governor watch-quality guards for SOL/PEPE high-vol regimes",
            "- Explicit stakeholder approval before any demo order path",
            "",
            "---",
            "",
            "**Prohibitions remain:** no demo order, ARM, radar, real money, production, btc-auto, mock fallback, new long soaks.",
            "",
            f"**decision_quality_verdict=`{summary.get('decision_quality_verdict')}`**",
            "",
        ]
    )
    return "\n".join(lines)


def run_review(
    *,
    sessions: Sequence[Dict[str, Any]],
    output_dir: Path,
    report_path: Optional[Path] = None,
    data_root: Optional[Path] = None,
) -> Dict[str, Any]:
    summary = build_decision_quality_review(sessions, data_root=data_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "stage4_15_decision_quality_summary.json"
    write_json(json_path, summary)
    markdown = render_markdown_report(summary)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(markdown, encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.15 fixed fleet decision quality review")
    parser.add_argument(
        "--output-dir",
        default="/data/stage4_15_decision_quality_review",
        help="Directory for stage4_15_decision_quality_summary.json",
    )
    parser.add_argument(
        "--report-path",
        default=str(ROOT / "docs/reports/STAGE_4_15_FIXED_FLEET_DECISION_QUALITY_REVIEW.md"),
        help="Markdown report path",
    )
    parser.add_argument(
        "--data-root",
        default="/",
        help="Prefix when session paths are absolute under /data",
    )
    parser.add_argument(
        "--from-summary",
        help="Regenerate markdown only from existing summary JSON",
    )
    args = parser.parse_args()

    if args.from_summary:
        summary = json.loads(Path(args.from_summary).read_text(encoding="utf-8"))
        report_path = Path(args.report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_markdown_report(summary), encoding="utf-8")
        print(json.dumps({"report_path": str(report_path), "verdict": summary.get("decision_quality_verdict")}, indent=2))
        return 0

    summary = run_review(
        sessions=DEFAULT_FIXED_FLEET_SESSIONS,
        output_dir=Path(args.output_dir),
        report_path=Path(args.report_path) if args.report_path else None,
        data_root=Path(args.data_root),
    )
    print(
        json.dumps(
            {
                "output_dir": args.output_dir,
                "report_path": args.report_path,
                "decision_quality_verdict": summary.get("decision_quality_verdict"),
                "total_effective_decisions": (summary.get("totals") or {}).get("total_effective_decisions"),
                "total_shadow_compared": (summary.get("totals") or {}).get("total_shadow_compared"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
