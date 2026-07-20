"""NEXUS Phase 6.4 — Feature Registry.

Provides:
- FeatureDefinition  — metadata about a named feature
- FeatureObservation — single data point for a feature at a point in time
- FeatureSnapshot    — immutable, point-in-time consistent collection of observations
- FeatureRegistry    — register/get/list features; build snapshots

Namespaces:
  NATURAL            — production candidate pipeline
  SHADOW             — shadow evaluation (read-only, no production mutation)
  REPLAY_VALIDATION  — replay / backtesting validation
  VALIDATION         — dry-run or schema validation

Point-in-time guarantee:
  Snapshots only include observations with event_time <= decision_time.

Snapshot integrity:
  sha256 of canonical JSON (sorted keys, no whitespace) of all included observations.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Namespace constants
# ─────────────────────────────────────────────────────────────────────────────

class Namespace:
    NATURAL = "NATURAL"
    SHADOW = "SHADOW"
    REPLAY_VALIDATION = "REPLAY_VALIDATION"
    VALIDATION = "VALIDATION"

    _ALL = {NATURAL, SHADOW, REPLAY_VALIDATION, VALIDATION}

    @classmethod
    def valid(cls, ns: str) -> bool:
        return ns in cls._ALL


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FeatureDefinition:
    """Metadata about a registered feature."""
    name: str
    namespace: str
    description: str = ""
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)
    experimental: bool = False
    registered_at: str = field(default_factory=lambda: _utc_iso())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FeatureObservation:
    """A single observed value for a feature at a specific event_time."""
    feature_name: str
    namespace: str
    value: Any
    quality: str                  # COMPLETE / INCOMPLETE / UNAVAILABLE / EXPERIMENTAL
    event_time: float             # unix epoch seconds (UTC)
    reason: Optional[str] = None  # explanation for UNAVAILABLE / EXPERIMENTAL
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "namespace": self.namespace,
            "value": self.value,
            "quality": self.quality,
            "event_time": self.event_time,
            "reason": self.reason,
            "metadata": self.metadata,
        }


@dataclass
class FeatureSnapshot:
    """Immutable point-in-time snapshot of feature observations."""
    decision_time: float
    namespace: str
    observations: list[FeatureObservation]
    snapshot_hash: str = ""
    created_at: str = field(default_factory=lambda: _utc_iso())

    def __post_init__(self) -> None:
        if not self.snapshot_hash:
            self.snapshot_hash = _compute_hash(self.observations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_time": self.decision_time,
            "namespace": self.namespace,
            "observations": [o.to_dict() for o in self.observations],
            "snapshot_hash": self.snapshot_hash,
            "created_at": self.created_at,
            "count": len(self.observations),
        }

    def get(self, feature_name: str) -> Optional[FeatureObservation]:
        """Return the observation for a given feature_name, or None."""
        for obs in self.observations:
            if obs.feature_name == feature_name:
                return obs
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _utc_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON — sorted keys, no extra whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _compute_hash(observations: list[FeatureObservation]) -> str:
    """sha256 of canonical JSON of sorted observations."""
    data = sorted(
        [o.to_dict() for o in observations],
        key=lambda d: (d["feature_name"], d["event_time"]),
    )
    raw = _canonical_json(data)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# FeatureRegistry
# ─────────────────────────────────────────────────────────────────────────────

class FeatureRegistry:
    """Thread-safe feature definition and observation store."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._definitions: dict[str, FeatureDefinition] = {}
        # observations keyed by (name, namespace)
        self._observations: list[FeatureObservation] = []

    # ── Registration ──────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        namespace: str = Namespace.NATURAL,
        *,
        description: str = "",
        version: str = "1.0",
        tags: list[str] | None = None,
        experimental: bool = False,
    ) -> FeatureDefinition:
        """Register a feature definition. Idempotent — re-registration overwrites."""
        if not Namespace.valid(namespace):
            raise ValueError(f"Unknown namespace: {namespace!r}. Must be one of {Namespace._ALL}")
        defn = FeatureDefinition(
            name=name,
            namespace=namespace,
            description=description,
            version=version,
            tags=tags or [],
            experimental=experimental,
        )
        with self._lock:
            self._definitions[f"{namespace}:{name}"] = defn
        return defn

    def get_definition(self, name: str, namespace: str = Namespace.NATURAL) -> Optional[FeatureDefinition]:
        with self._lock:
            return self._definitions.get(f"{namespace}:{name}")

    def list_definitions(self, namespace: Optional[str] = None) -> list[FeatureDefinition]:
        with self._lock:
            if namespace is None:
                return list(self._definitions.values())
            return [d for d in self._definitions.values() if d.namespace == namespace]

    # ── Observations ──────────────────────────────────────────────────────────

    def record(self, observation: FeatureObservation) -> None:
        """Append an observation. Does not check against registered definitions."""
        with self._lock:
            self._observations.append(observation)

    def record_value(
        self,
        feature_name: str,
        value: Any,
        event_time: float,
        quality: str = "COMPLETE",
        namespace: str = Namespace.NATURAL,
        reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> FeatureObservation:
        obs = FeatureObservation(
            feature_name=feature_name,
            namespace=namespace,
            value=value,
            quality=quality,
            event_time=event_time,
            reason=reason,
            metadata=metadata or {},
        )
        self.record(obs)
        return obs

    # ── Snapshot builder ──────────────────────────────────────────────────────

    def build_snapshot(
        self,
        decision_time: float,
        namespace: str = Namespace.NATURAL,
        feature_names: Optional[list[str]] = None,
    ) -> FeatureSnapshot:
        """Build a point-in-time snapshot using only observations with event_time <= decision_time.

        If `feature_names` is provided, only those features are included.
        Per feature, the latest observation at or before decision_time is used.
        """
        with self._lock:
            all_obs = list(self._observations)
        eligible = [
            o for o in all_obs
            if o.namespace == namespace and o.event_time <= decision_time
            and (feature_names is None or o.feature_name in feature_names)
        ]
        # Keep only latest per feature_name
        latest: dict[str, FeatureObservation] = {}
        for obs in eligible:
            existing = latest.get(obs.feature_name)
            if existing is None or obs.event_time > existing.event_time:
                latest[obs.feature_name] = obs
        selected = sorted(latest.values(), key=lambda o: o.feature_name)
        return FeatureSnapshot(
            decision_time=decision_time,
            namespace=namespace,
            observations=selected,
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "definitionCount": len(self._definitions),
                "observationCount": len(self._observations),
                "namespaces": list({d.namespace for d in self._definitions.values()}),
            }

    def clear_observations(self) -> None:
        """For testing / reset only."""
        with self._lock:
            self._observations.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Global singleton
# ─────────────────────────────────────────────────────────────────────────────

_REGISTRY_LOCK = threading.Lock()
_REGISTRY: Optional[FeatureRegistry] = None


def get_feature_registry() -> FeatureRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        with _REGISTRY_LOCK:
            if _REGISTRY is None:
                _REGISTRY = FeatureRegistry()
    return _REGISTRY
