"""NEXUS Phase 6.4 — Shadow Feature Evaluation.

ShadowFeatureEvaluation computes a hypothetical shadow score/decision for
research purposes WITHOUT mutating any production fields:
  - candidate score
  - candidate side
  - candidate ranking
  - risk limits
  - natural PAPER order eligibility

Shadow evaluations are persisted to research store table key
`shadow_feature_evaluations` via store.append() when a store is available.

After every evaluation, production fields are asserted unchanged.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import threading
import time
import uuid
from typing import Any, Optional

RESEARCH_ONLY = True
_SHADOW_TABLE = "shadow_feature_evaluations"


def _utc_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# Production fields that must NEVER be mutated by shadow evaluation
_PROTECTED_FIELDS = frozenset({
    "score",
    "side",
    "rank",
    "ranking",
    "risk_limit",
    "risk_blocked",
    "order_eligible",
    "paper_eligible",
    "natural_eligible",
    "confidence",
})


class ProductionMutationError(RuntimeError):
    """Raised if shadow evaluation has mutated production fields."""


def _extract_protected(candidate: dict[str, Any]) -> dict[str, Any]:
    """Extract a snapshot of protected fields for before/after comparison."""
    return {k: copy.deepcopy(candidate.get(k)) for k in _PROTECTED_FIELDS if k in candidate}


def _assert_unchanged(
    before: dict[str, Any],
    after: dict[str, Any],
    context: str = "",
) -> None:
    """Raise ProductionMutationError if any protected field changed."""
    for key, before_val in before.items():
        after_val = after.get(key)
        if before_val != after_val:
            raise ProductionMutationError(
                f"Shadow evaluation mutated protected field '{key}': "
                f"{before_val!r} → {after_val!r}. Context: {context}"
            )
    # Also check for new keys added to after that weren't in before
    for key in after:
        if key in _PROTECTED_FIELDS and key not in before:
            raise ProductionMutationError(
                f"Shadow evaluation added protected field '{key}' that was not in original. "
                f"Context: {context}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# ShadowFeatureEvaluation
# ─────────────────────────────────────────────────────────────────────────────

class ShadowFeatureEvaluation:
    """Compute shadow feature scores without mutating production candidates.

    Usage
    -----
    evaluator = ShadowFeatureEvaluation(store=research_store)

    result = evaluator.evaluate(
        candidate=candidate_dict,
        feature_snapshot=snapshot,
        decision_time=time.time(),
    )

    # result["shadowScore"] is the research-only score
    # production candidate is provably unchanged
    """

    def __init__(self, store: Any = None, namespace: str = "SHADOW") -> None:
        """
        Parameters
        ----------
        store:
            Optional research store with .append(table, record) method.
        namespace:
            Feature namespace to use (default SHADOW).
        """
        self._store = store
        self.namespace = namespace
        self._lock = threading.RLock()
        self._eval_count = 0
        self._error_count = 0

    def evaluate(
        self,
        candidate: dict[str, Any],
        feature_snapshot: Any,  # FeatureSnapshot or dict
        decision_time: Optional[float] = None,
        scorer: Optional[Any] = None,
        extra_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Evaluate a shadow score for a candidate.

        The candidate is NEVER modified. All shadow scoring is done on
        a deep copy and the original is verified unchanged after evaluation.

        Parameters
        ----------
        candidate:
            Production candidate dict (must NOT be mutated).
        feature_snapshot:
            FeatureSnapshot or dict of feature observations.
        decision_time:
            Unix epoch seconds for the evaluation moment.
        scorer:
            Optional callable(candidate_copy, features) → float in [-1, 1].
            If None, a default heuristic scorer is used.
        extra_context:
            Optional additional research context dict (appended to record).

        Returns
        -------
        dict with:
            shadowScore: float or None
            shadowDecision: SHADOW_LONG / SHADOW_SHORT / SHADOW_NEUTRAL
            featureHash: sha256 of snapshot
            evaluationId: uuid
            productionUnchanged: bool (always True or exception raised)
        """
        if decision_time is None:
            decision_time = time.time()
        eval_id = str(uuid.uuid4())
        # Snapshot production protected fields BEFORE evaluation
        before_protected = _extract_protected(candidate)
        # Work on a deep copy — never touch original
        candidate_copy = copy.deepcopy(candidate)
        error: Optional[str] = None
        shadow_score: Optional[float] = None
        shadow_decision = "SHADOW_NEUTRAL"
        feature_hash: Optional[str] = None
        feature_values: dict[str, Any] = {}

        try:
            # Extract features from snapshot
            if hasattr(feature_snapshot, "observations"):
                for obs in feature_snapshot.observations:
                    if obs.quality not in ("UNAVAILABLE", "EXPERIMENTAL"):
                        feature_values[obs.feature_name] = obs.value
                feature_hash = getattr(feature_snapshot, "snapshot_hash", None)
            elif isinstance(feature_snapshot, dict):
                feature_values = {
                    k: v for k, v in feature_snapshot.items()
                    if v is not None
                }
                raw = json.dumps(feature_snapshot, sort_keys=True, separators=(",", ":"), default=str)
                feature_hash = hashlib.sha256(raw.encode()).hexdigest()

            # Compute shadow score
            if scorer is not None:
                shadow_score = float(scorer(candidate_copy, feature_values))
            else:
                shadow_score = _default_heuristic_scorer(candidate_copy, feature_values)

            if shadow_score is not None:
                if shadow_score > 0.2:
                    shadow_decision = "SHADOW_LONG"
                elif shadow_score < -0.2:
                    shadow_decision = "SHADOW_SHORT"
                else:
                    shadow_decision = "SHADOW_NEUTRAL"

        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            self._error_count += 1

        # Verify production fields UNCHANGED after evaluation
        after_protected = _extract_protected(candidate)
        _assert_unchanged(before_protected, after_protected, context=eval_id)

        result = {
            "evaluationId": eval_id,
            "namespace": self.namespace,
            "shadowScore": shadow_score,
            "shadowDecision": shadow_decision,
            "featureHash": feature_hash,
            "featureCount": len(feature_values),
            "productionUnchanged": True,
            "candidateSymbol": candidate.get("symbol"),
            "candidateSide": candidate.get("side"),  # READ ONLY — not mutated
            "decisionTime": decision_time,
            "error": error,
            "extraContext": extra_context or {},
            "researchOnly": True,
            "generatedAt": _utc_iso(),
        }

        # Persist to research store if available
        self._maybe_persist(result)

        with self._lock:
            self._eval_count += 1

        return result

    def _maybe_persist(self, record: dict[str, Any]) -> None:
        """Append evaluation record to research store if available."""
        if self._store is None:
            return
        try:
            append_fn = getattr(self._store, "append", None)
            if callable(append_fn):
                append_fn(_SHADOW_TABLE, record)
        except Exception:  # noqa: BLE001
            pass  # persistence is best-effort for research store

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "namespace": self.namespace,
                "evaluationCount": self._eval_count,
                "errorCount": self._error_count,
                "storeAvailable": self._store is not None,
                "researchOnly": True,
            }


# ─────────────────────────────────────────────────────────────────────────────
# Default heuristic scorer (for testing / fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _default_heuristic_scorer(
    candidate: dict[str, Any],
    features: dict[str, Any],
) -> Optional[float]:
    """A simple transparent heuristic scorer for shadow evaluation.

    Returns a score in [-1, 1] based on available feature signals.
    NOT a trading signal — research/shadow only.
    """
    scores: list[float] = []

    rsi = features.get("rsi_14") or features.get("rsi")
    if rsi is not None:
        try:
            r = float(rsi.get("value") if isinstance(rsi, dict) else rsi)
            # Normalize RSI [0,100] → [-1,1]: 50 → 0, 70 → 0.4, 30 → -0.4
            scores.append((r - 50.0) / 50.0)
        except (TypeError, ValueError):
            pass

    macd_data = features.get("macd")
    if isinstance(macd_data, dict):
        hist = macd_data.get("histogram")
        if hist is not None:
            try:
                # Clip histogram to ±0.5 signal
                scores.append(max(-1.0, min(1.0, float(hist) * 10.0)))
            except (TypeError, ValueError):
                pass

    trend = features.get("trend_slope_20") or features.get("trend_slope")
    if isinstance(trend, dict):
        ns = trend.get("normalizedSlope")
        if ns is not None:
            try:
                scores.append(max(-1.0, min(1.0, float(ns) * 100.0)))
            except (TypeError, ValueError):
                pass

    if not scores:
        return None
    return sum(scores) / len(scores)


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_EVALUATOR_LOCK = threading.Lock()
_EVALUATOR: Optional[ShadowFeatureEvaluation] = None


def get_shadow_evaluator() -> ShadowFeatureEvaluation:
    global _EVALUATOR
    if _EVALUATOR is None:
        with _EVALUATOR_LOCK:
            if _EVALUATOR is None:
                store = None
                try:
                    from backend.nexus_research.storage import get_research_store
                    store = get_research_store()
                except Exception:  # noqa: BLE001
                    pass
                _EVALUATOR = ShadowFeatureEvaluation(store=store)
    return _EVALUATOR
