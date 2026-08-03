"""Reflection calibration using Evidence V2 — no reserved OOS."""
from __future__ import annotations

import os
from collections import Counter
from typing import Any

from backend.nexus_ai_gateway.founder_providers import (
    CRITIC_SCHEMA,
    REFLECTION_SCHEMA,
    FounderAIGateway,
)
from backend.nexus_strategy_engine.constants import UNKNOWN
from backend.nexus_strategy_engine.evidence_v2 import (
    build_evidence_from_sim_row,
    completeness_ratio,
    deterministic_process_baseline,
)

PROCESS_MAP = {
    "PROCESS_COMPLIANT": {"win": "GOOD_PROCESS_WIN", "loss": "GOOD_PROCESS_LOSS"},
    "PROCESS_NONCOMPLIANT": {"win": "BAD_PROCESS_WIN", "loss": "BAD_PROCESS_LOSS"},
}


def build_calibration_packets(
    *,
    market_rows: list[dict[str, Any]],
    hypothesis: dict[str, Any],
    universe_snapshot_id: str,
    data_checksum: str,
    target_count: int = 40,
) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    # Market-derived
    for idx, row in enumerate(market_rows):
        if len(packets) >= target_count - 8:
            break
        packets.append(
            build_evidence_from_sim_row(
                row=row,
                hypothesis=hypothesis,
                trade_id=f"CAL_MKT_{idx}",
                candidate_id=f"cal_cand_{idx}",
                universe_snapshot_id=universe_snapshot_id,
                data_checksum=data_checksum,
            )
        )
    # Control fixtures with known violations
    fixtures = ["stale_data", "cost_gate", "missing_stop", "hard_block", "invalid_size"]
    base = market_rows[0] if market_rows else {
        "symbol": "BTCUSDT",
        "side": "Sell",
        "regime": "RANGE",
        "entry_status": "ENTRY_FILLED",
        "entry_price": 100.0,
        "stop": 102.0,
        "take_profit": 96.0,
        "entry_ts": 1_739_100_000_000,
        "gross_pnl": -1.0,
        "net_pnl": -1.2,
        "fees": 0.1,
        "slippage": 0.05,
        "funding": 0.0,
        "holding_bars": 5,
    }
    for i, viol in enumerate(fixtures):
        row = dict(base)
        row["net_pnl"] = 1.0 if i % 2 == 0 else -1.0
        row["gross_pnl"] = row["net_pnl"]
        packets.append(
            build_evidence_from_sim_row(
                row=row,
                hypothesis=hypothesis,
                trade_id=f"CAL_FIX_{viol}",
                candidate_id=f"fix_{viol}",
                universe_snapshot_id=universe_snapshot_id,
                data_checksum=data_checksum,
                intentional_violation=viol,
            )
        )
    # Pad with more market rows if needed
    i = 0
    while len(packets) < target_count and market_rows:
        row = market_rows[i % len(market_rows)]
        packets.append(
            build_evidence_from_sim_row(
                row=row,
                hypothesis=hypothesis,
                trade_id=f"CAL_PAD_{i}",
                candidate_id=f"pad_{i}",
                universe_snapshot_id=universe_snapshot_id,
                data_checksum=data_checksum,
            )
        )
        i += 1
        if i > target_count * 2:
            break
    return packets[:target_count]


def run_reflection_calibration(
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
    critic_agree = 0
    critic_disagree = 0
    invalid_schema = 0
    completeness = []

    mock = os.getenv("NEXUS_AI_MOCK", "1") == "1" or not use_real_ai
    if gw is None:
        gw = FounderAIGateway.from_env(mock_for_ci=mock)

    for packet in packets:
        base = deterministic_process_baseline(packet)
        det = base["deterministic_process_status"]
        det_counts[det] += 1
        completeness.append(base["evidence_completeness_ratio"])
        pnl = float(packet.get("net_pnl") or 0) if isinstance(packet.get("net_pnl"), (int, float)) else 0.0
        wl = "win" if pnl > 0 else "loss"

        prompt = (
            "Classify process using ONLY the evidence packet. "
            f"deterministic_baseline={det}. "
            "Do not invent MISSING/UNKNOWN fields. "
            "A loss is not automatically BAD_PROCESS_LOSS. "
            "A win is not automatically GOOD_PROCESS_WIN. "
            f"packet_keys_present={[k for k,v in packet.items() if v not in (None,'',UNKNOWN)][:40]}. "
            "Return reflection_v1 JSON with process_classification in "
            "GOOD_PROCESS_WIN|GOOD_PROCESS_LOSS|BAD_PROCESS_WIN|BAD_PROCESS_LOSS|UNDETERMINED_PROCESS."
        )
        reflection, rec, _ = gw.invoke_profile(
            profile_id="GROQ_REFLECTION_REASONER",
            prompt=prompt,
            schema=REFLECTION_SCHEMA,
            prompt_schema_version="reflection_v1",
        )
        if rec.get("result_status") == "INVALID_SCHEMA":
            invalid_schema += 1
        if reflection is None:
            undetermined += 1
            continue
        ai_cls = str(reflection.get("process_classification") or "UNDETERMINED_PROCESS")
        ai_counts[ai_cls] += 1
        ai_classified += 1
        if ai_cls == "UNDETERMINED_PROCESS":
            undetermined += 1
        expected_family = PROCESS_MAP.get(det, {}).get(wl)
        if expected_family and ai_cls == expected_family:
            agree += 1
        elif det == "PROCESS_EVIDENCE_INSUFFICIENT" and ai_cls == "UNDETERMINED_PROCESS":
            agree += 1
        elif ai_cls != "UNDETERMINED_PROCESS":
            disagree += 1
            # critic on disagreement
            critic, crit_rec, _ = gw.invoke_profile(
                profile_id="SAMBANOVA_INDEPENDENT_CRITIC",
                prompt=f"Review disagreement det={det} ai={ai_cls}. Return critic_v1.",
                schema=CRITIC_SCHEMA,
                prompt_schema_version="critic_v1",
            )
            if crit_rec.get("result_status") == "INVALID_SCHEMA":
                invalid_schema += 1
            if critic:
                v = str(critic.get("critic_verdict") or critic.get("verdict") or "").upper()
                if "AGREE" in v and "DIS" not in v:
                    critic_agree += 1
                else:
                    critic_disagree += 1

    ratio = sum(completeness) / max(len(completeness), 1)
    return {
        "schema": "reflection_calibration_summary_v1",
        "reflection_calibration_trade_count": len(packets),
        "evidence_completeness_ratio": ratio,
        "deterministic_classifiable_count": int(
            det_counts.get("PROCESS_COMPLIANT", 0) + det_counts.get("PROCESS_NONCOMPLIANT", 0)
        ),
        "AI_classified_count": ai_classified,
        "undetermined_count": undetermined,
        "deterministic_AI_agreement_count": agree,
        "deterministic_AI_disagreement_count": disagree,
        "critic_agreement_count": critic_agree,
        "critic_disagreement_count": critic_disagree,
        "invalid_schema_count": invalid_schema,
        "deterministic_counts": dict(det_counts),
        "ai_process_counts": dict(ai_counts),
        "control_fixtures_labeled": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
        "reserved_oos_used": False,
        "synthetic_market_performance": False,
    }
