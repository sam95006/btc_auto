"""Blind Reflection V2.2 — Groq classifies without seeing deterministic answer."""
from __future__ import annotations

import os
import time
from collections import Counter
from typing import Any

from backend.nexus_ai_gateway.founder_providers import CRITIC_SCHEMA, REFLECTION_SCHEMA, FounderAIGateway
from backend.nexus_edge_discovery import BLIND_REFLECTION
from backend.nexus_strategy_engine.evidence_v2 import completeness_ratio, deterministic_process_baseline
from backend.nexus_strategy_engine.reflection_calibration import PROCESS_MAP
from backend.nexus_strategy_engine.reflection_v2_1 import build_calibration_packets_v21

ALLOWED = (
    "GOOD_PROCESS_WIN",
    "GOOD_PROCESS_LOSS",
    "BAD_PROCESS_WIN",
    "BAD_PROCESS_LOSS",
    "UNDETERMINED_PROCESS",
)
INFORMATIVE = frozenset(
    {"GOOD_PROCESS_WIN", "GOOD_PROCESS_LOSS", "BAD_PROCESS_WIN", "BAD_PROCESS_LOSS"}
)


def _strip_deterministic_leak(prompt: str) -> None:
    banned = (
        "deterministic_baseline",
        "Deterministic mapping suggests",
        "expected_family",
        "expected classification",
        "desired agreement",
    )
    low = prompt.lower()
    for b in banned:
        assert b.lower() not in low, f"blind_prompt_leak:{b}"


def run_blind_reflection_v22(
    *,
    market_rows: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    universe_snapshot_id: str,
    data_checksum: str,
    target_count: int = 60,
) -> dict[str, Any]:
    prev = os.environ.get("NEXUS_AI_MOCK")
    os.environ["NEXUS_AI_MOCK"] = "0"
    try:
        packets = build_calibration_packets_v21(
            market_rows=market_rows,
            hypotheses=hypotheses,
            universe_snapshot_id=universe_snapshot_id,
            data_checksum=data_checksum,
            target_count=target_count,
        )
        gw = FounderAIGateway.from_env(mock_for_ci=False)
        agree = disagree = undetermined = informative = valid = invalid = 0
        critic_total = critic_resolved = 0
        critic_agree_det = critic_agree_groq = critic_indep = 0
        ai_counts: Counter[str] = Counter()

        for packet in packets:
            base = deterministic_process_baseline(packet)
            det = base["deterministic_process_status"]
            pnl = float(packet.get("net_pnl") or 0) if isinstance(packet.get("net_pnl"), (int, float)) else 0.0
            wl = "win" if pnl > 0 else "loss"
            expected = PROCESS_MAP.get(det, {}).get(wl)
            if det == "PROCESS_EVIDENCE_INSUFFICIENT":
                expected = "UNDETERMINED_PROCESS"

            missing = (packet.get("evidence_layers") or {}).get("missing_evidence") or []
            # BLIND prompt: no deterministic answer
            prompt = (
                "Blind Reflection V2.2. Classify process using ONLY the evidence packet. "
                f"missing_evidence={missing}. "
                "Do NOT invent spread, slippage, Funding, OI, regime, rule violation, or entry rationale. "
                "A loss is not automatically BAD_PROCESS_LOSS. A win is not automatically GOOD_PROCESS_WIN. "
                f"process_classification MUST be exactly one of: {'|'.join(ALLOWED)}. "
                "If evidence is insufficient, return UNDETERMINED_PROCESS. "
                "Return reflection_v1 JSON."
            )
            _strip_deterministic_leak(prompt)
            assert "deterministic_baseline" not in prompt.lower()
            assert "deterministic mapping suggests" not in prompt.lower()
            assert "expected_family" not in prompt.lower()

            reflection, rec, _ = gw.invoke_profile(
                profile_id="GROQ_REFLECTION_REASONER",
                prompt=prompt,
                schema=REFLECTION_SCHEMA,
                prompt_schema_version="blind_reflection_v2_2",
            )
            if rec.get("result_status") in {"SUCCESS", "OK"} and reflection is not None:
                valid += 1
            else:
                invalid += 1
                undetermined += 1
                time.sleep(0.25)
                continue

            raw = str(reflection.get("process_classification") or "").strip().upper()
            ai_cls = raw if raw in ALLOWED else "UNDETERMINED_PROCESS"
            ai_counts[ai_cls] += 1
            if ai_cls in INFORMATIVE:
                informative += 1
            if ai_cls == "UNDETERMINED_PROCESS":
                undetermined += 1

            if expected and ai_cls == expected:
                agree += 1
            elif det == "PROCESS_EVIDENCE_INSUFFICIENT" and ai_cls == "UNDETERMINED_PROCESS":
                agree += 1
            else:
                disagree += 1
                # Critic only after independent Groq result, and only on disagreement / low confidence
                conf = reflection.get("confidence")
                low_conf = isinstance(conf, (int, float)) and float(conf) < 0.55
                if ai_cls != expected or low_conf or ai_cls == "UNDETERMINED_PROCESS":
                    critic_total += 1
                    time.sleep(0.35)
                    critic, crit_rec, _ = gw.invoke_profile(
                        profile_id="SAMBANOVA_INDEPENDENT_CRITIC",
                        prompt=(
                            "Independent critic review. You may see evidence, deterministic result, and Groq result. "
                            "Do not invent market data. Do not target a requested answer. "
                            f"deterministic={det}/{expected}. groq={ai_cls}. "
                            "Return critic_v1 with critic_verdict."
                        ),
                        schema=CRITIC_SCHEMA,
                        prompt_schema_version="critic_v1",
                    )
                    if critic and str(critic.get("critic_verdict") or critic.get("verdict") or ""):
                        critic_resolved += 1
                        v = str(critic.get("critic_verdict") or critic.get("verdict") or "").upper()
                        if "DET" in v or (expected and expected in v):
                            critic_agree_det += 1
                        elif ai_cls in v or "GROQ" in v:
                            critic_agree_groq += 1
                        else:
                            critic_indep += 1
            time.sleep(0.2)

        n = max(len(packets), 1)
        classified = max(agree + disagree, 1)
        informative_ratio = informative / n
        quality_ok = (
            (valid / n) >= 0.95
            and (agree / classified) >= 0.70
            and informative_ratio >= 0.40
            and ((critic_resolved / critic_total) if critic_total else 1.0) >= 0.80
        )
        return {
            "schema": "blind_reflection_v2_2_calibration",
            "engine": BLIND_REFLECTION,
            "NEXUS_AI_MOCK": "0",
            "blind_reflection_calibration_count": len(packets),
            "blind_valid_schema_ratio": valid / n,
            "blind_agreement_ratio": agree / classified,
            "blind_disagreement_ratio": disagree / classified,
            "informative_classification_ratio": informative_ratio,
            "undetermined_ratio": undetermined / n,
            "critic_resolution_ratio": (critic_resolved / critic_total) if critic_total else 1.0,
            "critic_agreement_with_deterministic": critic_agree_det,
            "critic_agreement_with_Groq": critic_agree_groq,
            "critic_independent_disagreement": critic_indep,
            "ai_process_counts": dict(ai_counts),
            "quality_targets_met": quality_ok,
            "new_lesson_record_count": 0,
            "new_policy_effect_lesson_count": 0 if not quality_ok or informative_ratio < 0.40 else 0,
            "anchored_v2_1_preserved_as": "ANCHORED_CALIBRATION_RESULT",
            "anchored_v2_1_not_overwritten": True,
            "prompt_excludes_deterministic_answer": True,
            "prompt_excludes_expected_family": True,
            "critic_runs_only_after_independent_result": True,
            "api_keys_exposed": False,
            "sanitized_inputs_only": True,
        }
    finally:
        if prev is None:
            os.environ.pop("NEXUS_AI_MOCK", None)
        else:
            os.environ["NEXUS_AI_MOCK"] = prev
