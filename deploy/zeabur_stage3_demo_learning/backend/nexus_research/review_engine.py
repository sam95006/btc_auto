"""Phase 6 Gate D — Review Engine.

Wraps the DecisionOrchestrator (roles.py) and the ResearchReasoningProvider
(reasoning_provider.py) to expose the current review mode to the UI.

The review engine:
  - Always runs the deterministic role assessment pipeline (never skipped).
  - Optionally enriches the output with the reasoning provider result
    (RULES_ONLY / LLM_ASSISTED / LLM_UNAVAILABLE / DEGRADED).
  - Never modifies the orchestrator's risk verdict or decision status.
  - Never passes private account data to the reasoning provider.
  - Exposes review_mode, provider_name, and provider_status for the UI.

UI must display review mode honestly:
  RULES_ONLY     → "規則式分析" (not labelled as generative AI)
  LLM_ASSISTED   → "LLM 輔助分析" (with provider name)
  LLM_UNAVAILABLE→ "LLM 不可用 → 規則式" (transparent fallback)
  DEGRADED       → "降級模式 → 規則式" (circuit breaker open)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True


def _ts() -> int:
    return int(time.time() * 1000)


class ReviewEngine:
    """Orchestrates role analysis + reasoning provider for Gate D review."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._review_count = 0
        self._last_review_at: int | None = None

    @property
    def _orchestrator(self):
        from backend.nexus_research.roles import DecisionOrchestrator
        return DecisionOrchestrator()

    @property
    def _provider(self):
        from backend.nexus_research.reasoning_provider import get_reasoning_provider
        return get_reasoning_provider()

    def run_review(
        self,
        case_id: str,
        candidate: dict[str, Any],
        context: dict[str, Any] | None = None,
        enrich_with_reasoning: bool = True,
    ) -> dict[str, Any]:
        """Run full role review + optional reasoning provider enrichment.

        The orchestrator decision (risk verdict, decisionStatus) is NEVER
        modified by the reasoning provider — it only adds a 'reasoning' field.

        Args:
            case_id: Review case identifier.
            candidate: Public market candidate snapshot (no private data).
            context: Additional context (activeCases, priorOutcomes, etc.).
            enrich_with_reasoning: If True, call reasoning provider for enrichment.

        Returns:
            Combined review result with roleDecision + reasoning fields.
        """
        context = context or {}

        # Step 1: Run deterministic role assessment (always, never skipped)
        try:
            role_decision = self._orchestrator.run(
                case_id=case_id,
                candidate=candidate,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[review_engine] orchestrator error: %s", exc)
            role_decision = {
                "caseId": case_id,
                "decisionStatus": "ERROR",
                "analysisMode": "RULES",
                "error": str(exc),
                "researchOnly": True,
            }

        # Step 2: Optionally enrich with reasoning provider
        reasoning_result: dict[str, Any] = {}
        provider_mode = "RULES_ONLY"
        provider_name = "none"
        if enrich_with_reasoning:
            try:
                provider = self._provider
                provider_mode = provider.mode
                provider_name = provider.provider_name

                # Build evidence pack (public market data only — no private fields)
                evidence_pack = self._build_evidence_pack(candidate, role_decision)
                reasoning_result = provider.reason(evidence_pack)

            except Exception as exc:  # noqa: BLE001
                logger.warning("[review_engine] reasoning provider error: %s", exc)
                reasoning_result = {"error": str(exc), "mode": "RULES_ONLY"}

        with self._lock:
            self._review_count += 1
            self._last_review_at = _ts()

        result = {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "caseId": case_id,
            "reviewMode": provider_mode,
            "providerName": provider_name,
            "roleDecision": role_decision,
            "reasoning": reasoning_result,
            "decisionStatus": role_decision.get("decisionStatus"),
            "symbol": role_decision.get("symbol"),
            "direction": role_decision.get("direction"),
            "reviewedAt": _ts(),
            # Important: reasoning provider NEVER modifies these values
            "_invariant": "reasoning_provider_does_not_modify_risk_verdict_or_decision_status",
        }
        return result

    def _build_evidence_pack(
        self,
        candidate: dict[str, Any],
        role_decision: dict[str, Any],
    ) -> dict[str, Any]:
        """Build evidence pack with public market data only.

        MUST NOT include private account data (balances, API keys, etc.).
        """
        allowed_candidate_fields = {
            "symbol", "side", "direction", "score", "totalScore",
            "change24hPct", "fundingRate", "oiChange5mPct", "priceChange5mPct",
            "spreadBps", "riskScore", "stage", "collecting",
            "sector", "regime",
        }
        safe_candidate = {k: v for k, v in candidate.items() if k in allowed_candidate_fields}

        # Summary of role decisions (non-private)
        assessments = role_decision.get("assessments") or []
        assessment_summary = [
            {
                "role": a.get("role"),
                "verdict": a.get("verdict"),
                "confidence": a.get("confidence"),
                "flags": a.get("flags", []),
            }
            for a in assessments
        ]

        return {
            "symbol": safe_candidate.get("symbol", "UNKNOWN"),
            "analysisMode": "RESEARCH",
            "evidenceIds": [
                f"role_{a['role'].lower()}" for a in assessment_summary if a.get("role")
            ],
            "candidateScore": safe_candidate.get("score"),
            "riskFlags": [
                f for a in assessment_summary for f in (a.get("flags") or [])
            ],
            "roleVerdicts": {a["role"]: a["verdict"] for a in assessment_summary if a.get("role")},
            "decisionStatus": role_decision.get("decisionStatus"),
            # Public market data
            "change24hPct": safe_candidate.get("change24hPct"),
            "fundingRate": safe_candidate.get("fundingRate"),
            "sector": safe_candidate.get("sector"),
            "regime": safe_candidate.get("regime"),
        }

    def status(self) -> dict[str, Any]:
        try:
            provider = self._provider
            provider_mode = provider.mode
            provider_name = provider.provider_name
            provider_status = provider.status()
        except Exception as exc:  # noqa: BLE001
            provider_mode = "RULES_ONLY"
            provider_name = "none"
            provider_status = {"error": str(exc)}

        with self._lock:
            review_count = self._review_count
            last_review_at = self._last_review_at

        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "reviewMode": provider_mode,
            "providerName": provider_name,
            "reviewCount": review_count,
            "lastReviewAt": last_review_at,
            "providerStatus": provider_status,
            # UI transparency fields
            "uiModeLabel": _mode_ui_label(provider_mode),
            "fabricatedChat": False,
            "generatedAt": _ts(),
        }


def _mode_ui_label(mode: str) -> str:
    """Return honest UI label for review mode."""
    labels = {
        "RULES_ONLY": "規則式分析（非生成式 AI）",
        "LLM_ASSISTED": "LLM 輔助分析",
        "LLM_UNAVAILABLE": "LLM 不可用 → 規則式分析",
        "DEGRADED": "降級模式（錯誤回退）→ 規則式分析",
    }
    return labels.get(mode, f"未知模式: {mode}")


# ── Singleton ─────────────────────────────────────────────────────────────────
_ENGINE: ReviewEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_review_engine() -> ReviewEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = ReviewEngine()
            logger.info("[review_engine] ReviewEngine initialised (researchOnly=true)")
        return _ENGINE
