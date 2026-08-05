"""Shared Feature Registry contracts — leaf module (no registry/seed imports).

Breaks feature_seed ↔ registry cycles by hosting Namespace + FeatureDefinition
as shared contracts. Registry implements storage; seed registers via DI.
"""
from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


def utc_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class Namespace:
    NATURAL = "NATURAL"
    SHADOW = "SHADOW"
    REPLAY_VALIDATION = "REPLAY_VALIDATION"
    VALIDATION = "VALIDATION"

    _ALL = {NATURAL, SHADOW, REPLAY_VALIDATION, VALIDATION}

    @classmethod
    def valid(cls, ns: str) -> bool:
        return ns in cls._ALL


@dataclass
class FeatureDefinition:
    """Metadata about a registered feature."""

    name: str
    namespace: str
    description: str = ""
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)
    experimental: bool = False
    registered_at: str = field(default_factory=utc_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class FeatureRegistryProtocol(Protocol):
    """DI surface used by feature_seed — avoids importing the concrete registry."""

    def register(
        self,
        name: str,
        namespace: str = ...,
        *,
        description: str = ...,
        version: str = ...,
        tags: list[str] | None = ...,
        experimental: bool = ...,
    ) -> FeatureDefinition: ...

    def list_definitions(self, namespace: Optional[str] = None) -> list[FeatureDefinition]: ...
