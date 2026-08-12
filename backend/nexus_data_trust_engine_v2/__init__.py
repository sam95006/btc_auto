"""V17-F Data Quality and Trust Engine V2.

System-wide Data Trust Score from freshness, completeness, cross-source
agreement, schema validity, timestamp integrity, revision uncertainty,
license status, market coverage, microstructure availability, and anomaly rate.

Outputs: TRUSTED | USABLE_WITH_LIMITS | DEGRADED | STALE | CONFLICTED |
LICENSE_BLOCKED | UNAVAILABLE.

Hard rule: Data Trust dominates AI confidence — DEGRADED (and worse) force
WAIT / ABSTAIN / BLOCK even when AI confidence is 99%.
"""
from __future__ import annotations

from backend.nexus_data_trust_engine_v2.engine import (
    apply_ai_suggestion,
    compute_trust_score,
    evaluate_inputs,
    evaluate_raw,
)
from backend.nexus_data_trust_engine_v2.hard_bans import hard_ban_probe_matrix

__all__ = [
    "apply_ai_suggestion",
    "compute_trust_score",
    "evaluate_inputs",
    "evaluate_raw",
    "hard_ban_probe_matrix",
]
