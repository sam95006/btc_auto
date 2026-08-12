"""JSON Schema for V16-A Trade Error Ontology V1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_trade_error_ontology_v1.constants import (
    AVOIDABILITY_LEVELS,
    ERROR_DIMENSIONS,
    ONTOLOGY_VERSION,
    PROCESS_CLASSES,
    SCHEMA,
    SCHEMA_REL,
    SEVERITY_LEVELS,
)


def build_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "nexus://v16_a/trade_error_ontology_v1.schema.json",
        "title": "NEXUS Trade Error Ontology V1",
        "description": (
            "Machine-readable trade error gene bank and classification record. "
            "AI may propose; deterministic classifier is authoritative."
        ),
        "schema_name": SCHEMA,
        "ontology_version": ONTOLOGY_VERSION,
        "type": "object",
        "required": [
            "schema",
            "ontology_version",
            "process_classification",
            "deterministic_class",
            "dimensions",
            "evidence_refs",
            "severity",
            "avoidability",
            "recurrence_signature",
            "causal_confidence",
            "classifier_authority",
            "versioning",
        ],
        "properties": {
            "schema": {"const": SCHEMA},
            "ontology_version": {"type": "string", "minLength": 1},
            "process_classification": {"enum": list(PROCESS_CLASSES)},
            "deterministic_class": {"enum": list(PROCESS_CLASSES)},
            "ai_proposed_class": {
                "anyOf": [{"enum": list(PROCESS_CLASSES)}, {"type": "null"}]
            },
            "dimensions": {
                "type": "array",
                "items": {"enum": list(ERROR_DIMENSIONS)},
                "uniqueItems": True,
            },
            "matched_gene_ids": {
                "type": "array",
                "items": {"type": "string", "pattern": "^TEG\\.[A-Z0-9_.]+$"},
            },
            "evidence_refs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["ref_key", "ref_value"],
                    "properties": {
                        "ref_key": {"type": "string"},
                        "ref_value": {},
                        "source": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "severity": {"enum": list(SEVERITY_LEVELS)},
            "avoidability": {"enum": list(AVOIDABILITY_LEVELS)},
            "recurrence_signature": {
                "type": "string",
                "minLength": 1,
                "pattern": "^RS\\|.+",
            },
            "causal_confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "classifier_authority": {
                "type": "object",
                "required": [
                    "deterministic_is_final",
                    "ai_can_override",
                    "fallback",
                ],
                "properties": {
                    "deterministic_is_final": {"const": True},
                    "ai_can_override": {"const": False},
                    "fallback": {"const": "deterministic_classifier"},
                    "ai_disagreement": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            "versioning": {
                "type": "object",
                "required": ["ontology_version", "gene_bank_checksum"],
                "properties": {
                    "ontology_version": {"type": "string"},
                    "gene_bank_checksum": {"type": "string", "minLength": 16},
                    "classifier_version": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "pnl": {"type": "number"},
            "is_win": {"type": "boolean"},
            "is_loss": {"type": "boolean"},
            "is_bad_process": {"type": "boolean"},
            "is_good_process": {"type": "boolean"},
            "supports_profitable_bad_process_win": {"const": True},
            "noncompliant_reasons": {
                "type": "array",
                "items": {"type": "string"},
            },
            "trade_id": {"type": ["string", "null"]},
        },
        "additionalProperties": True,
        "definitions": {
            "process_classes": list(PROCESS_CLASSES),
            "error_dimensions": list(ERROR_DIMENSIONS),
            "severity_levels": list(SEVERITY_LEVELS),
            "avoidability_levels": list(AVOIDABILITY_LEVELS),
        },
        "policy": {
            "ai_proposes_only": True,
            "ai_cannot_override_deterministic": True,
            "pnl_does_not_decide_process": True,
            "supports_profitable_bad_process_win": True,
            "deterministic_classifier_fallback": True,
        },
    }


def write_schema_artifact(root: Path | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    path = root / SCHEMA_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = build_schema()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_schema(root: Path | None = None) -> dict[str, Any]:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    path = root / SCHEMA_REL
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return build_schema()


def validate_classification_record(record: dict[str, Any]) -> list[str]:
    """Lightweight structural validation (no external jsonschema dependency)."""
    errors: list[str] = []
    schema = build_schema()
    for key in schema["required"]:
        if key not in record:
            errors.append(f"missing_required:{key}")
    if record.get("schema") != SCHEMA:
        errors.append("bad_schema")
    cls = record.get("process_classification")
    if cls not in PROCESS_CLASSES:
        errors.append(f"bad_process_classification:{cls}")
    det = record.get("deterministic_class")
    if det not in PROCESS_CLASSES:
        errors.append(f"bad_deterministic_class:{det}")
    if record.get("process_classification") != record.get("deterministic_class"):
        # Final class MUST equal deterministic — AI cannot diverge the final field.
        errors.append("final_class_must_equal_deterministic")
    auth = record.get("classifier_authority") or {}
    if auth.get("deterministic_is_final") is not True:
        errors.append("deterministic_must_be_final")
    if auth.get("ai_can_override") is not False:
        errors.append("ai_must_not_override")
    if auth.get("fallback") != "deterministic_classifier":
        errors.append("fallback_must_be_deterministic")
    sev = record.get("severity")
    if sev not in SEVERITY_LEVELS:
        errors.append(f"bad_severity:{sev}")
    av = record.get("avoidability")
    if av not in AVOIDABILITY_LEVELS:
        errors.append(f"bad_avoidability:{av}")
    dims = record.get("dimensions") or []
    for d in dims:
        if d not in ERROR_DIMENSIONS:
            errors.append(f"bad_dimension:{d}")
    rs = str(record.get("recurrence_signature") or "")
    if not rs.startswith("RS|"):
        errors.append("bad_recurrence_signature")
    cc = record.get("causal_confidence")
    if not isinstance(cc, (int, float)) or not (0.0 <= float(cc) <= 1.0):
        errors.append("bad_causal_confidence")
    if not isinstance(record.get("evidence_refs"), list):
        errors.append("evidence_refs_must_be_list")
    ver = record.get("versioning") or {}
    if not ver.get("ontology_version") or not ver.get("gene_bank_checksum"):
        errors.append("bad_versioning")
    return errors
