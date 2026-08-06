"""Fixtures for PUB18-B Decision Detail transparency (DEMO / PROVIDER_REQUIRED / STALE)."""
from __future__ import annotations

from typing import Any

FIXTURE_AS_OF = "2026-08-06T03:00:00Z"


def catalog() -> list[dict[str, Any]]:
    """Deterministic decision-detail fixtures. Never labeled LIVE."""
    return [
        {
            "case_id": "detail_demo_wait",
            "decision_id": "dec_pub18_wait_001",
            "mode": "DEMO_DATA",
            "chrome_label": "DEMO_DATA",
            "ai_posture": "WAIT",
            "data_freshness": "DEMO_DATA",
            "decision_timeline": {
                "summary": "OBSERVING → AI_ANALYZING → AI_SUGGESTION → WAIT",
                "stages": [
                    {"stage": "OBSERVING", "at": "2026-08-06T02:40:00Z"},
                    {"stage": "AI_ANALYZING", "at": "2026-08-06T02:45:00Z"},
                    {"stage": "AI_SUGGESTION", "at": "2026-08-06T02:50:00Z"},
                    {"stage": "WAIT", "at": "2026-08-06T02:55:00Z"},
                ],
                "availability": "DEMO_DATA",
            },
            "market_regime": {
                "label": "MIXED",
                "summary": "Mixed regime · no dominant trend confirmation",
                "availability": "DEMO_DATA",
            },
            "data_trust": {
                "band": "MODERATE",
                "summary": "Core public feeds present · derivatives provider still required",
                "availability": "DEMO_DATA",
            },
            "strategy_expert_label": {
                "label": "DEFENSIVE_NO_TRADE",
                "summary": "Defensive expert routing — suggestion only",
                "availability": "DEMO_DATA",
            },
            "evidence": [
                {
                    "summary": "Breadth not confirming breakout",
                    "polarity": "SUPPORTING",
                    "freshness": "DEMO_DATA",
                },
                {
                    "summary": "Volatility expansion risk flagged",
                    "polarity": "SUPPORTING",
                    "freshness": "DEMO_DATA",
                },
            ],
            "counter_evidence": [
                {
                    "summary": "Short-term momentum still positive",
                    "polarity": "CONTRADICTING",
                    "freshness": "DEMO_DATA",
                }
            ],
            "risk_reason": {
                "summary": "Cost / uncertainty band elevated for directional entry",
                "availability": "DEMO_DATA",
            },
            "why_wait_abstain": {
                "summary": "WAIT because confirmation and data-trust gates incomplete",
                "posture": "WAIT",
                "availability": "DEMO_DATA",
            },
            "historical_similarity_aggregate": {
                "summary": "12 similar public cases · 7 WAIT · 3 ABSTAIN · 2 LONG",
                "sample_count": 12,
                "availability": "DEMO_DATA",
                # Aggregates only — never exact proprietary thresholds.
            },
            "shadow_outcome": {
                "status": "OPEN_SHADOW",
                "summary": "Shadow decision open · no live fill · analysis only",
                "availability": "DEMO_DATA",
            },
            "process_classification_aggregate": {
                "summary": "Process: evidence_gap 42% · risk_block 33% · cost_block 25%",
                "availability": "DEMO_DATA",
            },
            "delayed_learning_summary": {
                "summary": "Delayed learning pending shadow close · public summary only",
                "status": "PENDING",
                "availability": "DEMO_DATA",
            },
        },
        {
            "case_id": "detail_demo_abstain",
            "decision_id": "dec_pub18_abstain_001",
            "mode": "DEMO_DATA",
            "chrome_label": "FIXTURE",
            "ai_posture": "ABSTAIN",
            "data_freshness": "FIXTURE",
            "decision_timeline": {
                "summary": "OBSERVING → RISK_REVIEW → ABSTAIN",
                "stages": [
                    {"stage": "OBSERVING", "at": "2026-08-06T01:10:00Z"},
                    {"stage": "RISK_REVIEW", "at": "2026-08-06T01:20:00Z"},
                    {"stage": "ABSTAIN", "at": "2026-08-06T01:25:00Z"},
                ],
                "availability": "FIXTURE",
            },
            "market_regime": {
                "label": "STRESS",
                "summary": "Stress regime · elevated uncertainty",
                "availability": "FIXTURE",
            },
            "data_trust": {
                "band": "DEGRADED",
                "summary": "Data trust degraded under stress fixture",
                "availability": "FIXTURE",
            },
            "strategy_expert_label": {
                "label": "DEFENSIVE_NO_TRADE",
                "summary": "Defensive expert · abstain posture",
                "availability": "FIXTURE",
            },
            "evidence": [
                {
                    "summary": "Liquidity thin across public venues (fixture)",
                    "polarity": "SUPPORTING",
                    "freshness": "FIXTURE",
                }
            ],
            "counter_evidence": [],
            "risk_reason": {
                "summary": "Risk governor advisory: abstain under stress band",
                "availability": "FIXTURE",
            },
            "why_wait_abstain": {
                "summary": "ABSTAIN because risk and data-trust gates blocked suggestion",
                "posture": "ABSTAIN",
                "availability": "FIXTURE",
            },
            "historical_similarity_aggregate": {
                "summary": "8 similar public stress cases · 6 ABSTAIN · 2 WAIT",
                "sample_count": 8,
                "availability": "FIXTURE",
            },
            "shadow_outcome": {
                "status": "CLOSED_NO_FILL",
                "summary": "Shadow closed without fill · process classified as risk_block",
                "availability": "FIXTURE",
            },
            "process_classification_aggregate": {
                "summary": "Process: risk_block 62% · evidence_gap 25% · cost_block 13%",
                "availability": "FIXTURE",
            },
            "delayed_learning_summary": {
                "summary": "Delayed learning: public process note recorded · no private lesson",
                "status": "RECORDED_PUBLIC",
                "availability": "FIXTURE",
            },
        },
        {
            "case_id": "detail_provider_required",
            "decision_id": "dec_pub18_provider_required",
            "mode": "PROVIDER_REQUIRED",
            "chrome_label": "PROVIDER_REQUIRED",
            "ai_posture": "ABSTAIN",
            "data_freshness": "PROVIDER_REQUIRED",
            "decision_timeline": {
                "summary": "PROVIDER_REQUIRED",
                "stages": [],
                "availability": "PROVIDER_REQUIRED",
            },
            "market_regime": {
                "label": "PROVIDER_REQUIRED",
                "summary": "PROVIDER_REQUIRED",
                "availability": "PROVIDER_REQUIRED",
            },
            "data_trust": {
                "band": "PROVIDER_REQUIRED",
                "summary": "PROVIDER_REQUIRED",
                "availability": "PROVIDER_REQUIRED",
            },
            "strategy_expert_label": {
                "label": "UNAVAILABLE",
                "summary": "PROVIDER_REQUIRED",
                "availability": "PROVIDER_REQUIRED",
            },
            "evidence": [],
            "counter_evidence": [],
            "risk_reason": {
                "summary": "PROVIDER_REQUIRED",
                "availability": "PROVIDER_REQUIRED",
            },
            "why_wait_abstain": {
                "summary": "ABSTAIN · provider binding required before suggestion",
                "posture": "ABSTAIN",
                "availability": "PROVIDER_REQUIRED",
            },
            "historical_similarity_aggregate": {
                "summary": "PROVIDER_REQUIRED",
                "sample_count": None,
                "availability": "PROVIDER_REQUIRED",
            },
            "shadow_outcome": {
                "status": "UNAVAILABLE",
                "summary": "PROVIDER_REQUIRED",
                "availability": "PROVIDER_REQUIRED",
            },
            "process_classification_aggregate": {
                "summary": "PROVIDER_REQUIRED",
                "availability": "PROVIDER_REQUIRED",
            },
            "delayed_learning_summary": {
                "summary": "PROVIDER_REQUIRED",
                "status": "UNAVAILABLE",
                "availability": "PROVIDER_REQUIRED",
            },
        },
        {
            "case_id": "detail_stale",
            "decision_id": "dec_pub18_stale_001",
            "mode": "DEMO_DATA",
            "chrome_label": "STALE",
            "ai_posture": "WAIT",
            "data_freshness": "STALE",
            "decision_timeline": {
                "summary": "Last public update aged beyond freshness band",
                "stages": [
                    {"stage": "AI_SUGGESTION", "at": "2026-08-05T12:00:00Z"},
                    {"stage": "WAIT", "at": "2026-08-05T12:05:00Z"},
                ],
                "availability": "STALE",
            },
            "market_regime": {
                "label": "MIXED",
                "summary": "Regime label retained · freshness STALE",
                "availability": "STALE",
            },
            "data_trust": {
                "band": "STALE",
                "summary": "Data trust marked STALE — not shown as LIVE",
                "availability": "STALE",
            },
            "strategy_expert_label": {
                "label": "DEFENSIVE_NO_TRADE",
                "summary": "Expert label retained under STALE chrome",
                "availability": "STALE",
            },
            "evidence": [
                {
                    "summary": "Prior breadth observation (stale)",
                    "polarity": "SUPPORTING",
                    "freshness": "STALE",
                }
            ],
            "counter_evidence": [
                {
                    "summary": "Prior momentum observation (stale)",
                    "polarity": "CONTRADICTING",
                    "freshness": "STALE",
                }
            ],
            "risk_reason": {
                "summary": "Risk reason retained · do not act on STALE surface",
                "availability": "STALE",
            },
            "why_wait_abstain": {
                "summary": "WAIT retained · refresh required before any suggestion change",
                "posture": "WAIT",
                "availability": "STALE",
            },
            "historical_similarity_aggregate": {
                "summary": "Aggregate unchanged · freshness STALE",
                "sample_count": 12,
                "availability": "STALE",
            },
            "shadow_outcome": {
                "status": "OPEN_SHADOW",
                "summary": "Shadow still open · STALE public view",
                "availability": "STALE",
            },
            "process_classification_aggregate": {
                "summary": "Process aggregate unchanged · STALE",
                "availability": "STALE",
            },
            "delayed_learning_summary": {
                "summary": "Delayed learning waiting on fresh close event",
                "status": "PENDING",
                "availability": "STALE",
            },
        },
        {
            "case_id": "detail_unavailable",
            "decision_id": "dec_pub18_unavailable",
            "mode": "UNAVAILABLE",
            "chrome_label": "UNAVAILABLE",
            "ai_posture": "ABSTAIN",
            "data_freshness": "UNAVAILABLE",
            "decision_timeline": {
                "summary": "UNAVAILABLE",
                "stages": [],
                "availability": "UNAVAILABLE",
            },
            "market_regime": {
                "label": "UNAVAILABLE",
                "summary": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
            },
            "data_trust": {
                "band": "UNAVAILABLE",
                "summary": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
            },
            "strategy_expert_label": {
                "label": "UNAVAILABLE",
                "summary": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
            },
            "evidence": [],
            "counter_evidence": [],
            "risk_reason": {
                "summary": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
            },
            "why_wait_abstain": {
                "summary": "ABSTAIN · decision detail unavailable",
                "posture": "ABSTAIN",
                "availability": "UNAVAILABLE",
            },
            "historical_similarity_aggregate": {
                "summary": "UNAVAILABLE",
                "sample_count": None,
                "availability": "UNAVAILABLE",
            },
            "shadow_outcome": {
                "status": "UNAVAILABLE",
                "summary": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
            },
            "process_classification_aggregate": {
                "summary": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
            },
            "delayed_learning_summary": {
                "summary": "UNAVAILABLE",
                "status": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
            },
        },
    ]
