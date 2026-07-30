#!/usr/bin/env python3
"""Offline analyzer for NEXUS Demo Validation session exports.

Does NOT talk to Zeabur containers. Input is an export directory or ZIP only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import zipfile
from pathlib import Path
from typing import Any


UNAVAILABLE = "UNAVAILABLE"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
NOT_YET_OBSERVABLE = "NOT_YET_OBSERVABLE"
NOT_PROVEN = "NOT_PROVEN"
PRELIMINARY_EVIDENCE = "PRELIMINARY_EVIDENCE"

ACCEPTABLE_DECISION_DELTAS = frozenset(
    {
        "ALLOW→REQUIRE_EXTRA_CONFIRMATION",
        "ALLOW→BLOCK_COST_DOMINATED_SETUP",
        "ALLOW→EXACT_SETUP_COOLDOWN",
        "CANDIDATE_SCORE_LOWERED",
        "MARGIN_PROPOSAL_BLOCKED",
        "STRATEGY_CONFIRMATION_INCREASED",
    }
)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def resolve_input(input_path: Path) -> Path:
    if input_path.is_dir():
        return input_path
    if input_path.suffix.lower() == ".zip":
        extract_dir = input_path.with_suffix("") / "_extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(input_path, "r") as zf:
            zf.extractall(extract_dir)
        return extract_dir
    raise FileNotFoundError(f"input must be directory or zip: {input_path}")


def _safe_num(v: Any) -> float | str:
    if v is None:
        return UNAVAILABLE
    if isinstance(v, str) and v.strip().upper() in {UNAVAILABLE, "N/A", ""}:
        return UNAVAILABLE
    try:
        return float(v)
    except (TypeError, ValueError):
        return UNAVAILABLE


def analyze_session(root: Path, session_id: str | None = None) -> dict[str, Any]:
    manifest = {}
    for name in ("manifest.json", "export_manifest.json", "session_manifest.json"):
        p = root / name
        if p.exists():
            manifest = _load_json(p)
            break

    sid = session_id or manifest.get("session_id") or "UNKNOWN"
    trades = _read_jsonl(root / "trades.jsonl") or _load_listish(root / "trades.json")
    candidates = _read_jsonl(root / "candidates.jsonl") or _load_listish(root / "candidates.json")
    reflections = _read_jsonl(root / "reflections.jsonl") or _load_listish(root / "reflections.json")
    decision_deltas = _read_jsonl(root / "decision_deltas.jsonl") or _load_listish(root / "decision_deltas.json")
    outcomes = _read_jsonl(root / "outcomes.jsonl") or _load_listish(root / "outcomes.json")
    session = {}
    for name in ("bounded_6h_status.json", "session_status.json", "session.json"):
        p = root / name
        if p.exists():
            session = _load_json(p)
            break
    if "bounded_6h" in session and isinstance(session["bounded_6h"], dict):
        session = session["bounded_6h"]

    candidates_total = int(session.get("candidates_total") or len(candidates) or 0)
    cost_blocks = int(session.get("cost_gate_blocks") or _count_reason(candidates, "COST") or 0)
    risk_blocks = int(session.get("risk_critic_blocks") or _count_reason(candidates, "RISK") or 0)
    mistake_blocks = int(session.get("mistake_guard_blocks") or _count_reason(candidates, "MISTAKE") or 0)
    entries = int(session.get("entries_total") or 0)
    completed = int(session.get("trades_completed") or len(trades) or 0)

    wins = losses = 0
    gross = 0.0
    entry_fees = 0.0
    exit_fees = 0.0
    funding_vals: list[float] = []
    funding_missing = 0
    good_w = good_l = bad_w = bad_l = 0
    direction_ok_net_loss = 0
    cost_dominated = 0
    fee_churn = 0

    trade_rows: list[dict[str, Any]] = []
    outcome_rows: list[dict[str, Any]] = []

    for t in trades:
        pnl = _safe_num(t.get("realized_pnl", t.get("net_pnl", t.get("pnl"))))
        fee_e = _safe_num(t.get("entry_fee", t.get("fees_entry")))
        fee_x = _safe_num(t.get("exit_fee", t.get("fees_exit")))
        fee_tot = _safe_num(t.get("total_fees", t.get("fees")))
        fund = _safe_num(t.get("funding"))
        if isinstance(pnl, float):
            gross += pnl
            if pnl >= 0:
                wins += 1
            else:
                losses += 1
        if isinstance(fee_e, float):
            entry_fees += fee_e
        if isinstance(fee_x, float):
            exit_fees += fee_x
        if not isinstance(fee_tot, float) and isinstance(fee_e, float) and isinstance(fee_x, float):
            fee_tot = fee_e + fee_x
        if isinstance(fund, float):
            funding_vals.append(fund)
        else:
            funding_missing += 1
            fund = UNAVAILABLE
        pq = str(t.get("process_quality") or t.get("outcome_class") or "").upper()
        if "GOOD_PROCESS_WIN" in pq:
            good_w += 1
        elif "GOOD_PROCESS_LOSS" in pq:
            good_l += 1
        elif "BAD_PROCESS_WIN" in pq:
            bad_w += 1
        elif "BAD_PROCESS_LOSS" in pq:
            bad_l += 1
        dir_ok = bool(t.get("direction_correct") or t.get("favorable_direction"))
        net = _safe_num(t.get("net_pnl", pnl if isinstance(pnl, float) else None))
        if dir_ok and isinstance(net, float) and net < 0:
            direction_ok_net_loss += 1
        if t.get("cost_dominated") or "COST" in str(t.get("block_reason", "")).upper():
            cost_dominated += 1
        if isinstance(fee_tot, float) and isinstance(pnl, float) and abs(fee_tot) >= abs(pnl):
            fee_churn += 1
        trade_rows.append(
            {
                "trade_id": t.get("trade_id") or t.get("id"),
                "symbol": t.get("symbol"),
                "gross_pnl": pnl,
                "entry_fee": fee_e,
                "exit_fee": fee_x,
                "total_fees": fee_tot,
                "funding": fund,
                "net_pnl": net,
                "process_quality": pq or UNAVAILABLE,
            }
        )

    for o in outcomes:
        outcome_rows.append(
            {
                "outcome_id": o.get("outcome_id") or o.get("id"),
                "trade_case_id": o.get("trade_case_id") or o.get("source_trade_case_id"),
                "process_quality": o.get("process_quality"),
                "result": o.get("result"),
            }
        )

    total_fees = entry_fees + exit_fees
    if funding_missing and not funding_vals:
        funding: float | str = UNAVAILABLE
        net_pnl: float | str = UNAVAILABLE if completed else 0.0 if completed == 0 else UNAVAILABLE
        if completed == 0:
            net_pnl = 0.0
        elif isinstance(gross, float):
            # fees known, funding unavailable → net cannot be claimed complete
            net_pnl = UNAVAILABLE
    else:
        funding = sum(funding_vals)
        net_pnl = gross - total_fees + (funding if isinstance(funding, float) else 0.0)

    # When zero trades, net can be reported as 0 only as "no closed PnL", not fabricated funding.
    if completed == 0:
        net_pnl = 0.0
        funding = UNAVAILABLE if funding_missing or not funding_vals else funding

    profit_factor: float | str
    expectancy: float | str
    max_dd: float | str
    if completed < 3:
        profit_factor = INSUFFICIENT_SAMPLE
        expectancy = INSUFFICIENT_SAMPLE
        max_dd = INSUFFICIENT_SAMPLE
    else:
        win_sum = sum(float(r["gross_pnl"]) for r in trade_rows if isinstance(r["gross_pnl"], float) and r["gross_pnl"] > 0)
        loss_sum = abs(sum(float(r["gross_pnl"]) for r in trade_rows if isinstance(r["gross_pnl"], float) and r["gross_pnl"] < 0))
        profit_factor = (win_sum / loss_sum) if loss_sum > 0 else (math.inf if win_sum > 0 else INSUFFICIENT_SAMPLE)
        expectancy = gross / completed if completed else INSUFFICIENT_SAMPLE
        max_dd = _max_drawdown([float(r["gross_pnl"]) for r in trade_rows if isinstance(r["gross_pnl"], float)])

    learning = assess_learning(reflections, decision_deltas, candidates)
    zero_trade = None
    if entries == 0 and completed == 0:
        zero_trade = {
            "candidates_total": candidates_total,
            "cost_gate_blocks": cost_blocks,
            "risk_critic_blocks": risk_blocks,
            "mistake_guard_blocks": mistake_blocks,
            "recommendation": "DEMO_AUTONOMOUS_6H_BLOCKED_NO_VALID_CANDIDATES",
            "note": "Zero fills is valid when gates fail-closed; do not loosen live session",
            "false_negative_unknown": True,
        }

    summary = {
        "session_id": sid,
        "candidates_total": candidates_total,
        "risk_critic_blocks": risk_blocks,
        "mistake_guard_blocks": mistake_blocks,
        "cost_gate_blocks": cost_blocks,
        "entries": entries,
        "completed_trades": completed,
        "wins": wins,
        "losses": losses,
        "gross_pnl": gross if completed else 0.0,
        "entry_fees": entry_fees if completed else 0.0,
        "exit_fees": exit_fees if completed else 0.0,
        "total_fees": total_fees if completed else 0.0,
        "funding": funding,
        "net_pnl": net_pnl,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "max_drawdown": max_dd,
        "good_process_wins": good_w,
        "good_process_losses": good_l,
        "bad_process_wins": bad_w,
        "bad_process_losses": bad_l,
        "reflection_coverage": learning["reflection_coverage"],
        "similar_case_coverage": learning["similar_case_coverage"],
        "decision_delta_count": learning["decision_delta_count"],
        "repeated_error_count": learning["repeated_error_count"],
        "cost_dominated_entry_count": cost_dominated,
        "direction_correct_but_net_loss_count": direction_ok_net_loss,
        "fee_churn_count": fee_churn,
        "learning_effectiveness": learning["learning_effectiveness"],
        "zero_trade_analysis": zero_trade,
        "forbidden_labels": {
            "proven": False,
            "production_ready": False,
            "profitable": False,
        },
    }
    return {
        "summary": summary,
        "trade_rows": trade_rows,
        "outcome_rows": outcome_rows,
        "reflections": reflections,
        "decision_deltas": decision_deltas,
        "learning": learning,
    }


def _load_listish(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = _load_json(path)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "trades", "candidates", "reflections", "decision_deltas", "outcomes"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    return []


def _count_reason(rows: list[dict[str, Any]], needle: str) -> int:
    n = 0
    for r in rows:
        blob = " ".join(str(r.get(k, "")) for k in ("block_reason", "gate", "verdict", "reason")).upper()
        if needle in blob:
            n += 1
    return n


def _max_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return abs(max_dd)


def assess_learning(
    reflections: list[dict[str, Any]],
    deltas: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    with_similar = 0
    chain_ok = 0
    for r in reflections:
        if r.get("similar_candidate_id") or r.get("similar_case_id"):
            with_similar += 1
        needed = (
            r.get("source_trade_case_id")
            and r.get("similarity_score") is not None
            and r.get("before_verdict")
            and r.get("after_verdict")
            and r.get("guard_action")
            and r.get("policy_version")
        )
        if needed:
            chain_ok += 1

    delta_count = len(deltas)
    accepted = 0
    for d in deltas:
        label = str(d.get("delta_type") or d.get("change") or "")
        normalized = label.replace(" ", "").replace("->", "→").upper()
        if normalized in {x.upper() for x in ACCEPTABLE_DECISION_DELTAS} or "ALLOW" in normalized:
            accepted += 1

    refl_cov = (len(reflections) / max(1, len(reflections))) if reflections else 0.0
    # Coverage vs trades unknown here; report raw counts honestly
    similar_cov = (with_similar / len(reflections)) if reflections else 0.0

    if not reflections:
        effectiveness = NOT_YET_OBSERVABLE
    elif with_similar == 0:
        effectiveness = NOT_YET_OBSERVABLE
    elif delta_count == 0:
        effectiveness = NOT_PROVEN
    elif accepted > 0:
        effectiveness = PRELIMINARY_EVIDENCE
    else:
        effectiveness = NOT_PROVEN

    return {
        "reflection_count": len(reflections),
        "reflection_coverage": refl_cov,
        "similar_case_coverage": similar_cov,
        "decision_delta_count": delta_count,
        "accepted_decision_delta_count": accepted,
        "evidence_chain_complete_count": chain_ok,
        "repeated_error_count": sum(1 for r in reflections if r.get("repeated_error")),
        "learning_effectiveness": effectiveness,
        "note": "6H must not claim PROVEN/PRODUCTION_READY/PROFITABLE",
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = result["summary"]
    (out_dir / "analysis_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "reflection_analysis.json").write_text(json.dumps(result["learning"], indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "similar_case_analysis.json").write_text(
        json.dumps({"items": [r for r in result["reflections"] if r.get("similar_candidate_id") or r.get("similar_case_id")]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "decision_delta_analysis.json").write_text(
        json.dumps({"items": result["decision_deltas"]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "error_recurrence_analysis.json").write_text(
        json.dumps({"repeated_error_count": summary.get("repeated_error_count"), "items": [r for r in result["reflections"] if r.get("repeated_error")]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with (out_dir / "trade_cost_analysis.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["trade_id", "symbol", "gross_pnl", "entry_fee", "exit_fee", "total_fees", "funding", "net_pnl", "process_quality"],
        )
        w.writeheader()
        for row in result["trade_rows"]:
            w.writerow(row)

    with (out_dir / "outcome_analysis.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["outcome_id", "trade_case_id", "process_quality", "result"])
        w.writeheader()
        for row in result["outcome_rows"]:
            w.writerow(row)

    md = [
        f"# Session Quality Report — {summary.get('session_id')}",
        "",
        f"- Entries: {summary.get('entries')}",
        f"- Completed trades: {summary.get('completed_trades')}",
        f"- Cost gate blocks: {summary.get('cost_gate_blocks')}",
        f"- Funding: {summary.get('funding')}",
        f"- Net PnL: {summary.get('net_pnl')}",
        f"- Learning effectiveness: {summary.get('learning_effectiveness')}",
        f"- Profit factor: {summary.get('profit_factor')}",
        "",
        "Forbidden claims (must remain false for 6H): PROVEN / PRODUCTION_READY / PROFITABLE",
    ]
    if summary.get("zero_trade_analysis"):
        md.append("")
        md.append("## Zero-trade analysis")
        md.append(json.dumps(summary["zero_trade_analysis"], indent=2, ensure_ascii=False))
    (out_dir / "session_quality_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze NEXUS demo session export offline")
    ap.add_argument("--input", required=True, help="Export directory or ZIP")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--output", required=True, help="Output directory")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero on missing core files")
    args = ap.parse_args()

    root = resolve_input(Path(args.input))
    if args.strict and not any((root / n).exists() for n in ("manifest.json", "export_manifest.json", "session_status.json", "bounded_6h_status.json", "session.json")):
        print("STRICT: missing session manifest/status")
        return 2
    result = analyze_session(root, session_id=args.session_id)
    write_outputs(result, Path(args.output))
    print(json.dumps({"ok": True, "session_id": result["summary"]["session_id"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
