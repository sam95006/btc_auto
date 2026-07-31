#!/usr/bin/env python3
"""Forensic analysis of exported cost_gates — recompute, audit, classify A–E.

Does not mutate source DB or rewrite historical records.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Defaults matching session_limits / cost_entry_gate (observation policy)
MARGIN_CAP = 20.0
LEVERAGE = 25
FUNDING_BUFFER_RATE = 0.0001  # will override from code constants if present
COST_UNCERTAINTY_RATE = 0.0002
MIN_NET_REWARD_TO_COST = 0.25
MIN_NET_REWARD_RISK_RATIO = 0.35
TAKER_DEFAULT = 0.00055

try:
    from backend.nexus_demo_execution.session_limits import (
        COST_UNCERTAINTY_BUFFER_RATE,
        FUNDING_CONSERVATIVE_BUFFER_RATE,
        MIN_NET_REWARD_RISK_RATIO as _MIN_RR,
        MIN_NET_REWARD_TO_COST as _MIN_COST,
        TAKER_FEE_RATE_DEFAULT,
    )

    FUNDING_BUFFER_RATE = FUNDING_CONSERVATIVE_BUFFER_RATE
    COST_UNCERTAINTY_RATE = COST_UNCERTAINTY_BUFFER_RATE
    MIN_NET_REWARD_TO_COST = _MIN_COST
    MIN_NET_REWARD_RISK_RATIO = _MIN_RR
    TAKER_DEFAULT = TAKER_FEE_RATE_DEFAULT
except Exception:  # noqa: BLE001
    pass


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, str) and v.strip().upper() in {"", "MISSING", "UNKNOWN", "UNAVAILABLE", "N/A"}:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(vals: list[float], p: float) -> float | str:
    if not vals:
        return "UNAVAILABLE"
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return s[idx]


def recompute_from_breakdown(gate: dict[str, Any], candidate: dict[str, Any] | None) -> dict[str, Any]:
    bd = gate.get("breakdown") if isinstance(gate.get("breakdown"), dict) else {}
    fee_rate = _num(bd.get("fee_rate") or gate.get("fee_rate"))
    notional = _num(bd.get("notional"))
    entry_fee = _num(bd.get("estimated_entry_fee"))
    exit_fee = _num(bd.get("estimated_exit_fee"))
    slip = _num(bd.get("estimated_slippage"))
    fund = _num(bd.get("estimated_funding"))
    unc = _num(bd.get("cost_uncertainty_buffer"))
    gross = _num(bd.get("gross_take_profit_pnl") or gate.get("estimated_net_reward"))
    # Prefer recorded gross from breakdown
    gross_tp = _num(bd.get("gross_take_profit_pnl"))
    gross_sl = _num(bd.get("gross_stop_loss_pnl"))

    issues: list[str] = []
    funding_class = "FUNDING_MISSING"

    # Funding honesty from recorded gate
    fs = str(gate.get("funding_status") or "").upper()
    if fs == "UNAVAILABLE":
        funding_class = "FUNDING_UNAVAILABLE"
        if fund == 0.0:
            # buffer may be non-zero even when unavailable
            if fund is not None and abs(fund) < 1e-12 and "FUNDING_UNAVAILABLE" in str(gate.get("labels")):
                pass
        labels = gate.get("labels") or []
        if "FUNDING_UNAVAILABLE_USING_CONSERVATIVE_BUFFER" in labels:
            funding_class = "FUNDING_UNAVAILABLE"
    elif fs == "KNOWN":
        if fund is None:
            funding_class = "FUNDING_MISSING"
        elif abs(fund) < 1e-15:
            funding_class = "FUNDING_KNOWN_ZERO"
        else:
            funding_class = "FUNDING_KNOWN_NONZERO"
    else:
        if fund == 0.0 or fund == 0:
            funding_class = "FUNDING_DEFAULTED_TO_ZERO"
            issues.append("FUNDING_DEFAULTED_TO_ZERO")

    # Recompute if we have fee_rate + notional
    recomputed: dict[str, Any] = {
        "fee_rate": fee_rate if fee_rate is not None else "UNAVAILABLE",
        "notional": notional if notional is not None else "UNAVAILABLE",
    }
    formula_match = True
    if fee_rate is None or notional is None:
        formula_match = False
        issues.append("INSUFFICIENT_INPUTS_FOR_RECOMPUTE")
        recomputed.update(
            {
                "estimated_entry_fee": "UNAVAILABLE",
                "estimated_exit_fee": "UNAVAILABLE",
                "estimated_round_trip_fee": "UNAVAILABLE",
                "estimated_total_cost": "UNAVAILABLE",
                "estimated_net_reward": "UNAVAILABLE",
            }
        )
    else:
        r_entry = notional * fee_rate
        r_exit = notional * fee_rate
        r_rt = r_entry + r_exit
        # Slippage: need bps — from candidate if available
        slip_bps = _num((candidate or {}).get("spread_bps"))
        if slip_bps is None:
            # reverse from recorded slip if possible
            r_slip = slip if slip is not None else "UNAVAILABLE"
        else:
            r_slip = notional * (slip_bps / 10000.0)
        # Funding recompute
        cand_fs = str((candidate or {}).get("funding_status") or "").upper()
        cand_fr = _num((candidate or {}).get("funding_rate"))
        if cand_fs == "KNOWN" and cand_fr is not None:
            r_fund = abs(notional * cand_fr)
            funding_class = "FUNDING_KNOWN_ZERO" if abs(r_fund) < 1e-15 else "FUNDING_KNOWN_NONZERO"
        elif cand_fs == "UNAVAILABLE" or gate.get("funding_status") == "UNAVAILABLE":
            r_fund = notional * FUNDING_BUFFER_RATE
            funding_class = "FUNDING_UNAVAILABLE"
        else:
            r_fund = fund if fund is not None else notional * FUNDING_BUFFER_RATE
            if fund == 0.0 and cand_fs not in {"KNOWN"}:
                funding_class = "FUNDING_DEFAULTED_TO_ZERO"
                issues.append("FUNDING_DEFAULTED_TO_ZERO")

        r_unc = notional * COST_UNCERTAINTY_RATE
        if isinstance(r_slip, float):
            r_total = r_rt + r_slip + float(r_fund) + r_unc
        else:
            r_total = "UNAVAILABLE"

        r_net = (gross_tp - r_total) if isinstance(r_total, float) and gross_tp is not None else "UNAVAILABLE"

        recomputed.update(
            {
                "estimated_entry_fee": round(r_entry, 8),
                "estimated_exit_fee": round(r_exit, 8),
                "estimated_round_trip_fee": round(r_rt, 8),
                "estimated_slippage": round(r_slip, 8) if isinstance(r_slip, float) else r_slip,
                "estimated_funding": round(float(r_fund), 8) if isinstance(r_fund, (int, float)) else r_fund,
                "cost_uncertainty_buffer": round(r_unc, 8),
                "estimated_total_cost": round(r_total, 8) if isinstance(r_total, float) else r_total,
                "estimated_net_reward": round(r_net, 8) if isinstance(r_net, float) else r_net,
                "gross_take_profit_pnl": gross_tp if gross_tp is not None else "UNAVAILABLE",
                "gross_stop_loss_pnl": gross_sl if gross_sl is not None else "UNAVAILABLE",
            }
        )

        # Compare recorded vs recomputed fees
        for key, recorded, recomputed_v in (
            ("entry_fee", entry_fee, r_entry),
            ("exit_fee", exit_fee, r_exit),
            ("funding", fund, r_fund if isinstance(r_fund, float) else None),
            ("uncertainty", unc, r_unc),
        ):
            if recorded is not None and recomputed_v is not None and isinstance(recomputed_v, float):
                if abs(recorded - recomputed_v) > 1e-5:
                    formula_match = False
                    issues.append(f"MISMATCH_{key.upper()}")

        # Notional vs margin*leverage check if candidate has qty/price
        if candidate:
            price = _num(candidate.get("last_price") or candidate.get("entry_price") or candidate.get("price"))
            # qty not always on candidate — derive from notional/price
            if price and price > 0 and notional:
                implied_qty = notional / price
                expected_notional_from_margin = MARGIN_CAP * LEVERAGE
                # soft check: notional should be near 500U
                if abs(notional - expected_notional_from_margin) / expected_notional_from_margin > 0.35:
                    issues.append("NOTIONAL_FAR_FROM_MARGIN_X_LEVERAGE")
                    # not automatically E — allocation may vary

        # Double fee / double leverage heuristics
        if fee_rate and notional and entry_fee is not None:
            if abs(entry_fee - notional * fee_rate * LEVERAGE) < 1e-6:
                issues.append("FEE_MAY_INCLUDE_EXTRA_LEVERAGE_FACTOR")
                formula_match = False
            if abs(entry_fee - MARGIN_CAP * fee_rate) < 1e-6 and abs(entry_fee - notional * fee_rate) > 1e-4:
                issues.append("FEE_COMPUTED_ON_MARGIN_NOT_NOTIONAL")
                formula_match = False

    return {
        "recomputed": recomputed,
        "formula_match": formula_match and not any(i.startswith("MISMATCH_") or i.startswith("FEE_") for i in issues),
        "formula_issue_codes": issues,
        "funding_class": funding_class,
    }


def classify_row(gate: dict[str, Any], recomputed_meta: dict[str, Any]) -> tuple[str, list[str]]:
    issues = list(recomputed_meta.get("formula_issue_codes") or [])
    labels = [str(x) for x in (gate.get("labels") or [])]
    reason = str(gate.get("reason") or "")
    funding_class = recomputed_meta.get("funding_class")
    net = _num(gate.get("estimated_net_reward"))
    total_cost = _num(gate.get("estimated_total_cost"))
    rr = _num(gate.get("net_reward_risk_ratio"))
    fee_status = str(gate.get("fee_rate_status") or "")

    # E first if clear defects
    e_codes = [i for i in issues if i.startswith("FEE_") or i.startswith("MISMATCH_") or i == "FUNDING_DEFAULTED_TO_ZERO"]
    if "FUNDING_DEFAULTED_TO_ZERO" in issues or funding_class == "FUNDING_DEFAULTED_TO_ZERO":
        return "E_POSSIBLE_GATE_CONFIGURATION_DEFECT", issues + ["FUNDING_HONESTY"]
    if any(i.startswith("FEE_MAY") or i.startswith("FEE_COMPUTED") for i in issues):
        return "E_POSSIBLE_GATE_CONFIGURATION_DEFECT", issues

    # B data missing
    if reason == "FEE_RATE_UNKNOWN" or fee_status == "UNKNOWN" or "FEE_RATE_UNKNOWN" in labels:
        return "B_DATA_MISSING_FAIL_CLOSED", issues + ["FEE_UNKNOWN"]
    if reason == "INVALID_PRICE_QTY":
        return "B_DATA_MISSING_FAIL_CLOSED", issues + ["INVALID_PRICE_QTY"]

    # D potential false negative — positive net but blocked on threshold
    if net is not None and net > 0 and reason == "BLOCK_COST_DOMINATED_ENTRY":
        if "net_reward_risk_ratio_low" in labels or "fee_churn_candidate" in labels:
            # borderline threshold
            if total_cost and net < MIN_NET_REWARD_TO_COST * total_cost * 1.15:
                return "D_POTENTIAL_FALSE_NEGATIVE", issues + ["THRESHOLD_BOUNDARY"]
            if rr is not None and 0 < rr < MIN_NET_REWARD_RISK_RATIO:
                return "D_POTENTIAL_FALSE_NEGATIVE", issues + ["RR_BOUNDARY"]

    # A correct cost block — net <= 0
    if net is not None and net <= 0:
        return "A_CORRECT_COST_BLOCK", issues + ["NET_REWARD_NON_POSITIVE"]

    # C market no net edge — data present, blocked for cost reasons with negative or insufficient edge
    if reason == "BLOCK_COST_DOMINATED_ENTRY":
        return "C_MARKET_NO_NET_EDGE", issues + ["COST_DOMINATED"]

    if not gate.get("allowed", True):
        return "C_MARKET_NO_NET_EDGE", issues + [reason or "BLOCKED"]

    return "C_MARKET_NO_NET_EDGE", issues


def audit_decision_deltas(deltas: list[dict[str, Any]]) -> dict[str, Any]:
    validated = 0
    invalid = 0
    misclassified = 0
    rows = []
    required = (
        "source_trade_case_id",
        "similar_candidate_id",
        "similarity_score",
        "before_verdict",
        "after_verdict",
        "before_score",
        "after_score",
        "guard_action",
        "reflection_id",
    )
    for d in deltas:
        if d.get("seed"):
            invalid += 1
            rows.append({**{k: d.get(k) for k in ("_record_id",)}, "decision_delta": False, "reason": "seed_record"})
            continue
        missing = [k for k in required if d.get(k) in (None, "", "MISSING")]
        # Session memory apply typically has before/after without trade case
        has_learning_chain = bool(d.get("source_trade_case_id") and d.get("similar_candidate_id") and d.get("guard_action"))
        if has_learning_chain and not missing:
            validated += 1
            rows.append({"_record_id": d.get("_record_id"), "decision_delta": True, "validated": True})
        else:
            invalid += 1
            misclassified += 1
            rows.append(
                {
                    "_record_id": d.get("_record_id"),
                    "decision_delta": False,
                    "cost_gate_or_memory_apply": True,
                    "missing_fields": missing,
                    "before_verdict": d.get("before_verdict"),
                    "after_verdict": d.get("after_verdict"),
                }
            )
    return {
        "recorded_decision_delta_count": len(deltas),
        "validated_decision_delta_count": validated,
        "invalid_decision_delta_count": invalid,
        "cost_gate_blocks_misclassified_as_delta": misclassified,
        "rows": rows,
    }


def pair_candidates(gates: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    """Best-effort pairing: cost gates are appended after risk-pass candidates in order.

    Risk-failed candidates never get a cost_gate row. Pair by sequential consumption
    of candidates that would reach cost gate (risk PASS/WATCH).
    """
    paired: list[dict[str, Any] | None] = [None] * len(gates)
    risk_ok = [c for c in candidates if str(c.get("risk_critic_verdict") or "PASS") in {"PASS", "WATCH", ""}]
    # If risk field absent, assume all candidates reached cost gate path after memory.apply
    if not any("risk_critic_verdict" in c for c in candidates):
        # memory.apply runs before cost gate for every candidate that wasn't risk-blocked.
        # Without risk field, use 1:1 with min length by record id order.
        for i, g in enumerate(gates):
            if i < len(candidates):
                paired[i] = candidates[i]
        return paired

    gi = 0
    for c in risk_ok:
        if gi >= len(gates):
            break
        # After memory apply, cost gate always appended
        paired[gi] = c
        gi += 1
    return paired


def analyze(export_dir: Path, output: Path, session_id: str) -> dict[str, Any]:
    gates = _load_jsonl(export_dir / "cost_gates.jsonl")
    candidates = _load_jsonl(export_dir / "bounded_candidates.jsonl")
    deltas = _load_jsonl(export_dir / "decision_deltas.jsonl")
    meta = {}
    if (export_dir / "export_meta.json").exists():
        meta = json.loads((export_dir / "export_meta.json").read_text(encoding="utf-8"))

    paired = pair_candidates(gates, candidates)
    raw_rows = []
    recomputed_rows = []
    class_rows = []
    formula_rows = []
    funding_rows = []

    class_counts: Counter[str] = Counter()
    fee_known = fee_unknown = 0
    funding_known = funding_unavail = funding_default_zero = 0
    slip_known = slip_unknown = 0
    gross_vals: list[float] = []
    cost_vals: list[float] = []
    net_vals: list[float] = []
    rr_vals: list[float] = []
    fee_dom = slip_dom = fund_dom = buf_dom = threshold_only = formula_mismatch = formula_unverifiable = 0
    symbols: set[str] = set()
    strategies: set[str] = set()
    regimes: set[str] = set()
    reason_counter: Counter[str] = Counter()

    for i, gate in enumerate(gates):
        cand = paired[i] if i < len(paired) else None
        rc = recompute_from_breakdown(gate, cand)
        primary, issue_codes = classify_row(gate, rc)
        class_counts[primary] += 1
        reason_counter[str(gate.get("reason") or "UNKNOWN")] += 1

        bd = gate.get("breakdown") if isinstance(gate.get("breakdown"), dict) else {}
        if gate.get("fee_rate_status") == "KNOWN":
            fee_known += 1
        else:
            fee_unknown += 1
        fc = rc["funding_class"]
        if fc in {"FUNDING_KNOWN_ZERO", "FUNDING_KNOWN_NONZERO"}:
            funding_known += 1
        elif fc == "FUNDING_UNAVAILABLE":
            funding_unavail += 1
        elif fc == "FUNDING_DEFAULTED_TO_ZERO":
            funding_default_zero += 1
        if _num(bd.get("estimated_slippage")) is not None:
            slip_known += 1
        else:
            slip_unknown += 1

        g = _num(bd.get("gross_take_profit_pnl"))
        tc = _num(gate.get("estimated_total_cost"))
        nr = _num(gate.get("estimated_net_reward"))
        rr = _num(gate.get("net_reward_risk_ratio"))
        if g is not None:
            gross_vals.append(g)
        if tc is not None:
            cost_vals.append(tc)
        if nr is not None:
            net_vals.append(nr)
        if rr is not None:
            rr_vals.append(rr)

        fees = (_num(bd.get("estimated_round_trip_fee")) or 0) 
        slip = _num(bd.get("estimated_slippage")) or 0
        fund = _num(bd.get("estimated_funding")) or 0
        buf = _num(bd.get("cost_uncertainty_buffer")) or 0
        if tc and tc > 0:
            parts = {"fee": fees, "slip": slip, "fund": fund, "buf": buf}
            dom = max(parts, key=parts.get)
            if dom == "fee":
                fee_dom += 1
            elif dom == "slip":
                slip_dom += 1
            elif dom == "fund":
                fund_dom += 1
            else:
                buf_dom += 1
        if primary == "D_POTENTIAL_FALSE_NEGATIVE":
            threshold_only += 1
        if not rc["formula_match"]:
            if "INSUFFICIENT_INPUTS_FOR_RECOMPUTE" in (rc.get("formula_issue_codes") or []):
                formula_unverifiable += 1
            else:
                formula_mismatch += 1

        if cand:
            if cand.get("symbol"):
                symbols.add(str(cand["symbol"]))
            if cand.get("strategy"):
                strategies.add(str(cand["strategy"]))
            if cand.get("regime"):
                regimes.add(str(cand["regime"]))

        raw = {
            "session_id": session_id,
            "candidate_id": (cand or {}).get("candidate_id", "MISSING"),
            "symbol": (cand or {}).get("symbol", "MISSING"),
            "direction": (cand or {}).get("direction", "MISSING"),
            "strategy": (cand or {}).get("strategy", "MISSING"),
            "regime": (cand or {}).get("regime", "MISSING"),
            "evaluated_at": gate.get("_created_at", "MISSING"),
            "entry_price": (cand or {}).get("last_price") or (cand or {}).get("price") or "MISSING",
            "margin": MARGIN_CAP,
            "leverage": LEVERAGE,
            "notional": bd.get("notional", "MISSING"),
            "gross_reward_usdt": bd.get("gross_take_profit_pnl", "MISSING"),
            "gross_risk_usdt": bd.get("gross_stop_loss_pnl", "MISSING"),
            "estimated_entry_fee": bd.get("estimated_entry_fee", "MISSING"),
            "estimated_exit_fee": bd.get("estimated_exit_fee", "MISSING"),
            "estimated_round_trip_fee": bd.get("estimated_round_trip_fee", "MISSING"),
            "estimated_slippage": bd.get("estimated_slippage", "MISSING"),
            "slippage_bps": (cand or {}).get("spread_bps", "MISSING"),
            "funding_rate": (cand or {}).get("funding_rate", "UNAVAILABLE"),
            "funding_status": gate.get("funding_status", "MISSING"),
            "estimated_funding": bd.get("estimated_funding", "MISSING"),
            "cost_uncertainty_buffer": bd.get("cost_uncertainty_buffer", "MISSING"),
            "estimated_total_cost": gate.get("estimated_total_cost", "MISSING"),
            "estimated_net_reward": gate.get("estimated_net_reward", "MISSING"),
            "net_reward_risk_ratio": gate.get("net_reward_risk_ratio", "MISSING"),
            "block_reason": gate.get("reason", "MISSING"),
            "block_reason_codes": gate.get("labels", []),
            "cost_gate_verdict": "BLOCK" if not gate.get("allowed") else "ALLOW",
            "account_epoch": gate.get("_account_epoch") or gate.get("account_epoch") or "MISSING",
            "_record_id": gate.get("_record_id"),
        }
        # Honesty: never coerce missing to 0 in raw export fields already set
        raw_rows.append(raw)
        recomputed_rows.append(
            {
                "_record_id": gate.get("_record_id"),
                "recorded_estimated_net_reward": gate.get("estimated_net_reward"),
                "recorded_estimated_total_cost": gate.get("estimated_total_cost"),
                "recorded_funding_status": gate.get("funding_status"),
                **{f"recomputed_{k}": v for k, v in rc["recomputed"].items()},
                "formula_match": rc["formula_match"],
                "formula_issue_codes": rc["formula_issue_codes"],
                "funding_class": rc["funding_class"],
            }
        )
        class_rows.append(
            {
                "_record_id": gate.get("_record_id"),
                "candidate_id": raw["candidate_id"],
                "symbol": raw["symbol"],
                "primary_classification": primary,
                "issue_codes": ";".join(issue_codes),
                "block_reason": raw["block_reason"],
            }
        )
        formula_rows.append(
            {
                "_record_id": gate.get("_record_id"),
                "formula_match": rc["formula_match"],
                "formula_issue_codes": ";".join(rc["formula_issue_codes"]),
            }
        )
        funding_rows.append(
            {
                "_record_id": gate.get("_record_id"),
                "funding_class": rc["funding_class"],
                "recorded_funding_status": gate.get("funding_status"),
                "recorded_estimated_funding": bd.get("estimated_funding"),
                "candidate_funding_status": (cand or {}).get("funding_status"),
                "candidate_funding_rate": (cand or {}).get("funding_rate"),
            }
        )

    delta_audit = audit_decision_deltas(deltas)
    data_missing_ratio = (class_counts.get("B_DATA_MISSING_FAIL_CLOSED", 0) / len(gates)) if gates else 0.0

    if delta_audit["validated_decision_delta_count"] > 0:
        learning = "PRELIMINARY_EVIDENCE"
    elif gates:
        learning = "NOT_YET_OBSERVABLE"
    else:
        learning = "NOT_YET_OBSERVABLE"

    # Dominant classification
    dominant_class = class_counts.most_common(1)[0][0] if class_counts else "UNKNOWN"
    # Insufficient inputs (e.g. FEE_RATE_UNKNOWN early exit) is data defect, not formula defect.
    possible_defect = (
        class_counts.get("E_POSSIBLE_GATE_CONFIGURATION_DEFECT", 0) > 0
        or formula_mismatch > 0
        or funding_default_zero > 0
    )

    gate24_ready = (
        formula_mismatch == 0
        and funding_default_zero == 0
        and data_missing_ratio <= 0.15
        and delta_audit["validated_decision_delta_count"] == delta_audit["recorded_decision_delta_count"]
        or (
            formula_mismatch == 0
            and funding_default_zero == 0
            and data_missing_ratio <= 0.15
            and delta_audit["invalid_decision_delta_count"] == delta_audit["recorded_decision_delta_count"]
            # all deltas invalid-as-learning is OK if we correctly reclassify
            and class_counts.get("E_POSSIBLE_GATE_CONFIGURATION_DEFECT", 0) == 0
            and dominant_class in {"A_CORRECT_COST_BLOCK", "C_MARKET_NO_NET_EDGE"}
        )
    )
    # Tighten: if many E or high missing, not ready
    if possible_defect or class_counts.get("E_POSSIBLE_GATE_CONFIGURATION_DEFECT", 0) > max(5, len(gates) * 0.01):
        gate24_ready = False
    if class_counts.get("D_POTENTIAL_FALSE_NEGATIVE", 0) > len(gates) * 0.2:
        gate24_ready = False

    if dominant_class in {"A_CORRECT_COST_BLOCK", "C_MARKET_NO_NET_EDGE"} and not possible_defect:
        rec = "COST_GATE_BEHAVIOR_PLAUSIBLE_PENDING_FOUNDER_24H_REVIEW" if gate24_ready else "COST_GATE_NEEDS_FOUNDER_REVIEW_BEFORE_24H"
    elif dominant_class == "B_DATA_MISSING_FAIL_CLOSED":
        rec = "FIX_DATA_SOURCES_THEN_DRY_RUN_REPLAY"
    elif dominant_class == "D_POTENTIAL_FALSE_NEGATIVE":
        rec = "OFFLINE_THRESHOLD_SENSITIVITY_BEFORE_LIVE_CHANGE"
    else:
        rec = "FIX_FORMULA_THEN_HISTORICAL_REPLAY_NO_24H"

    summary = {
        "session_id": session_id,
        "total_rows": len(gates),
        "unique_candidates": len({r["candidate_id"] for r in raw_rows if r["candidate_id"] != "MISSING"}),
        "duplicate_rows": max(0, len(gates) - len({r.get("_record_id") for r in gates})),
        "unique_symbols": len(symbols),
        "unique_strategies": len(strategies),
        "unique_regimes": len(regimes),
        "classification_A": class_counts.get("A_CORRECT_COST_BLOCK", 0),
        "classification_B": class_counts.get("B_DATA_MISSING_FAIL_CLOSED", 0),
        "classification_C": class_counts.get("C_MARKET_NO_NET_EDGE", 0),
        "classification_D": class_counts.get("D_POTENTIAL_FALSE_NEGATIVE", 0),
        "classification_E": class_counts.get("E_POSSIBLE_GATE_CONFIGURATION_DEFECT", 0),
        "fee_known_count": fee_known,
        "fee_unknown_count": fee_unknown,
        "funding_known_count": funding_known,
        "funding_unavailable_count": funding_unavail,
        "funding_defaulted_zero_count": funding_default_zero,
        "slippage_known_count": slip_known,
        "slippage_unknown_count": slip_unknown,
        "gross_reward_min": min(gross_vals) if gross_vals else "UNAVAILABLE",
        "gross_reward_median": statistics.median(gross_vals) if gross_vals else "UNAVAILABLE",
        "gross_reward_p95": _pct(gross_vals, 95),
        "total_cost_min": min(cost_vals) if cost_vals else "UNAVAILABLE",
        "total_cost_median": statistics.median(cost_vals) if cost_vals else "UNAVAILABLE",
        "total_cost_p95": _pct(cost_vals, 95),
        "net_reward_min": min(net_vals) if net_vals else "UNAVAILABLE",
        "net_reward_median": statistics.median(net_vals) if net_vals else "UNAVAILABLE",
        "net_reward_p95": _pct(net_vals, 95),
        "net_rr_min": min(rr_vals) if rr_vals else "UNAVAILABLE",
        "net_rr_median": statistics.median(rr_vals) if rr_vals else "UNAVAILABLE",
        "net_rr_p95": _pct(rr_vals, 95),
        "fee_dominated_count": fee_dom,
        "slippage_dominated_count": slip_dom,
        "funding_dominated_count": fund_dom,
        "buffer_dominated_count": buf_dom,
        "threshold_only_block_count": threshold_only,
        "formula_mismatch_count": formula_mismatch,
        "formula_unverifiable_count": formula_unverifiable,
        "block_reason_distribution": dict(reason_counter),
        "root_cause_note": (
            "All rows short-circuited on FEE_RATE_UNKNOWN with empty breakdown; "
            "cost math never ran. Decision deltas lack source_trade_case_id and "
            "are scan-memory applies, not trade-learning deltas."
            if reason_counter.get("FEE_RATE_UNKNOWN", 0) == len(gates) and gates
            else ""
        ),
        "decision_delta_audit": {
            "recorded_decision_delta_count": delta_audit["recorded_decision_delta_count"],
            "validated_decision_delta_count": delta_audit["validated_decision_delta_count"],
            "invalid_decision_delta_count": delta_audit["invalid_decision_delta_count"],
            "cost_gate_blocks_misclassified_as_delta": delta_audit["cost_gate_blocks_misclassified_as_delta"],
        },
        "data_missing_ratio": data_missing_ratio,
        "dominant_classification": dominant_class,
        "possible_formula_defect": possible_defect,
        "learning_effectiveness": learning,
        "24h_gate_ready": gate24_ready,
        "validation_duration": "6H",
        "post_session_idle_time": "separate",
        "24H_validation_completed": False,
        "recommendation": rec,
        "source_meta": meta,
    }

    output.mkdir(parents=True, exist_ok=True)

    def write_jsonl(name: str, rows: list[dict[str, Any]]) -> None:
        with (output / name).open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    write_jsonl("cost_gate_raw_1221.jsonl", raw_rows)
    write_jsonl("cost_gate_recomputed_1221.jsonl", recomputed_rows)

    def write_csv(name: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            (output / name).write_text("", encoding="utf-8")
            return
        keys = list(rows[0].keys())
        with (output / name).open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow(r)

    write_csv("cost_gate_classification.csv", class_rows)
    write_csv("cost_gate_formula_issues.csv", formula_rows)
    write_csv("cost_gate_funding_audit.csv", funding_rows)
    write_csv("decision_delta_audit.csv", delta_audit["rows"])

    (output / "cost_gate_distribution.json").write_text(
        json.dumps(
            {
                "classification": dict(class_counts),
                "block_reason": dict(reason_counter),
                "symbols": sorted(symbols),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output / "cost_gate_forensic_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        f"# Cost Gate Forensic Report — {session_id}",
        "",
        f"- Rows: {summary['total_rows']}",
        f"- A/B/C/D/E: {summary['classification_A']}/{summary['classification_B']}/{summary['classification_C']}/{summary['classification_D']}/{summary['classification_E']}",
        f"- formula_mismatch_count: {summary['formula_mismatch_count']}",
        f"- funding_defaulted_zero_count: {summary['funding_defaulted_zero_count']}",
        f"- validated_decision_delta_count: {summary['decision_delta_audit']['validated_decision_delta_count']}",
        f"- invalid_decision_delta_count: {summary['decision_delta_audit']['invalid_decision_delta_count']}",
        f"- learning_effectiveness: {summary['learning_effectiveness']}",
        f"- 24h_gate_ready: {summary['24h_gate_ready']}",
        f"- recommendation: {summary['recommendation']}",
        "",
        "validation_duration=6H; post_session_idle_time=separate; 24H_validation_completed=false",
        "",
        "Note: decision_delta_count≈candidates reflects session memory apply on scans, not trade learning deltas.",
    ]
    (output / "cost_gate_forensic_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    manifest = {
        "session_id": session_id,
        "source_db_checksum": meta.get("database_checksum_after") or meta.get("database_checksum_before"),
        "export_row_count": len(gates),
        "source_schema": meta.get("schema_snapshot"),
        "tool": "forensic_cost_gate_analysis.py",
        "generated_at": time.time(),
        "redaction_status": "payloads_from_persisted_redacted_streams",
    }
    (output / "evidence_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--session-id", default="NEXUS-DEMO-6H-8124394e67")
    args = ap.parse_args()
    summary = analyze(Path(args.export_dir), Path(args.output), args.session_id)
    print(json.dumps({"ok": True, "rows": summary["total_rows"], "recommendation": summary["recommendation"], "24h_gate_ready": summary["24h_gate_ready"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
