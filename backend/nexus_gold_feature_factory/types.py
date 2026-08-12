"""V17-G Gold Feature Factory — typed observation records."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class FeatureObservation:
    """One reproducible gold feature observation with mandatory lineage metadata."""

    feature_id: str
    value: Any
    quality: str  # COMPLETE | PARTIAL | UNAVAILABLE | MISSING
    feature_version: str
    source_lineage: tuple[str, ...]
    as_of: int  # ms epoch UTC (PIT cutoff)
    available_at: Optional[int]  # ms epoch UTC when inputs were received
    lookback: int  # bars or window units
    normalization: str
    missing_policy: str
    license_scope: str
    calculation_hash: str
    definition: str = ""
    units: str = ""
    reason: Optional[str] = None
    stale: bool = False
    staleness_ms: Optional[int] = None
    predictive_edge_claimed: bool = False
    evidence_class: str = "fixture"
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source_lineage"] = list(self.source_lineage)
        return d


REQUIRED_OBS_KEYS = (
    "feature_id",
    "value",
    "quality",
    "feature_version",
    "source_lineage",
    "as_of",
    "available_at",
    "lookback",
    "normalization",
    "missing_policy",
    "license_scope",
    "calculation_hash",
)
