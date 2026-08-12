"""Tests for canonical authority registry."""
from __future__ import annotations

from backend.nexus_contracts.authority_registry import (
    AUTHORITY_DOMAINS,
    build_canonical_registry,
    get_authority,
    list_authorities,
)


def test_all_domains_registered():
    regs = list_authorities()
    assert {r.domain for r in regs} == set(AUTHORITY_DOMAINS)


def test_exactly_one_canonical_per_domain():
    for rec in list_authorities():
        assert rec.canonical_module
        assert rec.canonical_symbol
        assert rec.authority_id


def test_no_delete_now_flags():
    for rec in list_authorities():
        for c in rec.competitors:
            assert c.delete_now is False


def test_registry_payload_schema():
    payload = build_canonical_registry()
    assert payload["schema"] == "nexus_canonical_authority_registry_v1"
    assert payload["summary"]["domain_count"] == len(AUTHORITY_DOMAINS)
    assert "cost" in payload["by_domain"]
    assert payload["by_domain"]["execution"]["canonical_module"].startswith(
        "backend.nexus_execution"
    )


def test_get_authority():
    auth = get_authority("provider_retry")
    assert auth.canonical_module == "backend.nexus_provider.retry_policy"
