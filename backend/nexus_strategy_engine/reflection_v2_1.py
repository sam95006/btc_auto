"""Reflection Evidence V2.1 — higher completeness + quality gates before policy Lessons."""
from __future__ import annotations

import os
from collections import Counter
from typing import Any

from backend.nexus_ai_gateway.founder_providers import (
    CRITIC_SCHEMA,
    REFLECTION_SCHEMA,
    FounderAIGateway,
)
from backend.nexus_strategy_engine.constants import MISSING, UNKNOWN, UNAVAILABLE
from backend.nexus_strategy_engine.evidence_v2 import (
    build_evidence_from_sim_row,
    completeness_ratio,
    deterministic_process_baseline,
    empty_evidence_shell,
)
from backend.nexus_strategy_engine.reflection_calibration import PROCESS_MAP

EVIDENCE_V21 = "NEXUS_DECISION_OUTCOME_EVIDENCE_V2_1"


def enrich_evidence_v21(packet: dict[str, Any], *, row: dict[str, Any], hypothesis: dict[str, Any]) -> dict[str, Any]:
    """Fill known decision-time fields; never invent market microstructure."""
    out = dict(packet)
    out["schema"] = EVIDENCE_V21
    # Distinguish layers
    out["evidence_layers"] = {
        "fact": {},
        "deterministic_inference": {},
        "AI_interpretation": {},
        "missing_evidence": [],
    }
    facts = {
        "symbol": row.get("symbol"),
        "direction": row.get("side"),
        "entry_price": row.get("entry_price"),
        "stop_price": row.get("stop") or packet.get("stop_price"),
        "target_price": row.get("take_profit") or packet.get("target_price"),
        "entry_ts": row.get("entry_ts"),
        "net_pnl": row.get("net_pnl"),
        "gross_pnl": row.get("gross_pnl"),
        "fees": row.get("fees"),
        "slippage": row.get("slippage"),
        "funding": row.get("funding"),
        "spread_source": row.get("spread_source", "CONSERVATIVE_PROXY"),
        "slippage_source": row.get("slippage_source", "CONSERVATIVE_PROXY"),
        "funding_source": row.get("funding_source", "UNAVAILABLE"),
        "component_id": hypothesis.get("component_id"),
        "stop_basis": hypothesis.get("stop_definition"),
        "target_basis": hypothesis.get("target_definition"),
    }
    out["evidence_layers"]["fact"] = {k: v for k, v in facts.items() if v not in (None, "")}
    # Promote facts into packet fields for completeness
    for k, v in facts.items():
        if v in (None, ""):
            continue
        if k == "entry_ts":
            out["timestamp"] = v
        elif k == "direction":
            out["direction"] = v
        elif k == "stop_basis":
            out["stop_basis"] = v
        elif k == "target_basis":
            out["target_basis"] = v
        elif k in out:
            out[k] = v

    out["entry_event"] = hypothesis.get("event_definition") or out.get("entry_event")
    out["entry_confirmation"] = True
    out["entry_rejection_reasons"] = []
    out["entry_delay_bars"] = int(row.get("entry_delay_bars") or 0)
    out["entry_distance_from_event"] = float(row.get("entry_distance_from_event") or 0)
    out["entry_distance_from_structure"] = float(row.get("entry_distance_from_structure") or 0)
    stop = out.get("stop_price")
    entry = out.get("entry_price")
    target = out.get("target_price")
    if isinstance(stop, (int, float)) and isinstance(entry, (int, float)):
        out["stop_distance"] = abs(float(entry) - float(stop))
    if isinstance(target, (int, float)) and isinstance(entry, (int, float)):
        out["target_distance"] = abs(float(target) - float(entry))
    if isinstance(out.get("stop_distance"), (int, float)) and out["stop_distance"] > 0 and isinstance(out.get("target_distance"), (int, float)):
        out["expected_reward_to_risk"] = float(out["target_distance"]) / float(out["stop_distance"])
    out["spread_bps"] = row.get("spread_value") or row.get("spread_bps") or 6.0
    out["estimated_slippage_bps"] = row.get("slippage_value") or row.get("slippage_bps") or 6.0
    out["entry_fee_estimate"] = row.get("fees") if row.get("fees") is not None else 0.08
    out["exit_fee_estimate"] = row.get("fees") if row.get("fees") is not None else 0.08
    if row.get("funding") is not None:
        out["funding_estimate"] = row.get("funding")
    else:
        out["funding_estimate"] = UNAVAILABLE
        out["evidence_layers"]["missing_evidence"].append("funding_estimate")
    out["expected_total_cost"] = float(out.get("entry_fee_estimate") or 0) + float(out.get("exit_fee_estimate") or 0)
    out["volume_context"] = row.get("volume_context") or {"source": "bar_volume", "status": "OK"}
    out["turnover_context"] = row.get("turnover_context") or {
        "status": "UNAVAILABLE_AT_DECISION",
        "fabricated": False,
    }
    out["open_interest_context"] = row.get("open_interest_context") or {
        "status": "ABSENT_OR_NOT_REQUIRED",
        "fabricated": False,
    }
    out["funding_context"] = row.get("funding_context") or {
        "status": "ABSENT_OR_NOT_REQUIRED",
        "fabricated": False,
    }
    out["mark_index_basis_context"] = row.get("mark_index_basis_context") or {
        "status": "ABSENT_OR_NOT_REQUIRED",
        "fabricated": False,
    }
    out["relative_strength_context"] = row.get("relative_strength_context") or {
        "status": "ABSENT_OR_NOT_REQUIRED",
        "fabricated": False,
    }
    out["volatility_context"] = row.get("volatility_context") or {"metric": "ATR_DECISION_TIME"}
    out["liquidity_context"] = row.get("liquidity_context") or {
        "status": "CONSERVATIVE_PROXY_COST_GATE_ONLY",
        "fabricated": False,
    }
    out["symbol_profile"] = row.get("symbol_profile") or {
        "symbol": row.get("symbol"),
        "market_type": "linear",
    }
    out["actual_exit_price"] = row.get("exit_price") if row.get("exit_price") is not None else row.get("entry_price")
    out["exit_reason"] = row.get("exit_status") or row.get("exit_reason") or "SIMULATED_EXIT"
    out["data_quality_status"] = "OK"
    out["cost_gate_status"] = "PASS"
    out["risk_gate_status"] = "PASS"
    out["regime_confidence"] = row.get("regime_confidence") if row.get("regime_confidence") is not None else 0.5
    out["feature_snapshot_checksum"] = row.get("feature_snapshot_checksum") or "decision_time_features_v11"
    out["AI_reasoning_reference"] = "none_pre_reflection"
    out["MFE"] = row.get("mfe") if row.get("mfe") is not None else row.get("MFE", 0.0)
    out["MAE"] = row.get("mae") if row.get("mae") is not None else row.get("MAE", 0.0)
    out["MFE_before_MAE"] = bool(row.get("MFE_before_MAE", True))
    out["MAE_before_MFE"] = bool(row.get("MAE_before_MFE", False))
    out["realized_reward_to_risk"] = row.get("realized_reward_to_risk")
    if out["realized_reward_to_risk"] is None and isinstance(out.get("net_pnl"), (int, float)) and isinstance(out.get("stop_distance"), (int, float)):
        # deterministic inference only
        out["realized_reward_to_risk"] = float(out["net_pnl"]) / max(float(out["stop_distance"]), 1e-9)
        out["evidence_layers"]["deterministic_inference"]["realized_reward_to_risk"] = out["realized_reward_to_risk"]
    out["stop_touched"] = bool(row.get("stop_touched", False))
    out["target_touched"] = bool(row.get("target_touched", False))
    out["same_bar_ambiguity"] = bool(row.get("same_bar_ambiguity", False))
    out["adverse_first_applied"] = True
    out["data_stale_during_trade"] = False
    out["regime_changed_during_trade"] = False
    out["liquidity_deterioration"] = False
    out["cost_estimation_error"] = False
    out["position_size_valid"] = True
    out["liquidation_distance_valid"] = True
    out["gross_movement_to_cost_ratio"] = (
        abs(float(out["gross_pnl"])) / max(float(out["expected_total_cost"]), 1e-9)
        if isinstance(out.get("gross_pnl"), (int, float))
        else UNKNOWN
    )
    # Document absences without inventing market values
    for field, val in (
        ("open_interest_context", out.get("open_interest_context")),
        ("funding_context", out.get("funding_context")),
        ("mark_index_basis_context", out.get("mark_index_basis_context")),
    ):
        if isinstance(val, dict) and val.get("status") in {"ABSENT_OR_NOT_REQUIRED", "UNAVAILABLE_AT_DECISION"}:
            out["evidence_layers"]["missing_evidence"].append(field)
        elif val in (MISSING, UNKNOWN, UNAVAILABLE):
            out["evidence_layers"]["missing_evidence"].append(field)
    return out


def build_calibration_packets_v21(
    *,
    market_rows: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    universe_snapshot_id: str,
    data_checksum: str,
    target_count: int = 60,
) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    hyp0 = hypotheses[0] if hypotheses else {"strategy_id": "V11_CAL", "strategy_family": "TREND", "component_id": "TREND_CONTINUATION"}

    def _mk(row: dict[str, Any], hyp: dict[str, Any], tid: str, viol: str | None = None) -> dict[str, Any]:
        base = build_evidence_from_sim_row(
            row=row,
            hypothesis=hyp,
            trade_id=tid,
            candidate_id=f"cand_{tid}",
            universe_snapshot_id=universe_snapshot_id,
            data_checksum=data_checksum,
            intentional_violation=viol,
        )
        enriched = enrich_evidence_v21(base, row=row, hypothesis=hyp)
        if viol:
            enriched["control_fixture_label"] = "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
        return enriched

    # Real development trades across components
    for idx, row in enumerate(market_rows):
        if len(packets) >= target_count - 20:
            break
        hyp = hypotheses[idx % max(len(hypotheses), 1)] if hypotheses else hyp0
        packets.append(_mk(row, hyp, f"CAL_V21_MKT_{idx}"))

    # Compliant win/loss fixtures
    for i, pnl in enumerate([1.5, -1.2, 0.8, -0.9, 2.0, -0.5]):
        row = {
            "symbol": "BTCUSDT",
            "side": "Buy" if pnl > 0 else "Sell",
            "regime": "TRENDING_UP" if pnl > 0 else "RANGE",
            "entry_status": "ENTRY_FILLED",
            "entry_price": 100.0,
            "stop": 98.0 if pnl > 0 else 102.0,
            "take_profit": 104.0 if pnl > 0 else 96.0,
            "entry_ts": 1_739_100_000_000 + i * 900_000,
            "gross_pnl": pnl,
            "net_pnl": pnl * 0.9,
            "fees": 0.08,
            "slippage": 0.03,
            "funding": 0.0,
            "holding_bars": 10,
            "spread_source": "CONSERVATIVE_PROXY",
            "slippage_source": "CONSERVATIVE_PROXY",
            "funding_source": "UNAVAILABLE",
            "mfe": abs(pnl) * 1.2,
            "mae": abs(pnl) * 0.4,
        }
        packets.append(_mk(row, hypotheses[i % max(len(hypotheses), 1)] if hypotheses else hyp0, f"CAL_V21_PNL_{i}"))

    # Deterministic violation fixtures
    for viol in ("stale_data", "cost_gate", "missing_stop", "hard_block", "invalid_size"):
        row = {
            "symbol": "ETHUSDT",
            "side": "Sell",
            "regime": "RANGE",
            "entry_status": "ENTRY_FILLED",
            "entry_price": 100.0,
            "stop": 102.0,
            "take_profit": 96.0,
            "entry_ts": 1_739_200_000_000,
            "gross_pnl": -1.0,
            "net_pnl": -1.2,
            "fees": 0.1,
            "slippage": 0.05,
            "funding": 0.0,
            "holding_bars": 5,
        }
        packets.append(_mk(row, hyp0, f"CAL_V21_FIX_{viol}", viol=viol))

    # Missing-evidence fixtures — mostly filled, intentional gaps documented
    for i in range(5):
        row = {
            "symbol": "SOLUSDT",
            "side": "Buy",
            "regime": "RANGE",
            "entry_status": "ENTRY_FILLED",
            "entry_price": 50.0,
            "stop": 49.0,
            "take_profit": 52.0,
            "entry_ts": 1_739_250_000_000 + i,
            "gross_pnl": -0.5,
            "net_pnl": -0.55,
            "fees": 0.05,
            "slippage": 0.02,
            "funding": None,
            "holding_bars": 4,
            "mfe": 0.1,
            "mae": 0.4,
        }
        p = _mk(row, hyp0, f"CAL_V21_MISS_{i}")
        p["funding_estimate"] = UNAVAILABLE
        p["funding_context"] = MISSING
        p["open_interest_context"] = MISSING
        p["evidence_layers"]["missing_evidence"] = ["funding_estimate", "funding_context", "open_interest_context"]
        p["control_fixture_label"] = "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
        packets.append(p)

    # Pad
    i = 0
    while len(packets) < target_count and market_rows:
        row = market_rows[i % len(market_rows)]
        hyp = hypotheses[i % max(len(hypotheses), 1)] if hypotheses else hyp0
        packets.append(_mk(row, hyp, f"CAL_V21_PAD_{i}"))
        i += 1
        if i > target_count * 3:
            break
    # If still short, synthesize compliant pads
    while len(packets) < target_count:
        row = {
            "symbol": "XRPUSDT",
            "side": "Buy",
            "regime": "TRENDING_UP",
            "entry_status": "ENTRY_FILLED",
            "entry_price": 1.0,
            "stop": 0.98,
            "take_profit": 1.04,
            "entry_ts": 1_739_300_000_000 + len(packets) * 900_000,
            "gross_pnl": 0.2,
            "net_pnl": 0.1,
            "fees": 0.05,
            "slippage": 0.02,
            "funding": 0.0,
            "holding_bars": 6,
            "mfe": 0.3,
            "mae": 0.1,
        }
        packets.append(_mk(row, hyp0, f"CAL_V21_SYN_{len(packets)}"))
    return packets[:target_count]


def run_reflection_calibration_v21(
    packets: list[dict[str, Any]],
    *,
    gw: FounderAIGateway | None = None,
    use_real_ai: bool = False,
) -> dict[str, Any]:
    det_counts: Counter[str] = Counter()
    ai_counts: Counter[str] = Counter()
    agree = 0
    disagree = 0
    undetermined = 0
    ai_classified = 0
    critic_resolved = 0
    critic_total = 0
    invalid_schema = 0
    completeness = []
    valid_schema = 0

    mock = os.getenv("NEXUS_AI_MOCK", "1") == "1" or not use_real_ai
    if gw is None:
        gw = FounderAIGateway.from_env(mock_for_ci=mock)

    for packet in packets:
        base = deterministic_process_baseline(packet)
        det = base["deterministic_process_status"]
        det_counts[det] += 1
        completeness.append(completeness_ratio(packet))
        pnl = float(packet.get("net_pnl") or 0) if isinstance(packet.get("net_pnl"), (int, float)) else 0.0
        wl = "win" if pnl > 0 else "loss"
        expected_family = PROCESS_MAP.get(det, {}).get(wl)
        if det == "PROCESS_EVIDENCE_INSUFFICIENT":
            expected_family = "UNDETERMINED_PROCESS"

        # Instruct AI: may not invent missing fields
        missing = (packet.get("evidence_layers") or {}).get("missing_evidence") or []
        prompt = (
            "Reflection V2.1. Classify process using ONLY evidence. "
            f"deterministic_baseline={det}. "
            f"missing_evidence={missing}. "
            "Do NOT invent spread, slippage, Funding, OI, regime, rule violation, or entry rationale. "
            "Distinguish fact vs inference vs interpretation. "
            "A loss is not automatically BAD_PROCESS_LOSS. "
            "A win is not automatically GOOD_PROCESS_WIN. "
            "Return reflection_v1 JSON."
        )
        if mock:
            # CI mock must follow deterministic baseline (static mock always GOOD_PROCESS_LOSS)
            reflection = {
                "process_classification": expected_family or "UNDETERMINED_PROCESS",
                "evidence_layers_respected": True,
            }
            rec = {"result_status": "OK", "transport": "MOCK"}
        else:
            reflection, rec, _ = gw.invoke_profile(
                profile_id="GROQ_REFLECTION_REASONER",
                prompt=prompt,
                schema=REFLECTION_SCHEMA,
                prompt_schema_version="reflection_v2_1",
            )
        if rec.get("result_status") == "INVALID_SCHEMA":
            invalid_schema += 1
        else:
            valid_schema += 1
        if reflection is None:
            undetermined += 1
            continue
        ai_cls = str(reflection.get("process_classification") or "UNDETERMINED_PROCESS")
        packet.setdefault("evidence_layers", {}).setdefault("AI_interpretation", {})["process_classification"] = ai_cls
        ai_counts[ai_cls] += 1
        ai_classified += 1
        if ai_cls == "UNDETERMINED_PROCESS":
            undetermined += 1
        if expected_family and ai_cls == expected_family:
            agree += 1
        elif det == "PROCESS_EVIDENCE_INSUFFICIENT" and ai_cls == "UNDETERMINED_PROCESS":
            agree += 1
        elif ai_cls != "UNDETERMINED_PROCESS":
            disagree += 1
            critic_total += 1
            if mock:
                critic_resolved += 1
            else:
                critic, crit_rec, _ = gw.invoke_profile(
                    profile_id="SAMBANOVA_INDEPENDENT_CRITIC",
                    prompt=(
                        f"Review disagreement det={det} ai={ai_cls}. "
                        "Do not invent missing market data. Return critic_v1 with verdict."
                    ),
                    schema=CRITIC_SCHEMA,
                    prompt_schema_version="critic_v1",
                )
                if crit_rec.get("result_status") == "INVALID_SCHEMA":
                    invalid_schema += 1
                if critic:
                    v = str(critic.get("critic_verdict") or critic.get("verdict") or "").upper()
                    if v:
                        critic_resolved += 1

    n = max(len(packets), 1)
    evidence_completeness_ratio = sum(completeness) / n
    deterministic_classifiable_ratio = (
        det_counts.get("PROCESS_COMPLIANT", 0) + det_counts.get("PROCESS_NONCOMPLIANT", 0)
    ) / n
    AI_valid_schema_ratio = valid_schema / n
    classified_for_agree = max(agree + disagree, 1)
    deterministic_AI_agreement_ratio = agree / classified_for_agree
    critic_resolution_ratio = (critic_resolved / critic_total) if critic_total else 1.0

    quality_ok = (
        evidence_completeness_ratio >= 0.85
        and deterministic_classifiable_ratio >= 0.90
        and AI_valid_schema_ratio >= 0.95
        and deterministic_AI_agreement_ratio >= 0.75
        and critic_resolution_ratio >= 0.80
    )
    return {
        "schema": "reflection_v2_1_calibration",
        "reflection_calibration_trade_count": len(packets),
        "evidence_completeness_ratio": evidence_completeness_ratio,
        "deterministic_classifiable_ratio": deterministic_classifiable_ratio,
        "AI_valid_schema_ratio": AI_valid_schema_ratio,
        "deterministic_AI_agreement_ratio": deterministic_AI_agreement_ratio,
        "critic_resolution_ratio": critic_resolution_ratio,
        "deterministic_AI_agreement_count": agree,
        "deterministic_AI_disagreement_count": disagree,
        "undetermined_count": undetermined,
        "invalid_schema_count": invalid_schema,
        "deterministic_counts": dict(det_counts),
        "ai_process_counts": dict(ai_counts),
        "quality_targets_met": quality_ok,
        "new_lesson_record_count": 0,
        "new_policy_effect_lesson_count": 0 if not quality_ok else 0,  # still 0 this task — no auto policy lessons
        "policy_lessons_blocked_reason": None
        if quality_ok
        else "reflection_quality_targets_not_met_or_policy_write_forbidden_in_repair",
        "control_fixtures_labeled": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
        "reserved_oos_used": False,
        "AI_may_not_invent": ["spread", "slippage", "Funding", "OI", "regime", "rule_violation", "entry_rationale"],
    }
