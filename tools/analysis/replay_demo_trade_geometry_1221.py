#!/usr/bin/env python3
"""Geometry + cost replay of frozen 6H candidates — no future data, no orders."""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.fee_rate import replay_conservative_quote
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP, MIN_NET_REWARD_RISK_RATIO
from backend.nexus_demo_execution.trade_geometry import (
    compute_structure_geometry,
    evaluate_fixed_symmetric_percent,
)


SENSITIVITY = [
    (0.008, 0.008),
    (0.008, 0.005),
    (0.010, 0.005),
    (0.012, 0.006),
    (0.015, 0.0075),
]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _qty(price: float) -> float:
    if price <= 0:
        return 0.0
    return (MARGIN_PER_TRADE_CAP * FIXED_LEVERAGE) / price


def _extract_structure(cand: dict[str, Any]) -> dict[str, Any]:
    # Only use fields present on the frozen candidate — never invent ATR/swings.
    mq = cand.get("market_quality") if isinstance(cand.get("market_quality"), dict) else {}
    return {
        "atr": cand.get("atr") or mq.get("atr"),
        "recent_swing_high": cand.get("recent_swing_high") or mq.get("recent_swing_high"),
        "recent_swing_low": cand.get("recent_swing_low") or mq.get("recent_swing_low"),
        "support": cand.get("support") or mq.get("support"),
        "resistance": cand.get("resistance") or mq.get("resistance"),
        "liquidity_levels": cand.get("liquidity_levels") or mq.get("liquidity_levels"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--session-id", default="NEXUS-DEMO-6H-8124394e67")
    ap.add_argument("--fee-rate", type=float, default=0.00055)
    args = ap.parse_args()

    export_dir = Path(args.export_dir)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    candidates = _load_jsonl(export_dir / "bounded_candidates.jsonl")
    gates = _load_jsonl(export_dir / "cost_gates.jsonl")
    pairs = list(zip(candidates, gates)) if len(gates) == len(candidates) else [(c, None) for c in candidates]

    rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    formula_errors = 0
    future_data_used = False

    for cand, gate in pairs:
        try:
            price = float(cand.get("last_price") or 0)
            side = str(cand.get("direction") or "Buy")
            qty = _qty(price)
            funding = cand.get("funding_rate") if str(cand.get("funding_status") or "").upper() == "KNOWN" else None
            spread = float(cand.get("spread_bps") or 0)
            fee_q = replay_conservative_quote(str(cand.get("symbol") or ""), args.fee_rate)
            structure = _extract_structure(cand)
            geom = compute_structure_geometry(
                side=side,
                entry_price=price,
                atr=_f(structure["atr"]),
                recent_swing_high=_f(structure["recent_swing_high"]),
                recent_swing_low=_f(structure["recent_swing_low"]),
                support=_f(structure["support"]),
                resistance=_f(structure["resistance"]),
                liquidity_levels=structure["liquidity_levels"] if isinstance(structure["liquidity_levels"], list) else None,
                spread_bps=spread,
                slippage_bps=spread,
                fee_rate=fee_q.usable_taker,
                funding_rate=float(funding) if funding is not None else None,
                qty=qty,
            )
            # Engineering reference: original fixed ±0.8%
            fixed = evaluate_fixed_symmetric_percent(
                side=side,
                entry_price=price,
                tp_pct=0.008,
                sl_pct=0.008,
                fee_rate=float(fee_q.usable_taker or 0),
                spread_bps=spread,
                slippage_bps=spread,
                funding_rate=float(funding) if funding is not None else None,
                qty=qty,
            )
            row = {
                "candidate_id": cand.get("candidate_id"),
                "symbol": cand.get("symbol"),
                "strategy": cand.get("strategy"),
                "regime": cand.get("regime"),
                "original_gate_reason": (gate or {}).get("reason"),
                "fee_source": fee_q.fee_source,
                "fee_rate_status": fee_q.status,
                "geometry_source": geom.geometry_source,
                "geometry_allowed": geom.allowed,
                "geometry_block_reason": geom.block_reason,
                "inputs_missing": list(geom.inputs_missing),
                "net_rr": geom.net_rr,
                "gross_rr": geom.gross_rr,
                "net_reward": geom.net_reward,
                "total_cost": geom.total_cost,
                "fixed_08_net_rr": fixed.net_rr,
                "fixed_08_allowed": fixed.allowed,
                "FIXED_SYMMETRIC_GEOMETRY_INCOMPATIBLE_WITH_NET_RR_GATE": True,
            }
            rows.append(row)
            if geom.block_reason == "GEOMETRY_INPUT_MISSING":
                missing_rows.append(
                    {
                        "candidate_id": cand.get("candidate_id"),
                        "symbol": cand.get("symbol"),
                        "missing": ",".join(geom.inputs_missing),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            formula_errors += 1
            rows.append(
                {
                    "candidate_id": cand.get("candidate_id"),
                    "symbol": cand.get("symbol"),
                    "geometry_block_reason": f"FORMULA_ERROR:{type(exc).__name__}",
                    "geometry_allowed": False,
                }
            )

    # Sensitivity aggregate (engineering only)
    sens_stats = []
    for tp_pct, sl_pct in SENSITIVITY:
        pass_n = 0
        for cand, _ in pairs[: min(200, len(pairs))]:  # sample first 200 for speed
            price = float(cand.get("last_price") or 0)
            if price <= 0:
                continue
            funding = cand.get("funding_rate") if str(cand.get("funding_status") or "").upper() == "KNOWN" else None
            fixed = evaluate_fixed_symmetric_percent(
                side=str(cand.get("direction") or "Buy"),
                entry_price=price,
                tp_pct=tp_pct,
                sl_pct=sl_pct,
                fee_rate=args.fee_rate,
                spread_bps=float(cand.get("spread_bps") or 0),
                slippage_bps=float(cand.get("spread_bps") or 0),
                funding_rate=float(funding) if funding is not None else None,
                qty=_qty(price),
            )
            if fixed.allowed:
                pass_n += 1
        sens_stats.append(
            {
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "gross_rr": round(tp_pct / sl_pct, 4) if sl_pct else None,
                "sample_n": min(200, len(pairs)),
                "pass_count": pass_n,
                "note": "engineering_diagnosis_only_not_for_live_tuning",
            }
        )

    geometry_complete = sum(1 for r in rows if not r.get("inputs_missing"))
    geometry_missing = sum(1 for r in rows if r.get("geometry_block_reason") == "GEOMETRY_INPUT_MISSING")
    geometry_valid = sum(1 for r in rows if r.get("geometry_allowed") is True)
    geometry_invalid = sum(1 for r in rows if r.get("geometry_allowed") is False)
    net_rr_pass = sum(
        1
        for r in rows
        if isinstance(r.get("net_rr"), (int, float)) and float(r["net_rr"]) >= MIN_NET_REWARD_RISK_RATIO
    )
    net_rr_block = sum(
        1
        for r in rows
        if isinstance(r.get("net_rr"), (int, float)) and float(r["net_rr"]) < MIN_NET_REWARD_RISK_RATIO
    )
    cost_block = sum(1 for r in rows if r.get("geometry_block_reason") == "BLOCK_COST_DOMINATED_ENTRY")
    fixed_pass = sum(1 for r in rows if r.get("fixed_08_allowed") is True)

    summary = {
        "session_id": args.session_id,
        "rows_total": len(rows),
        "geometry_complete": geometry_complete,
        "geometry_input_missing": geometry_missing,
        "geometry_valid": geometry_valid,
        "geometry_invalid": geometry_invalid,
        "net_rr_pass": net_rr_pass,
        "net_rr_block": net_rr_block,
        "cost_block": cost_block,
        "potential_candidates": geometry_valid,
        "formula_errors": formula_errors,
        "future_data_used": future_data_used,
        "fixed_symmetric_08_pass": fixed_pass,
        "FIXED_SYMMETRIC_GEOMETRY_INCOMPATIBLE_WITH_NET_RR_GATE": fixed_pass == 0,
        "required_net_rr": MIN_NET_REWARD_RISK_RATIO,
        "fee_rate_used": args.fee_rate,
        "fee_rate_status": "REPLAY_CONFIGURED_CONSERVATIVE",
        "symbol_distribution": dict(Counter(str(r.get("symbol")) for r in rows)),
        "strategy_distribution": dict(Counter(str(r.get("strategy")) for r in rows)),
        "regime_distribution": dict(Counter(str(r.get("regime")) for r in rows)),
        "sensitivity": sens_stats,
        "generated_at": time.time(),
        "recommendation": "STRUCTURE_GEOMETRY_INPUTS_REQUIRED_BEFORE_6H_V2",
    }

    with (out / "geometry_replay_1221.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "geometry_replay_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with (out / "geometry_replay_distribution.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["dimension", "key", "count"])
        for dim, dist in (
            ("symbol", summary["symbol_distribution"]),
            ("strategy", summary["strategy_distribution"]),
            ("regime", summary["regime_distribution"]),
        ):
            for k, v in dist.items():
                w.writerow([dim, k, v])

    with (out / "geometry_missing_inputs.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["candidate_id", "symbol", "missing"])
        w.writeheader()
        for r in missing_rows:
            w.writerow(r)

    sens_lines = [
        "# Geometry Sensitivity (engineering diagnosis only)",
        "",
        "Do **not** pick the highest pass-rate combo for live trading.",
        "",
        f"FIXED_SYMMETRIC_GEOMETRY_INCOMPATIBLE_WITH_NET_RR_GATE={summary['FIXED_SYMMETRIC_GEOMETRY_INCOMPATIBLE_WITH_NET_RR_GATE']}",
        f"fixed ±0.8% pass on full set: {fixed_pass}/{len(rows)}",
        "",
        "| TP% | SL% | Gross R:R | sample pass |",
        "|-----|-----|-----------|-------------|",
    ]
    for s in sens_stats:
        sens_lines.append(
            f"| {s['tp_pct']*100:.2f} | {s['sl_pct']*100:.2f} | {s['gross_rr']} | {s['pass_count']}/{s['sample_n']} |"
        )
    sens_lines.extend(
        [
            "",
            "## Structure replay",
            f"- geometry_input_missing: {geometry_missing}",
            f"- geometry_valid: {geometry_valid}",
            f"- formula_errors: {formula_errors}",
            f"- future_data_used: {future_data_used}",
            "",
            "Original 6H candidates lack ATR/swing/support/resistance fields → structure geometry cannot be completed without migrating market-structure inputs into the capture path.",
        ]
    )
    (out / "geometry_sensitivity_report.md").write_text("\n".join(sens_lines), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if formula_errors == 0 else 2


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
