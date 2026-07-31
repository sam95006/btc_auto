#!/usr/bin/env python3
"""Offline cost-gate replay of frozen 6H bounded_candidates — no re-scan, no orders.

Reconstructs qty/TP/SL with the same session policy used during NEXUS-DEMO-6H-8124394e67.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
from backend.nexus_demo_execution.fee_rate import (
    FEE_RATE_CONFIGURED_CONSERVATIVE,
    FEE_RATE_LIVE,
    FeeRateQuote,
    configured_conservative_quote,
)
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _qty_from_margin(price: float, margin: float = MARGIN_PER_TRADE_CAP, leverage: int = FIXED_LEVERAGE) -> float:
    if price <= 0:
        return 0.0
    notional = margin * leverage
    return notional / price


def _sl_tp(price: float, direction: str) -> tuple[float, float]:
    if str(direction).lower() in {"buy", "long"}:
        return price * 0.992, price * 1.008
    return price * 1.008, price * 0.992


def _resolve_fee(symbol: str, fee_rate: float | None, fee_source_cli: str) -> FeeRateQuote:
    if fee_rate is not None and fee_rate > 0:
        return FeeRateQuote(
            status=FEE_RATE_LIVE if fee_source_cli == "live" else FEE_RATE_CONFIGURED_CONSERVATIVE,
            symbol=symbol,
            maker_fee_rate=None,
            taker_fee_rate=fee_rate,
            fee_source=fee_source_cli,
            fee_fetch_error=None,
            fee_fetched_at=time.time(),
            fee_freshness_sec=0.0,
            fail_closed=False,
            new_entry_blocked=False,
        )
    cons = configured_conservative_quote(symbol)
    if cons is not None:
        return cons
    return FeeRateQuote(
        status="FEE_RATE_UNAVAILABLE",
        symbol=symbol,
        maker_fee_rate=None,
        taker_fee_rate=None,
        fee_source=fee_source_cli or "UNAVAILABLE",
        fee_fetch_error="no_fee_for_replay",
        fee_fetched_at=time.time(),
        fail_closed=True,
        new_entry_blocked=True,
    )


def replay_one(
    cand: dict[str, Any],
    original_gate: dict[str, Any] | None,
    fee_quote: FeeRateQuote,
) -> dict[str, Any]:
    symbol = str(cand.get("symbol") or "MISSING")
    price = float(cand.get("last_price") or 0)
    direction = str(cand.get("direction") or "Buy")
    qty = _qty_from_margin(price)
    sl, tp = _sl_tp(price, direction)
    funding = cand.get("funding_rate") if str(cand.get("funding_status") or "").upper() == "KNOWN" else None
    spread = float(cand.get("spread_bps") or 0)

    cost = evaluate_cost_gate(
        entry_price=price,
        stop_loss=sl,
        take_profit=tp,
        qty=qty,
        side=direction,
        fee_rate=fee_quote.usable_taker,
        funding_rate=float(funding) if funding is not None else None,
        slippage_bps=spread,
        fee_meta=fee_quote.to_dict(),
    )
    d = cost.to_dict()
    bd = d.get("breakdown") or {}
    return {
        "candidate_id": cand.get("candidate_id", "MISSING"),
        "symbol": symbol,
        "direction": direction,
        "original_verdict": (original_gate or {}).get("reason") or (original_gate or {}).get("allowed"),
        "original_allowed": (original_gate or {}).get("allowed"),
        "replay_verdict": d.get("reason"),
        "replay_allowed": d.get("allowed"),
        "fee_source": fee_quote.fee_source,
        "fee_rate_status": fee_quote.status,
        "taker_fee_rate": fee_quote.taker_fee_rate if fee_quote.taker_fee_rate is not None else "UNAVAILABLE",
        "gross_reward": bd.get("gross_take_profit_pnl", "UNAVAILABLE"),
        "total_cost": d.get("estimated_total_cost"),
        "net_reward": d.get("estimated_net_reward"),
        "net_rr": d.get("net_reward_risk_ratio"),
        "block_reason": d.get("reason") if not d.get("allowed") else "PASS",
        "qty": qty,
        "notional": bd.get("notional", "UNAVAILABLE"),
        "margin": MARGIN_PER_TRADE_CAP,
        "leverage": FIXED_LEVERAGE,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-dir", required=True, help="Readonly export dir with bounded_candidates.jsonl + cost_gates.jsonl")
    ap.add_argument("--output", required=True)
    ap.add_argument("--session-id", default="NEXUS-DEMO-6H-8124394e67")
    ap.add_argument("--fee-rate", type=float, default=None, help="Explicit taker fee for offline replay")
    ap.add_argument("--fee-source", default="replay_cli_fee_rate")
    args = ap.parse_args()

    export_dir = Path(args.export_dir)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    candidates = _load_jsonl(export_dir / "bounded_candidates.jsonl")
    gates = _load_jsonl(export_dir / "cost_gates.jsonl")
    # Pair by sequence after risk filter as forensic did — zip by index when lengths match
    pairs = list(zip(candidates, gates)) if len(gates) == len(candidates) else [(c, None) for c in candidates]

    rows: list[dict[str, Any]] = []
    formula_errors = 0
    for cand, gate in pairs:
        quote = _resolve_fee(str(cand.get("symbol") or ""), args.fee_rate, args.fee_source)
        try:
            rows.append(replay_one(cand, gate, quote))
        except Exception as exc:  # noqa: BLE001
            formula_errors += 1
            rows.append(
                {
                    "candidate_id": cand.get("candidate_id"),
                    "symbol": cand.get("symbol"),
                    "original_verdict": (gate or {}).get("reason"),
                    "replay_verdict": "FORMULA_ERROR",
                    "block_reason": f"FORMULA_ERROR:{type(exc).__name__}",
                    "fee_source": quote.fee_source,
                    "fee_rate_status": quote.status,
                    "gross_reward": "UNAVAILABLE",
                    "total_cost": "UNAVAILABLE",
                    "net_reward": "UNAVAILABLE",
                    "net_rr": "UNAVAILABLE",
                }
            )

    pass_n = sum(1 for r in rows if r.get("replay_allowed") is True)
    block_n = sum(1 for r in rows if r.get("replay_allowed") is not True)
    fee_unknown = sum(
        1
        for r in rows
        if r.get("fee_rate_status") in {"FEE_RATE_UNAVAILABLE", "FEE_RATE_AUTH_FAILED", "FEE_RATE_SCHEMA_MISMATCH"}
        or r.get("taker_fee_rate") in {None, "UNAVAILABLE"}
    )
    # Potential false negative: originally blocked on FEE_RATE_UNKNOWN but replay now passes
    pfn = sum(
        1
        for r in rows
        if r.get("original_allowed") is False
        and str(r.get("original_verdict")) == "FEE_RATE_UNKNOWN"
        and r.get("replay_allowed") is True
    )

    nets = [float(r["net_reward"]) for r in rows if isinstance(r.get("net_reward"), (int, float))]
    summary = {
        "session_id": args.session_id,
        "replay_rows": len(rows),
        "replay_pass_count": pass_n,
        "replay_block_count": block_n,
        "fee_unknown_count": fee_unknown,
        "formula_error_count": formula_errors,
        "potential_false_negative_count": pfn,
        "fee_source": args.fee_source if args.fee_rate is not None else "env_or_unavailable",
        "fee_rate_used": args.fee_rate if args.fee_rate is not None else "UNAVAILABLE",
        "replay_outputs_complete": formula_errors == 0 and len(rows) == len(candidates),
        "block_reason_distribution": dict(Counter(str(r.get("block_reason")) for r in rows)),
        "net_reward_median": statistics.median(nets) if nets else "UNAVAILABLE",
        "ready_for_next_bounded_test": fee_unknown == 0 and formula_errors == 0 and len(rows) == len(candidates),
        "generated_at": time.time(),
        "note": "Offline replay reconstructs qty/TP/SL from session policy; does not mutate source DB.",
    }

    with (out / "cost_gate_replay_1221.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "cost_gate_replay_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "cost_gate_replay_report.md").write_text(
        "\n".join(
            [
                f"# Cost Gate Replay — {args.session_id}",
                "",
                f"- rows: {summary['replay_rows']}",
                f"- pass: {summary['replay_pass_count']}",
                f"- block: {summary['replay_block_count']}",
                f"- fee_unknown: {summary['fee_unknown_count']}",
                f"- formula_errors: {summary['formula_error_count']}",
                f"- potential_false_negatives: {summary['potential_false_negative_count']}",
                f"- ready_for_next_bounded_test: {summary['ready_for_next_bounded_test']}",
                "",
                "24H remains blocked until Founder gate after fee source is LIVE or approved conservative.",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["replay_outputs_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
