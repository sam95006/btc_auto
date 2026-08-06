"""Registry + catalog document for PUB17-A Global Market Source Contracts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_pub17_global_market_contracts.constants import (
    ARTIFACT_REL,
    BRANCH,
    CATALOG_REL,
    CONTRACT_STATUSES,
    HARD_BANS,
    LANE,
    LANE_NAME,
    REQUIRED_CONTRACT_FIELDS,
    REQUIRED_DOMAINS,
    SCHEMA,
    SCHEMA_REL,
    SCHEMA_VERSION,
)
from backend.nexus_pub17_global_market_contracts.contracts import source_contracts
from backend.nexus_pub17_global_market_contracts.dto import (
    build_all_normalized_dtos,
    validate_dto,
)


class GlobalMarketContractError(ValueError):
    """Fail-closed contract registry error."""


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(contract, dict):
        return ["contract_not_object"]
    for key in REQUIRED_CONTRACT_FIELDS:
        if key not in contract:
            errors.append(f"missing_contract_field:{key}")
    domain = contract.get("domain")
    if domain not in REQUIRED_DOMAINS:
        errors.append(f"unknown_domain:{domain}")
    status = contract.get("status")
    if status not in CONTRACT_STATUSES:
        errors.append(f"bad_status:{status}")
    if contract.get("read_only") is False:
        errors.append("not_read_only")
    if contract.get("exchange_write") is True:
        errors.append("exchange_write_true")
    if status == "PROVIDER_REQUIRED":
        if contract.get("supports_live_bind") is True:
            errors.append("provider_required_supports_live_bind")
        if contract.get("endpoint") not in (None, "", "none"):
            # Allow None only — claiming an endpoint while PROVIDER_REQUIRED is dishonest.
            errors.append("provider_required_has_endpoint")
    if status == "CONTRACT_READY":
        if not contract.get("endpoint"):
            errors.append("contract_ready_missing_endpoint")
        if not contract.get("provider") or contract.get("provider") == "none":
            errors.append("contract_ready_missing_provider")
        vis = contract.get("license_visibility") or {}
        if not isinstance(vis, dict) or not vis.get("license_type"):
            errors.append("contract_ready_missing_license_visibility")
        prov = contract.get("provenance") or {}
        if not isinstance(prov, dict) or not prov.get("origin"):
            errors.append("contract_ready_missing_provenance")
    vis = contract.get("license_visibility")
    if vis is not None and not isinstance(vis, dict):
        errors.append("license_visibility_not_object")
    elif isinstance(vis, dict):
        if "visibility" not in vis:
            errors.append("license_visibility_missing_visibility")
        if vis.get("visibility") != "PUBLIC_VISIBLE":
            # License posture must be visible on the public contract surface.
            errors.append("license_visibility_not_public_visible")
    return errors


def validate_catalog(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("schema") != SCHEMA:
        errors.append("bad_schema")
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append("bad_schema_version")
    if doc.get("lane") != LANE:
        errors.append("bad_lane")
    contracts = doc.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        errors.append("contracts_missing_or_empty")
        return errors
    seen_domains: set[str] = set()
    for i, c in enumerate(contracts):
        if not isinstance(c, dict):
            errors.append(f"contract[{i}]_not_object")
            continue
        domain = str(c.get("domain") or "")
        if domain in seen_domains:
            errors.append(f"duplicate_domain:{domain}")
        seen_domains.add(domain)
        for err in validate_contract(c):
            errors.append(f"contract[{domain or i}]:{err}")
    missing = sorted(set(REQUIRED_DOMAINS) - seen_domains)
    if missing:
        errors.append(f"missing_domains:{missing}")
    dtos = doc.get("normalized_dtos")
    if isinstance(dtos, list):
        for i, dto in enumerate(dtos):
            for err in validate_dto(dto):
                errors.append(f"dto[{i}]:{err}")
    return errors


class GlobalMarketSourceRegistry:
    """In-memory registry of global market source contracts + normalized DTOs."""

    def __init__(self, contracts: list[dict[str, Any]] | None = None) -> None:
        self._contracts: list[dict[str, Any]] = []
        for c in contracts if contracts is not None else source_contracts():
            self.register(c)

    def register(self, contract: dict[str, Any]) -> dict[str, Any]:
        errors = validate_contract(contract)
        if errors:
            raise GlobalMarketContractError(";".join(errors))
        domain = str(contract["domain"])
        if any(c["domain"] == domain for c in self._contracts):
            raise GlobalMarketContractError(f"duplicate_domain:{domain}")
        stored = dict(contract)
        self._contracts.append(stored)
        return stored

    def list_contracts(self) -> list[dict[str, Any]]:
        return [dict(c) for c in self._contracts]

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        if status not in CONTRACT_STATUSES:
            raise GlobalMarketContractError(f"bad_status:{status}")
        return [dict(c) for c in self._contracts if c.get("status") == status]

    def provider_required_count(self) -> int:
        return sum(1 for c in self._contracts if c.get("status") == "PROVIDER_REQUIRED")

    def contract_ready_count(self) -> int:
        return sum(1 for c in self._contracts if c.get("status") == "CONTRACT_READY")

    def status_counts(self) -> dict[str, int]:
        counts = {s: 0 for s in CONTRACT_STATUSES}
        for c in self._contracts:
            st = c.get("status")
            if st in counts:
                counts[st] += 1
        return counts

    def to_document(self, *, retrieved_at: str | None = None) -> dict[str, Any]:
        dtos = build_all_normalized_dtos(retrieved_at=retrieved_at)
        # Align DTO list to registry contracts (same order).
        by_domain = {d["domain"]: d for d in dtos}
        ordered_dtos = [by_domain[c["domain"]] for c in self._contracts if c["domain"] in by_domain]
        doc = {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "lane": LANE,
            "lane_name": LANE_NAME,
            "branch": BRANCH,
            "hard_bans": list(HARD_BANS),
            "required_domains": list(REQUIRED_DOMAINS),
            "contract_count": len(self._contracts),
            "provider_required_count": self.provider_required_count(),
            "contract_ready_count": self.contract_ready_count(),
            "status_counts": self.status_counts(),
            "contracts": self.list_contracts(),
            "normalized_dtos": ordered_dtos,
            "read_only": True,
            "exchange_write": False,
            "fabricated_live_value_count": 0,
            "private_strategy_threshold_count": 0,
        }
        errors = validate_catalog(doc)
        if errors:
            raise GlobalMarketContractError(";".join(errors))
        return doc


def build_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "nexus://pub17_a/global_market_source_contracts.schema.json",
        "title": "NEXUS PUB17-A Global Market Source Contracts",
        "schema_name": SCHEMA,
        "type": "object",
        "required": ["schema", "schema_version", "lane", "contracts", "normalized_dtos"],
        "properties": {
            "schema": {"const": SCHEMA},
            "schema_version": {"const": SCHEMA_VERSION},
            "lane": {"const": LANE},
            "contracts": {"type": "array", "minItems": len(REQUIRED_DOMAINS)},
            "normalized_dtos": {"type": "array", "minItems": len(REQUIRED_DOMAINS)},
            "provider_required_count": {"type": "integer", "minimum": 0},
        },
        "additionalProperties": True,
    }


def write_schema_artifact(root: Path | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    path = root / SCHEMA_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_catalog_artifact(root: Path | None = None, *, retrieved_at: str | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    path = root / CATALOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = GlobalMarketSourceRegistry().to_document(retrieved_at=retrieved_at)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def ensure_artifact_dir(root: Path | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    path = root / ARTIFACT_REL
    path.mkdir(parents=True, exist_ok=True)
    return path
