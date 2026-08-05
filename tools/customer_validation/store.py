"""Local JSON workspace store — not a production customer database."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tools.customer_validation.hard_bans import refuse_production_customer_db

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_WORKSPACE = PACKAGE_DIR / "workspace"

COLLECTIONS = (
    "participants",
    "consents",
    "interviews",
    "problem_rankings",
    "workflow_maps",
    "decision_object_deliveries",
    "weekly_reviews",
    "retention_evidence",
    "wtp_evidence",
    "objections",
    "conversion_evidence",
)


def resolve_workspace(path: Path | str | None = None) -> Path:
    if path is None:
        env = os.environ.get("NEXUS_CUSTOMER_VALIDATION_WORKSPACE")
        root = Path(env) if env else DEFAULT_WORKSPACE
    else:
        root = Path(path)
    if str(root).lower().startswith(("postgres://", "mysql://", "mongodb://")):
        refuse_production_customer_db()
    return root


def _collection_path(workspace: Path, name: str) -> Path:
    if name not in COLLECTIONS:
        raise KeyError(f"unknown collection: {name}")
    return workspace / f"{name}.json"


def ensure_workspace(workspace: Path | str | None = None) -> Path:
    root = resolve_workspace(workspace)
    root.mkdir(parents=True, exist_ok=True)
    for name in COLLECTIONS:
        path = _collection_path(root, name)
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")
    meta = root / "WORKSPACE_META.json"
    if not meta.exists():
        meta.write_text(
            json.dumps(
                {
                    "schema": "NEXUS_CUSTOMER_VALIDATION_WORKSPACE_V1",
                    "production_customer_database": False,
                    "fabricated_participants_forbidden": True,
                    "target_icp_cohort_size": {"min": 10, "max": 20},
                    "note": "Empty until Founder enrolls genuine ICP participants.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return root


def load_collection(name: str, workspace: Path | str | None = None) -> list[dict[str, Any]]:
    root = ensure_workspace(workspace)
    path = _collection_path(root, name)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{name}.json must be a JSON array")
    return data


def save_collection(
    name: str,
    rows: list[dict[str, Any]],
    workspace: Path | str | None = None,
) -> Path:
    root = ensure_workspace(workspace)
    path = _collection_path(root, name)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def append_row(
    name: str,
    row: dict[str, Any],
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    rows = load_collection(name, workspace)
    rows.append(row)
    save_collection(name, rows, workspace)
    return row
