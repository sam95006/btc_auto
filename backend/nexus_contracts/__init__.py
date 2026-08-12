"""NEXUS contract authority surface (V11 Lane H).

Canonical registry and machine-readable authority declarations for Private Core.
Does not own runtime execution — only contracts, authority maps, and drift metadata.
"""
from __future__ import annotations

from backend.nexus_contracts.authority_registry import (
    AUTHORITY_DOMAINS,
    REGISTRY_SCHEMA,
    AuthorityRecord,
    build_canonical_registry,
    get_authority,
    list_authorities,
)

__all__ = [
    "AUTHORITY_DOMAINS",
    "REGISTRY_SCHEMA",
    "AuthorityRecord",
    "build_canonical_registry",
    "get_authority",
    "list_authorities",
]
