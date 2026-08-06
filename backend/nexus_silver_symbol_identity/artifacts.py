"""Write immutable readiness artifacts for V17-C silver symbol identity."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_silver_symbol_identity.constants import (
    ARTIFACT_REL,
    BRANCH,
    CANONICAL_IDENTITY_FIELDS,
    EVIDENCE_CLASS,
    HARD_BANS,
    IDENTITY_VERSION,
    LANE,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PROGRAM_ID,
    SCHEMA,
    SCHEMA_REL,
)
from backend.nexus_silver_symbol_identity.fixtures import fixture_catalog
from backend.nexus_silver_symbol_identity.schema import build_schema


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_immutable_artifacts(root: Path, *, head: str, test_summary: dict[str, Any]) -> dict[str, Any]:
    art = root / ARTIFACT_REL
    art.mkdir(parents=True, exist_ok=True)
    schema = build_schema()
    schema_path = root / SCHEMA_REL
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    status = {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "branch": BRANCH,
        "identity_version": IDENTITY_VERSION,
        "created_at": utc_now(),
        "head": head,
        "owned_paths": list(OWNED_PATHS),
        "hard_bans": list(HARD_BANS),
        "canonical_identity_fields": list(CANONICAL_IDENTITY_FIELDS),
        "evidence_class": EVIDENCE_CLASS,
        "fixture_catalog": fixture_catalog(),
        "tests": test_summary,
        "recommendation": PASS_RECOMMENDATION if test_summary.get("failed", 1) == 0 else "FAIL",
        "exchange_write": False,
        "mainnet": False,
        "pr26_merged": False,
        "pr27_merged": False,
    }
    (art / "silver_symbol_identity_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )
    return status
