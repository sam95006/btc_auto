"""Read-only forensic access to old campaign artifacts — never seal or modify."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from backend.nexus_event_study.constants import (
    REFERENCE_CAMPAIGN_ID,
    REFERENCE_FINALIZER_ARTIFACT_DIR,
)


class ForensicWriteAttemptError(RuntimeError):
    """Raised when a caller attempts any write against forensic paths."""


def open_forensic_text(path: Path) -> str:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"forensic_missing:{p}")
    with open(p, "rb") as fh:
        return fh.read().decode("utf-8", errors="replace")


def open_forensic_json(path: Path) -> Any:
    return json.loads(open_forensic_text(path))


def refuse_write(path: Path, *, reason: str = "forensic_ro_ban") -> None:
    raise ForensicWriteAttemptError(f"{reason}:{path}")


def forensic_campaign_probe(repo_root: Path) -> dict[str, Any]:
    """Inspect old campaign finalizer artifacts in RO mode; never mutate partitions."""
    root = Path(repo_root)
    art = root / REFERENCE_FINALIZER_ARTIFACT_DIR
    status: dict[str, Any] = {
        "schema": "v14_b_forensic_ro_probe",
        "campaign_id": REFERENCE_CAMPAIGN_ID,
        "artifact_dir": str(art).replace("\\", "/"),
        "mode": "READ_ONLY_FORENSIC",
        "raw_partitions_modified": False,
        "raw_partitions_sealed": False,
        "write_attempt_count": 0,
        "artifact_dir_exists": art.is_dir(),
        "files_sampled": [],
        "event_study_readiness_from_old_campaign": None,
        "notes": [],
    }
    if not art.is_dir():
        status["notes"].append("reference_finalizer_artifact_dir_absent_in_worktree")
        return status

    sampled = 0
    for path in sorted(art.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".md", ".txt"}:
            continue
        text = open_forensic_text(path)
        rel = str(path.relative_to(root)).replace("\\", "/")
        status["files_sampled"].append(rel)
        if path.name == "event_study_readiness.json":
            try:
                readiness = json.loads(text)
                status["event_study_readiness_from_old_campaign"] = readiness
            except json.JSONDecodeError:
                status["notes"].append("event_study_readiness_parse_error")
        sampled += 1
        if sampled >= 20:
            break

    status["notes"].append("no_seal_no_modify_old_raw_partitions")
    status["notes"].append("real_14d_event_study_not_executed")
    return status


def scan_owned_paths_for_write_apis(owned_py_files: Iterable[Path]) -> dict[str, Any]:
    banned_tokens = (
        "abandon_open_without_finalize",
        "open_tail_seal",
        "DurablePartitionWriter",
        "seal_open_tail",
        "finalize_partition",
    )
    hits: list[dict[str, str]] = []
    for path in owned_py_files:
        if path.name == "forensic_ro.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for tok in banned_tokens:
            if f"{tok}(" in text:
                hits.append(
                    {
                        "path": str(path).replace("\\", "/"),
                        "token": tok,
                    }
                )
    return {
        "schema": "v14_b_forensic_write_api_scan",
        "banned_callable_hits": hits,
        "ok": len(hits) == 0,
    }


def forensic_env_guard() -> dict[str, Any]:
    return {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false"),
        "MAINNET": os.environ.get("MAINNET", "false"),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false"),
        "ok": (
            os.environ.get("EXCHANGE_WRITE", "false").lower() in {"", "false", "0", "no"}
            and os.environ.get("MAINNET", "false").lower() in {"", "false", "0", "no"}
            and os.environ.get("REAL_MONEY", "false").lower() in {"", "false", "0", "no"}
        ),
    }
